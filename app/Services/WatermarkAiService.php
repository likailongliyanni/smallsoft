<?php

namespace App\Services;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
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
    private const WATERMARK_MODEL = 'wanx2.1-imageedit';
    private const DETECT_MODEL = 'qwen-vl-max-latest';

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
                'model' => self::DETECT_MODEL,
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
        $ossUrl = $this->uploadToDashScopeOss($apiKey, $image);
        $taskId = $this->createRemoveTask($apiKey, $ossUrl, $mode);
        $resultUrl = $this->waitTask($apiKey, $taskId);

        $response = Http::timeout(180)->get($resultUrl);
        if (! $response->successful()) {
            throw new RuntimeException('下载图片修复结果失败：HTTP '.$response->status());
        }

        return $response->body();
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
        $base = '处理后要保持商品主体、真实品牌 logo、商品外观、结构比例、自然光影和背景一致，不要改变商品型号、颜色、形状，不要新增文字或装饰。';

        return match ($mode) {
            'text_sticker' => '去除图片中后期叠加的文字贴纸、说明标签、黑色卖点条、装饰字幕、浮层卡片等，自动补全被遮挡背景。'.$base,
            'marketing' => '去除图片中的促销营销广告元素，例如 618、双11、到手价、全网低价、火热进行中、活动时间、咨询客服、优惠券、底部促销横幅、价格牌、促销角标等，自动补全为自然背景。'.$base,
            'clean' => '对图片进行清爽化处理，去除水印、促销贴纸、无关营销文字、遮挡商品的装饰块、杂乱广告横幅等干扰元素，让画面干净自然。'.$base,
            'all' => '去除图片中的水印、文字贴纸、牛皮癣营销内容、促销广告、价格横幅、平台角标、店铺名、网址、防盗文字等所有后期叠加干扰元素，并自动补全背景。'.$base,
            default => '去除图片中的水印、文字水印、半透明 logo、平台角标、网址、店铺名、防盗文字等，保持商品和画面其他内容不变。'.$base,
        };
    }

    private function modeLabel(string $mode): string
    {
        return match ($mode) {
            'text_sticker' => '去除文字贴纸',
            'marketing' => '去除营销广告',
            'clean' => '图片清爽化',
            'all' => '全部去除',
            default => '去除水印',
        };
    }

    private function uploadToDashScopeOss(string $apiKey, UploadedFile $image): string
    {
        $policy = Http::withToken($apiKey)
            ->timeout(60)
            ->acceptJson()
            ->get(self::DASHSCOPE_BASE.'/api/v1/uploads?action=getPolicy&model='.self::WATERMARK_MODEL);

        $this->ensureSuccessful($policy->status(), $policy->body(), '获取图片上传授权失败');

        $data = $policy->json('data') ?: [];
        foreach (['upload_host', 'upload_dir', 'policy', 'signature', 'oss_access_key_id'] as $key) {
            if (empty($data[$key])) {
                throw new RuntimeException('图片上传授权返回不完整。');
            }
        }

        $ext = strtolower($image->getClientOriginalExtension() ?: 'jpg');
        $ext = preg_replace('/[^a-z0-9]/', '', $ext) ?: 'jpg';
        $key = rtrim((string) $data['upload_dir'], '/').'/'.Str::uuid()->toString().'.'.$ext;

        $fields = [
            'OSSAccessKeyId' => (string) $data['oss_access_key_id'],
            'Signature' => (string) $data['signature'],
            'policy' => (string) $data['policy'],
            'key' => $key,
            'x-oss-object-acl' => (string) ($data['x_oss_object_acl'] ?? 'private'),
            'x-oss-forbid-overwrite' => (string) ($data['x_oss_forbid_overwrite'] ?? 'true'),
            'success_action_status' => '200',
        ];

        $upload = Http::timeout(180)
            ->attach('file', (string) file_get_contents($image->getRealPath()), $image->getClientOriginalName() ?: 'image.jpg')
            ->post((string) $data['upload_host'], $fields);

        if (! $upload->successful()) {
            throw new RuntimeException('图片上传失败：HTTP '.$upload->status());
        }

        return 'oss://'.$key;
    }

    private function createRemoveTask(string $apiKey, string $ossUrl, string $mode): string
    {
        $response = Http::withToken($apiKey)
            ->withHeaders([
                'X-DashScope-Async' => 'enable',
                'X-DashScope-OssResourceResolve' => 'enable',
            ])
            ->timeout(60)
            ->acceptJson()
            ->post(self::DASHSCOPE_BASE.'/api/v1/services/aigc/image2image/image-synthesis', [
                'model' => self::WATERMARK_MODEL,
                'input' => [
                    'function' => 'remove_watermark',
                    'prompt' => $this->removePrompt($mode),
                    'base_image_url' => $ossUrl,
                ],
                'parameters' => ['n' => 1],
            ]);

        $this->ensureSuccessful($response->status(), $response->body(), '创建图片修复任务失败');

        $taskId = data_get($response->json(), 'output.task_id');
        if (! is_string($taskId) || $taskId === '') {
            throw new RuntimeException('创建图片修复任务失败：没有返回 task_id。');
        }

        return $taskId;
    }

    private function waitTask(string $apiKey, string $taskId): string
    {
        $deadline = time() + 300;
        while (time() < $deadline) {
            $response = Http::withToken($apiKey)
                ->timeout(60)
                ->acceptJson()
                ->get(self::DASHSCOPE_BASE.'/api/v1/tasks/'.$taskId);

            $this->ensureSuccessful($response->status(), $response->body(), '查询图片修复任务失败');

            $output = $response->json('output') ?: [];
            $status = (string) ($output['task_status'] ?? '');
            if ($status === 'SUCCEEDED') {
                $url = data_get($output, 'results.0.url');
                if (! is_string($url) || $url === '') {
                    throw new RuntimeException('图片修复任务完成但没有返回结果图。');
                }

                return $url;
            }
            if (in_array($status, ['FAILED', 'CANCELED', 'UNKNOWN'], true)) {
                throw new RuntimeException($this->friendlyError(
                    (string) ($output['code'] ?? $status),
                    (string) ($output['message'] ?? '任务失败')
                ));
            }

            sleep(2);
        }

        throw new RuntimeException('图片修复任务超时（5 分钟）。');
    }

    private function apiKey(): string
    {
        $key = trim((string) env('DASHSCOPE_API_KEY', env('ALIYUN_API_KEY', '')));
        if ($key === '') {
            throw new RuntimeException('服务器未配置 DASHSCOPE_API_KEY。');
        }

        return $key;
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
