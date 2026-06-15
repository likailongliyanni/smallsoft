<?php

namespace App\Services;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use RuntimeException;

class WatermarkAiService
{
    public const DEFAULT_MODE = 'watermark';

    public const MODES = [
        'watermark',
        'text_sticker',
        'marketing',
        'clean',
        'all',
    ];

    private const DASHSCOPE_BASE = 'https://dashscope.aliyuncs.com';
    private const COMPAT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    private const IMAGE_GENERATION_ENDPOINT = '/api/v1/services/aigc/multimodal-generation/generation';
    private const FALLBACK_DETECT_MODEL = 'qwen3.6-plus';
    private const FALLBACK_REPAIR_MODEL = 'wan2.7-image';

    public function detect(UploadedFile $image, string $mode = self::DEFAULT_MODE): array
    {
        $mode = self::normalizeMode($mode);
        $apiKey = $this->apiKey();
        $mime = $image->getMimeType() ?: 'image/jpeg';
        $dataUrl = 'data:'.$mime.';base64,'.base64_encode((string) file_get_contents($image->getRealPath()));

        $response = Http::withToken($apiKey)
            ->timeout(60)
            ->acceptJson()
            ->post(self::COMPAT_BASE.'/chat/completions', [
                'model' => $this->detectModel(),
                'messages' => [[
                    'role' => 'user',
                    'content' => [
                        [
                            'type' => 'text',
                            'text' => $this->detectPrompt($mode),
                        ],
                        ['type' => 'image_url', 'image_url' => ['url' => $dataUrl]],
                    ],
                ]],
                'temperature' => 0,
                'stream' => false,
            ]);

        $this->ensureSuccessful($response->status(), $response->body(), '图片检测失败');

        $content = data_get($response->json(), 'choices.0.message.content');
        if (is_array($content)) {
            $content = collect($content)->map(fn ($part) => is_array($part) ? ($part['text'] ?? '') : '')->implode('');
        }
        if (! is_string($content) || trim($content) === '') {
            throw new RuntimeException('图片检测返回格式异常。');
        }

        $data = $this->extractJson($content);
        $needsRepair = (bool) ($data['needs_repair'] ?? $data['has_watermark'] ?? false);

        return [
            'needs_repair' => $needsRepair,
            'has_watermark' => $needsRepair,
            'mode' => $mode,
            'mode_label' => $this->modeLabel($mode),
            'note' => mb_substr((string) ($data['note'] ?? ''), 0, 120),
        ];
    }

    public function remove(UploadedFile $image, string $mode = self::DEFAULT_MODE): string
    {
        $mode = self::normalizeMode($mode);
        $apiKey = $this->apiKey();
        $imageBytes = (string) file_get_contents($image->getRealPath());
        if ($imageBytes === '') {
            throw new RuntimeException('图片文件为空，无法修复。');
        }

        $mime = $image->getMimeType() ?: 'image/jpeg';
        $dataUrl = 'data:'.$mime.';base64,'.base64_encode($imageBytes);
        // 万相 wan2.7-image 图像编辑：parameters 仅支持 watermark / n / size，
        // 不支持 negative_prompt、prompt_extend（防改角度/防合并的约束已写进正向 prompt）。
        $parameters = [
            'watermark' => false,
            'n' => 1,
        ];
        $size = trim((string) config('ai.image_repair.size', ''));
        if ($size !== '') {
            $parameters['size'] = $size;
        }

        $response = Http::withToken($apiKey)
            ->timeout(300)
            ->acceptJson()
            ->post(self::DASHSCOPE_BASE.self::IMAGE_GENERATION_ENDPOINT, [
                'model' => $this->repairModel(),
                'input' => [
                    'messages' => [[
                        'role' => 'user',
                        'content' => [
                            ['image' => $dataUrl],
                            ['text' => $this->removePrompt($mode)],
                        ],
                    ]],
                ],
                'parameters' => $parameters,
            ]);

        $this->ensureSuccessful($response->status(), $response->body(), '创建图片修复任务失败');

        $resultUrl = $this->resultImageUrl($response->json() ?: []);
        $download = Http::timeout(300)->get($resultUrl);
        if (! $download->successful()) {
            throw new RuntimeException('下载图片修复结果失败：HTTP '.$download->status());
        }

        return $download->body();
    }

