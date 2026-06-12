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
    private const FALLBACK_REPAIR_MODEL = 'qwen-image-2.0';

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
        $parameters = [
            'watermark' => false,
            'negative_prompt' => '旋转商品、改变角度、改变视角、改变拍摄方向、改变朝向、改变姿态、改变透视、把正面改侧面、把侧面改正面、把多台商品合并成单台、改变商品数量、脑补商品背面或侧面、补错结构、虚假配件、改变商品结构、改变商品比例、改变支架形状、改变风扇高度、错误 logo、错误包装、新增文字、模糊、低清晰度、变形、错色、复杂背景、彩色背景、过度美颜、卡通风格',
            'n' => 1,
            'prompt_extend' => false,
        ];
        $size = trim((string) env('ALIYUN_IMAGE_REPAIR_SIZE', ''));
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

        $this->ensureSuccessful($response->status(), $response->body(), '创建 Qwen-Image-2.0 图片修复失败');

        $resultUrl = $this->resultImageUrl($response->json() ?: []);
        $download = Http::timeout(300)->get($resultUrl);
        if (! $download->successful()) {
            throw new RuntimeException('下载 Qwen-Image-2.0 修复结果失败：HTTP '.$download->status());
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
        $key = trim((string) env('DASHSCOPE_API_KEY', env('ALIYUN_API_KEY', '')));
        if ($key === '') {
            throw new RuntimeException('服务器未配置 DASHSCOPE_API_KEY。');
        }

        return $key;
    }

    private function detectModel(): string
    {
        return trim((string) config('ai.defaults.vision.model', self::FALLBACK_DETECT_MODEL))
            ?: self::FALLBACK_DETECT_MODEL;
    }

    private function repairModel(): string
    {
        return trim((string) env('ALIYUN_IMAGE_REPAIR_MODEL', env('DASHSCOPE_IMAGE_REPAIR_MODEL', self::FALLBACK_REPAIR_MODEL)))
            ?: self::FALLBACK_REPAIR_MODEL;
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

        throw new RuntimeException('Qwen-Image-2.0 修复成功但没有返回结果图链接。');
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
        if (str_contains($text, 'access_denied') || str_contains($text, 'access denied')) {
            return '阿里云模型权限不足：当前 DASHSCOPE_API_KEY 无权调用 Qwen-Image-2.0 图片修复模型，请在百炼开通对应模型，或把 ALIYUN_IMAGE_REPAIR_MODEL 改成已开通的图像编辑模型。';
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
