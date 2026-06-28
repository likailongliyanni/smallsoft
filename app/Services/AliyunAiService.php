<?php

namespace App\Services;

use App\Models\GenerationJob;
use App\Models\QuotaLog;
use App\Models\User;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use RuntimeException;
use Throwable;

/**
 * 阿里云百炼 DashScope 纯净版 AI 调用服务
 *
 * 设计原则：
 *  - 默认档优先读取软件配置中心（auto/script），未配置时使用内置档位
 *  - API Key 默认来自 .env: DASHSCOPE_API_KEY，也可在功能配置中单独保存
 *  - 默认 thinking 关闭（避免推理超时）
 *  - 提示词复用 AiScriptService::buildJsonDslPrompt（保证规则一致）
 */
class AliyunAiService
{
    public const BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1';

    /**
     * 模型清单 — 客户端只看到 key/label/desc，实际模型名在 model 字段
     */
    public const MODELS = [
        'code' => [
            'model' => 'qwen3-coder-plus',
            'label' => '代码生成（默认）',
            'desc' => '专为脚本/代码生成优化，准确率最高',
            'max_tokens' => 8192,
            'temperature' => 0.1,
            'request_timeout' => 180,
            'thinking_enabled' => false,
        ],
        'balanced' => [
            'model' => 'qwen3.6-plus',
            'label' => '平衡',
            'desc' => '通用强模型，支持视觉理解',
            'max_tokens' => 8192,
            'temperature' => 0.2,
            'request_timeout' => 180,
            'thinking_enabled' => false,
        ],
        'strong' => [
            'model' => 'qwen3-max',
            'label' => '强档（慢/贵）',
            'desc' => '复杂场景使用，速度较慢',
            'max_tokens' => 8192,
            'temperature' => 0.2,
            'request_timeout' => 240,
            'thinking_enabled' => false,
        ],
        'fast' => [
            'model' => 'qwen3.6-flash',
            'label' => '快速（便宜）',
            'desc' => '简单流程优先使用',
            'max_tokens' => 8192,
            'temperature' => 0.2,
            'request_timeout' => 120,
            'thinking_enabled' => false,
        ],
        'vision' => [
            'model' => 'qwen-vl-max-latest',
            'label' => '视觉专用',
            'desc' => '截图分析、UI 元素识别',
            'max_tokens' => 4096,
            'temperature' => 0.1,
            'request_timeout' => 180,
            'thinking_enabled' => false,
        ],
    ];

    public const DEFAULT_KEY = 'code';

    public function __construct(
        private AiScriptService $scriptService,
        private SoftwareAiConfigService $softwareAi,
    ) {}

    /**
     * 生成自动化脚本（核心入口）
     */
    public function generate(User $user, array $payload, string $modelKey = self::DEFAULT_KEY): GenerationJob
    {
        $modelKey = isset(self::MODELS[$modelKey]) ? $modelKey : self::DEFAULT_KEY;
        $spec = $this->effectiveSpec($modelKey);

        $startedAt = microtime(true);
        $stepCount = count($payload['steps'] ?? []);

        $job = GenerationJob::create([
            'user_id' => $user->id,
            'flow_name' => $payload['flow_name'] ?? '未命名流程',
            'status' => 'pending',
            'step_count' => $stepCount,
            'request_payload' => $payload,
            'warnings' => $payload['warnings'] ?? [],
        ]);

        try {
            if (! empty($spec['disabled'])) {
                throw new RuntimeException('自动化脚本生成功能已在后台停用。');
            }
            if ($user->availableGenerations() <= 0) {
                throw new RuntimeException('生成次数不足，请购买额度或联系管理员添加测试次数。');
            }

            $apiKey = isset($spec['_config'])
                ? $this->softwareAi->apiKey($spec['_config'])
                : $this->apiKey();
            if ($apiKey === '') {
                throw new RuntimeException('服务器未配置 DASHSCOPE_API_KEY。请管理员在 .env 中配置。');
            }

            $result = $this->callDashScope($apiKey, $spec, $payload);

            $job->update([
                'status' => 'completed',
                'result_script' => $result['script'],
                'used_provider' => $spec['_config']->provider ?? 'aliyun',
                'used_model' => $spec['model'],
                'usage' => $result['usage'],
                'duration_ms' => $this->durationMs($startedAt),
                'reasoning_content' => $result['reasoning_content'] ?? null,
            ]);

            $this->consumeQuota($user, $job);

            return $job->fresh();
        } catch (Throwable $e) {
            $job->update([
                'status' => 'failed',
                'error_message' => $e->getMessage(),
                'duration_ms' => $this->durationMs($startedAt),
            ]);

            throw $e;
        }
    }

    /**
     * 列出客户端可见的模型清单
     */
    public function listModels(): array
    {
        return collect(self::MODELS)->map(function ($spec, $key) {
            $spec = $this->effectiveSpec($key);
            return [
            'key' => $key,
            'model' => $spec['model'],
            'label' => $spec['label'],
            'desc' => $spec['desc'],
            'is_default' => $key === self::DEFAULT_KEY,
            ];
        })->values()->all();
    }