    public static function normalizeMode(?string $mode): string
    {
        $mode = trim((string) $mode);

        return in_array($mode, self::MODES, true) ? $mode : self::DEFAULT_MODE;
    }

    private function detectPrompt(string $mode): string
    {
        $suffix = '只输出 JSON，不要输出解释，不要使用 Markdown。格式：{"needs_repair":true或false,"note":"需要处理的内容和位置，20字以内"}。';

        return match ($mode) {
            'text_sticker' => '判断这张商品图片是否有后期叠加的文字贴纸、说明标签、黑色卖点条、装饰字幕、浮层卡片等需要去除的元素。不要把商品包装、商品铭牌、真实场景里的自然文字误判为需要处理。'.$suffix,
            'marketing' => '判断这张商品图片是否有促销营销广告元素，例如 618、双11、到手价、全网低价、火热进行中、活动时间、咨询客服、优惠券、底部促销横幅、价格牌、促销角标等。'.$suffix,
            'clean' => '判断这张商品图片是否有影响清爽度的后期叠加元素，例如水印、促销贴纸、无关营销文字、遮挡商品的装饰块、杂乱广告横幅等。'.$suffix,
            'all' => '判断这张商品图片是否有任何需要清除的后期干扰元素，包括水印、文字贴纸、牛皮癣营销内容、促销广告、价格横幅、平台角标、店铺名、网址、防盗文字等。'.$suffix,
            default => '判断这张图片里是否有水印，包括文字水印、半透明 logo、平台角标、网址、店铺名、防盗文字等。不要把商品本体上的真实品牌 logo 或包装文字误判为水印。'.$suffix,
        };
    }

    private function removePrompt(string $mode): string
    {
        $base = '请基于输入图片生成一张可直接用于电商平台上架的高级白底商品主图。核心约束：只清理背景和后期叠加干扰，不要重新设计或重新拍摄商品。必须保持原图中商品的数量、排列、朝向、拍摄角度、透视方向、姿态、可见零件位置和结构关系；如果原图是双向展示、多台展示、左右对比或多角度展示，必须保持原来的数量、相对位置和各自角度，不要合并成单台，不要换成新的角度。拿捏不准、被遮挡、看不清的部位，只做最小范围修补，优先保留原图可见轮廓；不要根据常识脑补背面、侧面、支架、底座、叶片或其他看不见的结构。允许在不改变主体角度和布局的前提下轻微居中、适度留白。背景改为纯白或接近纯白，画面干净高级，边缘清晰，保留自然真实光影和轻微柔和投影。清理水印、平台角标、促销文案、价格条、店铺名、网址、杂乱背景和无关物体。必须保持商品型号、颜色、材质、比例、包装、真实品牌 logo、真实包装文字不变；不要新增文案、不要新增配件、不要改变商品卖点，不要把商品画成卡通，不要过度美颜。输出单张清晰 PNG。';

        return match ($mode) {
            'text_sticker' => '重点清理图片中后期叠加的文字贴纸、说明标签、卖点条、装饰字幕、浮层卡片，并转成白底上架主图。'.$base,
            'marketing' => '重点清理图片中后期叠加的促销营销元素，例如 618、双11、到手价、优惠券、促销横幅、价格牌、促销角标、咨询客服浮层，并转成白底上架主图。'.$base,
            'clean' => '重点做图片清爽化：去掉杂乱背景、无关装饰、广告横幅和影响上架质感的干扰元素，并转成高级白底上架主图。'.$base,
            'all' => '最终目标是白底上图：去掉水印、文字贴纸、促销广告、价格横幅、平台角标、店铺名、网址、防盗文字、杂乱背景和无关物体。'.$base,
            default => '重点去除图片中的水印、文字水印、半透明 logo、平台角标、网址、店铺名、防盗文字，并转成白底上架主图。'.$base,
        };
    }

    private function modeLabel(string $mode): string
    {
        return match ($mode) {
            'text_sticker' => '去除文字贴纸',
            'marketing' => '去除营销广告',
            'clean' => '图片清爽化',
            'all' => '白底上图',
            default => '去除水印',
        };
    }

