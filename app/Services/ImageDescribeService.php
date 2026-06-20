<?php

namespace App\Services;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use RuntimeException;

/**
 * 图片智能描述：截图 + 用户的简短说明 → 阿里云百炼视觉模型 → 详细中文描述。
 *
 * 用于 snap-saver「整理成文档」的 PDF 排版：用户给某张图填一句简介，
 * AI 结合图片内容把它扩写成一段通顺、详细的说明文字，方便做图文排版。
 *
 * 调用方式完全复用 WatermarkAiService.detect 的成熟范式（compatible-mode
 * chat/completions + image_url），模型走 ModelConfig(purpose=image_describe)
 * 可后台配置，百炼上新视觉模型时后台改个模型名即可，无需改代码/重新部署。
 */
class ImageDescribeService
{
    private const COMPAT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    private const FALLBACK_MODEL = 'qwen3.6-plus';

    /**
     * @param  UploadedFile  $image  待描述的截图
     * @param  string  $userHint  用户填的简短说明（可空）
     * @param  string  $style  描述风格：detail(详细) / brief(简短) / marketing(营销)
     * @return array{description:string, model:string}
     */
    public function describe(UploadedFile $image, string $userHint = '', string $style = 'detail'): array
    {
        $apiKey = $this->apiKey();
        $mime = $image->getMimeType() ?: 'image/jpeg';
        $dataUrl = 'data:'.$mime.';base64,'.base64_encode((string) file_get_contents($image->getRealPath()));

        $response = Http::withToken($apiKey)
            ->timeout((int) config('ai.defaults.vision.request_timeout', 120))
            ->acceptJson()
            ->post(self::COMPAT_BASE.'/chat/completions', [
                'model' => $this->model(),
                'messages' => [[
                    'role' => 'user',
                    'content' => [
                        ['type' => 'text', 'text' => $this->prompt($userHint, $style)],
                        ['type' => 'image_url', 'image_url' => ['url' => $dataUrl]],
                    ],
                ]],
                'temperature' => (float) config('ai.defaults.vision.temperature', 0.4),
                'stream' => false,
            ]);

        $this->ensureSuccessful($response->status(), $response->body(), '图片描述失败');

        $content = data_get($response->json(), 'choices.0.message.content');
        if (is_array($content)) {
            $content = collect($content)
                ->map(fn ($part) => is_array($part) ? ($part['text'] ?? '') : (string) $part)
                ->implode('');
        }
        $text = trim((string) $content);
        if ($text === '') {
            throw new RuntimeException('图片描述返回了空内容，请重试。');
        }

        // 去掉可能的 markdown 包裹和多余引号
        $text = preg_replace('/^```[a-z]*\s*|\s*```$/i', '', $text);
        $text = trim($text, " \t\n\r\0\x0B\"'“”");

        return [
            'description' => $text,
            'model' => $this->model(),
        ];
    }

    private function prompt(string $userHint, string $style): string
    {
        $hint = trim($userHint);
        $hintPart = $hint !== ''
            ? "用户想表达的重点是：「{$hint}」。请围绕这个重点来解读这张图——"
              ."图是论据，用户这句话是论点，你要让图为这句话服务。"
            : '用户没有给重点。请你判断这张图最值得说明的信息是什么，把它讲透。';

        // 关键：不是“看图说话”（罗列画面里有什么），而是“解释图”——
        // 说明这张图想传达什么、有什么用、为什么重要，把图变成有意义的内容。
        $base = '你是一名擅长内容表达的编辑，不是图像标注员。'.$hintPart
            .'写作要求：'
            .'1) 不要罗列画面里有什么（不要写“图中有/画面展示了/可以看到”这类描述句），'
            .'而是解释这张图说明了什么、传达了什么信息或价值。'
            .'2) 紧扣用户给的重点展开，图只是佐证，重点才是主线。'
            .'3) 可以结合常识做合理的意义引申，但不要编造图里明显没有、也无法合理推断的事实。'
            .'4) 用通顺自然的中文，像在跟读者讲解一样，开门见山直接说重点，'
            .'不要“这张图”“如图所示”这类废话开头。'
            .'5) 输出纯文本一段话，不要 Markdown，不要分点列表。';

        return match ($style) {
            'brief' => $base.'控制在 40 字以内，一句话点出这张图的核心意义。',
            'marketing' => $base.'语气生动有感染力，突出亮点、价值和打动人的理由，控制在 120 字以内。',
            default => $base.'讲解得透彻一些，把它的意义、作用、关键信息说清楚，控制在 150 字以内。',
        };
    }

    private function model(): string
    {
        // 优先取管理员后台配置（ModelConfig purpose=image_describe），
        // 其次复用 vision 默认模型，最后兜底常量。
        return $this->adminModel('image_describe')
            ?: (trim((string) config('ai.defaults.vision.model', self::FALLBACK_MODEL)) ?: self::FALLBACK_MODEL);
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
            return '';
        }
    }

    private function apiKey(): string
    {
        $key = trim((string) config('ai.dashscope_api_key', ''));
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

        $text = strtolower($code.' '.$message);
        if (str_contains($text, 'invalidapikey') || str_contains($text, 'invalid_api_key') || str_contains($text, 'incorrect api key')) {
            $message = '阿里云 API Key 无效，请检查服务器 DASHSCOPE_API_KEY。';
        } elseif (str_contains($text, 'arrearage')) {
            $message = '阿里云账户欠费，请到百炼控制台充值。';
        } elseif (str_contains($text, 'throttling') || str_contains($text, 'rate limit')) {
            $message = '阿里云接口被限流，请稍后重试。';
        } elseif (str_contains($text, 'datainspection') || str_contains($text, 'inappropriate')) {
            $message = '图片未通过内容审核。';
        }

        throw new RuntimeException($prefix.'：'.mb_substr($message, 0, 300));
    }
}