    /**
     * 测试 API Key 是否可用
     */
    public function testKey(string $modelKey = self::DEFAULT_KEY): array
    {
        $spec = $this->effectiveSpec($modelKey);
        if (! empty($spec['disabled'])) {
            return ['ok' => false, 'message' => '自动化脚本生成功能已在后台停用。'];
        }
        $apiKey = isset($spec['_config'])
            ? $this->softwareAi->apiKey($spec['_config'])
            : $this->apiKey();
        if ($apiKey === '') {
            return [
                'ok' => false,
                'message' => '未配置 DASHSCOPE_API_KEY（请在 .env 中设置）',
            ];
        }

        try {
            $response = Http::withToken($apiKey)
                ->timeout(30)
                ->acceptJson()
                ->post($this->chatEndpoint($spec['base_url'] ?? self::BASE_URL), [
                    'model' => $spec['model'],
                    'messages' => [
                        ['role' => 'system', 'content' => '只输出 JSON。'],
                        ['role' => 'user', 'content' => '输出 {"version":"1.0","name":"test","actions":[{"type":"goto","url":"https://example.com"}]}'],
                    ],
                    'temperature' => 0.1,
                    'max_tokens' => 200,
                    'stream' => false,
                ]);

            if (! $response->successful()) {
                return [
                    'ok' => false,
                    'status' => $response->status(),
                    'message' => '阿里 API 返回错误：'.$response->status(),
                    'body' => $response->body(),
                ];
            }

            $content = data_get($response->json(), 'choices.0.message.content');

            return [
                'ok' => true,
                'model' => $spec['model'],
                'sample' => is_string($content) ? mb_substr($content, 0, 200) : null,
                'usage' => data_get($response->json(), 'usage'),
            ];
        } catch (Throwable $e) {
            return [
                'ok' => false,
                'message' => $e->getMessage(),
            ];
        }
    }

    /**
     * 真正的 HTTP 调用
     */
    private function callDashScope(string $apiKey, array $spec, array $payload): array
    {
        // 复用 AiScriptService 的提示词构建逻辑（保证规则一致）
        [$system, $user] = $this->scriptService->buildJsonDslPrompt($payload);
        if (filled($spec['_config']->system_prompt ?? null)) {
            $system = (string) $spec['_config']->system_prompt;
        }

        $messages = $this->buildMessages($system, $user, $payload);

        $body = [
            'model' => $spec['model'],
            'messages' => $messages,
            'temperature' => $spec['temperature'],
            'max_tokens' => $spec['max_tokens'],
            'stream' => false,
        ];

        // thinking 默认关闭。如果以后要开，按 Aliyun OpenAI 兼容协议加这个：
        // $body['enable_thinking'] = true;
        // $body['thinking_budget'] = 16384;

        $response = Http::withToken($apiKey)
            ->timeout($spec['request_timeout'])
            ->acceptJson()
            ->post($this->chatEndpoint($spec['base_url'] ?? self::BASE_URL), $body);

        if (! $response->successful()) {
            // 识别阿里特定错误码，给出友好提示
            $body = $response->json();
            $errCode = data_get($body, 'error.code', '');
            $errType = data_get($body, 'error.type', '');
            $errMsg = data_get($body, 'error.message', '');

            if ($errCode === 'Arrearage' || $errType === 'Arrearage') {
                throw new RuntimeException(
                    '阿里云账户欠费，请去百炼控制台充值后再试：https://bailian.console.aliyun.com/'
                );
            }
            if (in_array($errCode, ['InvalidApiKey', 'AuthenticationError'], true)) {
                throw new RuntimeException(
                    '阿里云 API Key 无效或被禁用，请检查 .env 里的 DASHSCOPE_API_KEY'
                );
            }
            if (in_array($errCode, ['Throttling', 'RateLimitExceeded'], true)) {
                throw new RuntimeException(
                    '阿里云接口被限流，稍等几秒重试。如果频繁出现可去百炼控制台提额'
                );
            }
            if (str_contains((string) $errMsg, 'model not exist') || $errCode === 'ModelNotExist') {
                throw new RuntimeException(
                    "阿里云模型「{$spec['model']}」不存在或当前账户没开通访问权限"
                );
            }

            throw new RuntimeException(
                '阿里云调用失败 HTTP '.$response->status().': '
                .($errMsg ?: mb_substr($response->body(), 0, 500))
            );
        }

        $json = $response->json();
        $content = data_get($json, 'choices.0.message.content');
        if (! is_string($content) || trim($content) === '') {
            throw new RuntimeException('阿里云没有返回有效脚本内容。');
        }

        return [
            'script' => $this->stripCodeFence($content),
            'usage' => data_get($json, 'usage'),
            'reasoning_content' => data_get($json, 'choices.0.message.reasoning_content'),
        ];
    }