    private function apiKey(): string
    {
        // 走 config 而非 env()：config:cache 生效后 .env 不再加载，env() 会拿到空。
        $key = trim((string) config('ai.dashscope_api_key', ''));
        if ($key === '') {
            throw new RuntimeException('服务器未配置 DASHSCOPE_API_KEY。');
        }

        return $key;
    }

    private function detectModel(): string
    {
        // 优先取管理员后台配置（ModelConfig purpose=image_detect），其次 config，最后兜底常量。
        return $this->adminModel('image_detect')
            ?: (trim((string) config('ai.defaults.vision.model', self::FALLBACK_DETECT_MODEL)) ?: self::FALLBACK_DETECT_MODEL);
    }

    private function repairModel(): string
    {
        // 优先取管理员后台配置（ModelConfig purpose=image_repair）：百炼上新模型时
        // 后台改个模型名即可，无需改代码/env/重新部署。其次 config，最后兜底常量。
        return $this->adminModel('image_repair')
            ?: (trim((string) config('ai.image_repair.model', self::FALLBACK_REPAIR_MODEL)) ?: self::FALLBACK_REPAIR_MODEL);
    }

    private function adminModel(string $purpose): string
    {
        try {
            $model = \App\Models\ModelConfig::query()
                ->where('purpose', $purpose)
                ->where('enabled', true)
                ->value('model');

            return trim((string) $model);
        } catch (\Throwable $e) {
            // 表/字段缺失等异常时静默回退到 config。
            return '';
        }
    }

    private function resultImageUrl(array $payload): string
    {
        $content = data_get($payload, 'output.choices.0.message.content', []);
        if (is_array($content)) {
            foreach ($content as $part) {
                $url = is_array($part) ? trim((string) ($part['image'] ?? '')) : '';
                if ($url !== '') {
                    return $url;
                }
            }
        }

        foreach (['output.results.0.url', 'output.images.0.url', 'output.image_url', 'data.0.url', 'url'] as $path) {
            $url = trim((string) data_get($payload, $path, ''));
            if ($url !== '') {
                return $url;
            }
        }

        throw new RuntimeException('图片修复成功但没有返回结果图链接。');
    }

    private function ensureSuccessful(int $status, string $body, string $prefix): void
    {
        if ($status >= 200 && $status < 300) {
            return;
        }

        $json = json_decode($body, true);
        $code = (string) data_get($json, 'error.code', data_get($json, 'code', $status));
        $message = (string) data_get($json, 'error.message', data_get($json, 'message', mb_substr($body, 0, 300)));

        throw new RuntimeException($prefix.'：'.$this->friendlyError($code, $message));
    }

    private function friendlyError(string $code, string $message): string
    {
        $text = strtolower($code.' '.$message);
        if (str_contains($text, 'invalidapikey') || str_contains($text, 'invalid_api_key') || str_contains($text, 'incorrect api key')) {
            return '阿里云 API Key 无效，请检查服务器 .env 的 DASHSCOPE_API_KEY。';
        }
        if (str_contains($text, 'access_denied') || str_contains($text, 'access denied') || str_contains($text, 'model not exist') || str_contains($text, 'modelnotfound')) {
            return '阿里云模型权限不足：当前 DASHSCOPE_API_KEY 无权调用图片修复模型（'.$this->repairModel().'），请在百炼开通对应模型，或把 ALIYUN_IMAGE_REPAIR_MODEL 改成已开通的图像编辑模型。';
        }
        if (str_contains($text, 'arrearage')) {
            return '阿里云账户欠费，请到百炼控制台充值。';
        }
        if (str_contains($text, 'throttling') || str_contains($text, 'ratelimit') || str_contains($text, 'rate limit')) {
            return '阿里云接口被限流，请稍后重试。';
        }
        if (str_contains($text, 'datainspection') || str_contains($text, 'inappropriate') || str_contains($text, 'green')) {
            return '图片未通过内容审核，已跳过。';
        }

        return mb_substr($code.'：'.$message, 0, 300);
    }

    private function extractJson(string $content): array
    {
        $content = trim($content);
        if (preg_match('/```(?:json)?\s*(.*?)\s*```/s', $content, $matches)) {
            $content = trim($matches[1]);
        }
        if (preg_match('/\{.*\}/s', $content, $matches)) {
            $data = json_decode($matches[0], true);
            return is_array($data) ? $data : [];
        }

        return [];
    }
}
