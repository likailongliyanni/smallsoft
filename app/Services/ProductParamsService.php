<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use RuntimeException;

class ProductParamsService
{
    private const COMPAT_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
    private const FALLBACK_MODEL = 'qwen3.6-plus';

    /**
     * @return array{title:string, params:array<int, array{name:string,value:string}>}
     */
    public function generate(string $text): array
    {
        $response = Http::withToken($this->apiKey())
            ->timeout((int) config('ai.defaults.vision.request_timeout', 120))
            ->acceptJson()
            ->post(self::COMPAT_BASE.'/chat/completions', [
                'model' => $this->model(),
                'messages' => [[
                    'role' => 'user',
                    'content' => $this->prompt($text),
                ]],
                'temperature' => 0.1,
                'response_format' => ['type' => 'json_object'],
                'stream' => false,
            ]);

        if (! $response->successful()) {
            $message = (string) data_get($response->json(), 'error.message', data_get($response->json(), 'message', 'AI 参数生成失败'));
            throw new RuntimeException('商品参数生成失败：'.mb_substr($message, 0, 240));
        }

        $content = data_get($response->json(), 'choices.0.message.content');
        if (is_array($content)) {
            $content = collect($content)
                ->map(fn ($part) => is_array($part) ? ($part['text'] ?? '') : (string) $part)
                ->implode('');
        }
        $content = trim((string) $content);
        $content = preg_replace('/^```(?:json)?\s*|\s*```$/i', '', $content);
        $decoded = json_decode($content, true);
        if (! is_array($decoded)) {
            throw new RuntimeException('商品参数生成结果格式不正确，请重试。');
        }

        $params = [];
        foreach ((array) ($decoded['params'] ?? []) as $item) {
            if (! is_array($item)) {
                continue;
            }
            $name = trim((string) ($item['name'] ?? ''));
            $value = trim((string) ($item['value'] ?? ''));
            if ($name !== '' && $value !== '') {
                $params[] = ['name' => mb_substr($name, 0, 30), 'value' => mb_substr($value, 0, 120)];
            }
        }
        if ($params === []) {
            throw new RuntimeException('没有从介绍中识别出有效参数，请补充材质、尺寸、颜色等信息。');
        }

        return [
            'title' => mb_substr(trim((string) ($decoded['title'] ?? '')), 0, 80),
            'params' => array_slice($params, 0, 12),
        ];
    }

    private function prompt(string $text): string
    {
        return '你是电商商品资料编辑。请把下面的一句话商品介绍整理成商品标题和参数表。'
            .'只提取原文明确给出或可安全归类的信息，禁止编造。参数名简短、参数值保留完整。'
            .'只输出 JSON：{"title":"商品标题","params":[{"name":"参数名","value":"参数值"}]}。'
            .'最多 12 项。原文：'.trim($text);
    }

    private function model(): string
    {
        try {
            $configured = \App\Models\ModelConfig::query()
                ->where('purpose', 'product_params')
                ->where('enabled', true)
                ->value('model');
            if (trim((string) $configured) !== '') {
                return trim((string) $configured);
            }
        } catch (\Throwable) {
        }

        return trim((string) config('ai.defaults.vision.model', self::FALLBACK_MODEL)) ?: self::FALLBACK_MODEL;
    }

    private function apiKey(): string
    {
        $key = trim((string) config('ai.dashscope_api_key', ''));
        if ($key === '') {
            throw new RuntimeException('服务器未配置 DASHSCOPE_API_KEY。');
        }

        return $key;
    }
}