    /**
     * 把 system / user 拼成 OpenAI 兼容的 messages 数组
     * 如果 payload 里有截图 URL，按多模态格式打包
     */
    private function buildMessages(string $system, string $user, array $payload): array
    {
        $images = $this->collectVisionImages($payload);

        if ($images === []) {
            return [
                ['role' => 'system', 'content' => $system],
                ['role' => 'user', 'content' => $user],
            ];
        }

        $content = [
            ['type' => 'text', 'text' => $user."\n\n【视觉输入说明】下面图片是录制点击点附近的截图，请结合 DOM/selector 一起判断控件类型。"],
        ];

        foreach ($images as $img) {
            if (! empty($img['label'])) {
                $content[] = ['type' => 'text', 'text' => '截图：'.$img['label']];
            }
            $content[] = [
                'type' => 'image_url',
                'image_url' => ['url' => $img['url']],
            ];
        }

        return [
            ['role' => 'system', 'content' => $system],
            ['role' => 'user', 'content' => $content],
        ];
    }

    private function collectVisionImages(array $payload): array
    {
        $images = [];
        $push = function ($value, string $label = '') use (&$images): void {
            if (count($images) >= 20) {
                return;
            }
            $url = is_string($value) ? trim($value) : trim((string) ($value['url'] ?? $value['image_url'] ?? ''));
            if (! is_string($url) || $url === '') {
                return;
            }
            if (! str_starts_with($url, 'http://') && ! str_starts_with($url, 'https://') && ! str_starts_with($url, 'data:image/')) {
                return;
            }
            $images[] = ['url' => $url, 'label' => $label];
        };

        foreach (($payload['images'] ?? []) as $idx => $img) {
            $push($img, 'images['.$idx.']');
        }
        foreach (($payload['steps'] ?? []) as $idx => $step) {
            if (! is_array($step)) {
                continue;
            }
            foreach (['screenshot_url', 'image_url', 'crop_image_url'] as $key) {
                if (! empty($step[$key])) {
                    $push($step[$key], 'step '.($step['step_index'] ?? ($idx + 1)).' '.$key);
                }
            }
        }

        return $images;
    }

    private function effectiveSpec(string $modelKey): array
    {
        $modelKey = isset(self::MODELS[$modelKey]) ? $modelKey : self::DEFAULT_KEY;
        $spec = self::MODELS[$modelKey];
        $spec['base_url'] = self::BASE_URL;

        // 客户端明确选择其它档位时尊重用户选择；默认档由后台统一控制。
        if ($modelKey !== self::DEFAULT_KEY) {
            return $spec;
        }

        $config = $this->softwareAi->find('auto', 'script', false);
        if (! $config) {
            return $spec;
        }

        $spec['model'] = $config->model ?: $spec['model'];
        $spec['base_url'] = rtrim((string) ($config->base_url ?: self::BASE_URL), '/');
        $spec['temperature'] = (float) ($config->temperature ?? $spec['temperature']);
        $spec['max_tokens'] = (int) ($config->max_tokens ?: $spec['max_tokens']);
        $spec['request_timeout'] = (int) ($config->request_timeout ?: $spec['request_timeout']);
        $spec['thinking_enabled'] = (bool) $config->thinking_enabled;
        $spec['_config'] = $config;
        $spec['disabled'] = ! $config->enabled;

        return $spec;
    }

    private function chatEndpoint(string $baseUrl): string
    {
        $baseUrl = rtrim($baseUrl, '/');
        return str_ends_with($baseUrl, '/chat/completions')
            ? $baseUrl
            : $baseUrl.'/chat/completions';
    }

    private function apiKey(): string
    {
        // 走 config 而非 env()：config:cache 生效后 .env 不再加载，env() 会拿到空。
        return trim((string) config('ai.dashscope_api_key', ''));
    }

    private function consumeQuota(User $user, GenerationJob $job): void
    {
        DB::transaction(function () use ($user, $job): void {
            $fresh = User::query()->lockForUpdate()->findOrFail($user->id);
            if ($fresh->free_generations > 0) {
                $fresh->decrement('free_generations');
            } elseif ($fresh->paid_generations > 0) {
                $fresh->decrement('paid_generations');
            } else {
                throw new RuntimeException('生成次数不足。');
            }

            QuotaLog::create([
                'user_id' => $fresh->id,
                'change_value' => -1,
                'source' => 'aliyun_generation',
                'note' => '阿里云脚本生成任务 #'.$job->id,
            ]);
        });
    }

    private function stripCodeFence(string $content): string
    {
        $content = trim($content);
        if (preg_match('/^```(?:json|python|py)?\s*(.*?)\s*```$/s', $content, $matches)) {
            return trim($matches[1]);
        }

        return $content;
    }

    private function durationMs(float $startedAt): int
    {
        return (int) round((microtime(true) - $startedAt) * 1000);
    }
}
