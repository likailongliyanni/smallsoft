<?php

namespace App\Services;

use App\Models\GenerationJob;
use App\Models\ModelConfig;
use App\Models\QuotaLog;
use App\Models\User;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Schema;
use RuntimeException;
use Throwable;

class AiScriptService
{
    public function generate(User $user, array $payload): GenerationJob
    {
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
            if ($user->availableGenerations() <= 0) {
                throw new RuntimeException('生成次数不足，请购买额度或联系管理员添加测试次数。');
            }

            $config = $this->activeModelConfig();
            if (! $config) {
                if (! config('platform.allow_local_fallback')) {
                    throw new RuntimeException('后台还没有配置可用的大模型 API Key。请管理员进入 /admin 配置模型。');
                }

                $script = $this->localFallbackScript($payload);
                $job->update([
                    'status' => 'completed_local_fallback',
                    'result_script' => $script,
                    'used_provider' => 'local-fallback',
                    'used_model' => 'template',
                    'duration_ms' => $this->durationMs($startedAt),
                ]);
                $this->consumeQuota($user, $job, 'local_fallback');

                return $job->fresh();
            }

            $result = $this->callChatCompletions($config, $payload);
            $job->update([
                'status' => 'completed',
                'result_script' => $result['script'],
                'used_provider' => $config->provider,
                'used_model' => $config->model,
                'usage' => $result['usage'],
                'duration_ms' => $this->durationMs($startedAt),
                // 把思考过程存到 error_message 字段（临时复用，避免改表结构）
                // 或单独字段，看后续是否要扩展
                'reasoning_content' => $result['reasoning_content'] ?? null,
            ]);
            $this->consumeQuota($user, $job, 'ai_generation');

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

    public function buildPrompt(array $payload): array
    {
        // 根据 format 字段路由到不同 system prompt
        $format = $payload['format'] ?? 'python_v1';

        if ($format === 'json_dsl_v1') {
            return $this->buildJsonDslPrompt($payload);
        }

        // 旧版 Python 代码生成（保留向后兼容）
        $system = $payload['system_prompt'] ?? $this->defaultSystemPrompt();
        $user = json_encode([
            'goal' => '根据用户录制的网页操作流程，生成可直接运行的 Python Playwright 批量自动化脚本。',
            'output_contract' => [
                'language' => 'python',
                'framework' => 'playwright.sync_api',
                'data_source' => 'excel_or_csv',
                'return_format' => 'code_only',
            ],
            'business_rules' => [
                '需要用户提供文本或文件的步骤，必须映射为 template_fields 里的表格字段。',
                '普通点击、按钮、链接不生成表格字段。',
                '文本框必须先点击或双击定位，再从表格字段输入。',
                '下拉菜单、弹窗选择、文件上传、等待、人工验证必须按录制顺序执行。',
                '登录、短信、滑块、验证码、风控校验必须保留人工确认点，不得绕过。',
                '定位失败必须输出步骤编号、字段名称、URL 和定位信息。',
            ],
            'payload' => $payload,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);

        return [$system, $user];
    }

    /**
     * JSON DSL v1 提示词构建（新版桌面软件用）
     * system prompt 在服务器侧统一维护，客户端只发数据
     */
    public function buildJsonDslPrompt(array $payload): array
    {
        $category = $payload['category'] ?? 'browser';
        $system = $this->jsonDslSystemPrompt($category);

        $userPayload = [
            'flow_name' => $payload['flow_name'] ?? '未命名',
            'category' => $category,
            'init_url' => $payload['init_url'] ?? ($payload['notes'] ?? ''),
            'steps' => $payload['steps'] ?? [],
        ];

        // 多次录制融合（v2.0+）：若 payload 包含 sessions，附加进 user 消息
        // AI 会按 EXP-040-multi-session-fusion 的规则融合
        if (! empty($payload['sessions']) && is_array($payload['sessions']) && count($payload['sessions']) > 1) {
            $userPayload['multi_session'] = true;
            $userPayload['session_count'] = (int) ($payload['session_count'] ?? count($payload['sessions']));
            $userPayload['sessions'] = $payload['sessions'];
        }

        $user = json_encode($userPayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);

        return [$system, $user];
    }

    /**
     * JSON DSL 系统提示词（通用框架 + 分类经验包）
     *
     * @param string $category 场景分类：browser / excel / word / ps / pdf
     *
     * 加载顺序：
     *   1) resources/prompts/json_dsl_system.md           - 通用框架
     *   2) resources/prompts/patterns/common/*.md         - 所有场景通用经验
     *   3) resources/prompts/patterns/{category}/*.md     - 特定场景经验
     *   4) ai_patterns 表 category=common 的 + 该 category 的（数据库可远程推送）
     */
    public function jsonDslSystemPrompt(string $category = 'browser'): string
    {
        $parts = [];

        // 1) 通用框架
        $basePath = resource_path('prompts/json_dsl_system.md');
        if (is_file($basePath)) {
            $parts[] = trim((string) file_get_contents($basePath));
        } else {
            $parts[] = $this->defaultJsonDslSystemPrompt();
        }

        // 2) 通用经验文件
        $this->appendPatternsDir($parts, resource_path('prompts/patterns/common'));

        // 3) 聚水潭等专项场景：先加载 browser 经验做基础，再叠加专项经验
        //    （专项经验可以覆盖/补充 browser 通用规则）
        $browserSubcategories = ['jst'];
        if (in_array($category, $browserSubcategories, true)) {
            $this->appendPatternsDir($parts, resource_path('prompts/patterns/browser'));
        }

        // 4) 该场景的经验文件
        if ($category && $category !== 'common') {
            $this->appendPatternsDir($parts, resource_path("prompts/patterns/{$category}"));
        }

        // 5) 数据库经验包（通用 + 浏览器基础 + 该场景）
        try {
            if (class_exists('App\\Models\\AiPattern') && Schema::hasTable('ai_patterns')) {
                $dbCategories = ['common'];
                if (in_array($category, $browserSubcategories, true)) {
                    $dbCategories[] = 'browser';
                }
                if ($category) {
                    $dbCategories[] = $category;
                }
                $dbPatterns = \App\Models\AiPattern::query()
                    ->where('enabled', true)
                    ->whereIn('category', array_unique(array_filter($dbCategories)))
                    ->orderBy('priority')
                    ->orderBy('id')
                    ->get();
                foreach ($dbPatterns as $p) {
                    if (filled($p->content)) {
                        $parts[] = "### 模式：{$p->title}\n".trim($p->content);
                    }
                }
            }
        } catch (Throwable $e) {
            // 数据库不可用时降级
        }

        return implode("\n\n", $parts);
    }

    private function appendPatternsDir(array &$parts, string $dir): void
    {
        if (! is_dir($dir)) return;
        $files = glob($dir.'/*.md');
        sort($files);
        foreach ($files as $f) {
            // 跳过 README
            if (str_ends_with(basename($f), 'README.md')) continue;
            $content = trim((string) file_get_contents($f));
            if ($content !== '') {
                $parts[] = $content;
            }
        }
    }

    private function defaultJsonDslSystemPrompt(): string
    {
        return <<<'PROMPT'
你是浏览器自动化指令生成器。用户给你录制的网页操作步骤（含 selector/scoped_selector/xpath/label/excel_column 等字段），你必须输出一个 JSON 指令对象。

【严格输出要求】
1. 只输出 JSON 对象，从 { 开始，以 } 结束
2. 不要输出 Python 代码、HTML、Markdown
3. 不要任何解释文字、注释、前后说明
4. 不要用 ```json 或 ``` 包裹

【JSON Schema】
{
  "version": "1.0",
  "name": "<流程名>",
  "actions": [
    {"type": "goto", "url": "..."},
    {"type": "fill", "selector": "...", "value": "..."},
    {"type": "fill", "selector": "...", "from_excel": "<列名>"},
    {"type": "click", "selector": "...", "wait_after": 500},
    {"type": "select_option", "selector": "text=\"...\"", "wait_after": 400},
    {"type": "check", "selector": "...", "checked": true},
    {"type": "upload", "selector": "...", "from_excel": "<列名>"},
    {"type": "scroll", "to": "bottom"},
    {"type": "scroll", "to": "top"},
    {"type": "scroll", "selector": ".css-selector"},
    {"type": "press", "key": "PageDown"},
    {"type": "delay", "ms": 1000}
  ]
}

【字段说明】
- type: 必填，必须是 goto/fill/click/select_option/check/upload/scroll/press/delay 之一
- selector: 必填（delay 除外），CSS 或 Playwright 文本选择器
- value: 固定值（fill/select_option 用）
- from_excel: Excel 列名（input 类步骤的 excel_column 非空时用）
- wait_after: 毫秒（click/select_option，触发下拉/弹窗的 click 设 800）
- checked: true 或 false（check 用）

【选择器优先级】
对每个 step，按顺序选用：
1. step.scoped_selector 非空 → 直接用（最稳）
2. step.selector 看起来稳定（含 :has-text 或 placeholder）→ 用
3. 兜底 → 用 "xpath=" + step.xpath

【from_excel 规则】
- step.excel_column 非空 → fill/select_option 必须用 from_excel="<列名>"
- excel_column 为空 → 用 value 写固定值

【wait_after 建议】
- 普通点击不需要或设 300
- 触发下拉/弹窗的 click → 800
- select_option → 400

【任务】
读取 user 消息里的 steps 数组，按顺序转换为 actions 输出完整 JSON。

【再次强调】
只输出 JSON。不要 Python。不要解释。不要 Markdown。从 { 开始，以 } 结束。
PROMPT;
    }

    public function defaultSystemPrompt(): string
    {
        $path = resource_path('prompts/automation_script_system.md');
        if (is_file($path)) {
            return trim((string) file_get_contents($path));
        }

        return '你是一个资深网页自动化工程师。请根据用户登记的网页步骤生成 Python Playwright 批量自动化脚本，只输出代码。';
    }

    private function activeModelConfig(): ?ModelConfig
    {
        $config = ModelConfig::query()
            ->where('enabled', true)
            ->where('purpose', 'script')
            ->latest('id')
            ->first();

        if ($config && $config->base_url && $config->model && $config->api_key_encrypted) {
            return $config;
        }

        $provider = config('ai.default_provider', 'deepseek');
        $providerConfig = config("ai.providers.{$provider}", config('ai.providers.deepseek', []));
        $apiKeyEnv = $providerConfig['api_key_env'] ?? match ($provider) {
            'aliyun' => 'DASHSCOPE_API_KEY',
            'deepseek' => 'DEEPSEEK_API_KEY',
            default => 'OPENAI_COMPATIBLE_API_KEY',
        };
        $envApiKey = trim((string) env($apiKeyEnv, ''));
        if ($envApiKey === '' && $provider === 'aliyun') {
            $envApiKey = trim((string) env('ALIYUN_API_KEY', ''));
        }
        if ($envApiKey === '') {
            return null;
        }

        $config = new ModelConfig();
        $config->provider = $provider;
        $config->base_url = $providerConfig['base_url'] ?? null;
        $config->model = $providerConfig['model'] ?? null;
        $config->api_key_encrypted = Crypt::encryptString($envApiKey);
        $config->system_prompt = $this->defaultSystemPrompt();
        $config->enabled = true;
        $config->temperature = config('ai.temperature');
        $config->max_tokens = config('ai.max_tokens');
        $config->thinking_enabled = (bool) ($providerConfig['thinking_enabled'] ?? false);
        $config->reasoning_effort = $providerConfig['reasoning_effort'] ?? 'medium';
        $config->request_timeout = config('ai.request_timeout');

        return $config;
    }

    private function callChatCompletions(ModelConfig $config, array $payload): array
    {
        [$system, $user] = $this->buildPrompt([
            ...$payload,
            'system_prompt' => $config->system_prompt ?: $this->defaultSystemPrompt(),
        ]);

        $apiKey = Crypt::decryptString($config->api_key_encrypted);
        $endpoint = $this->chatEndpoint($config->base_url);
        $body = [
            'model' => $config->model,
            'messages' => $this->chatMessages($system, $user, $payload),
            'temperature' => $config->temperature ?? config('ai.temperature'),
            'stream' => false,
        ];

        if ($config->max_tokens) {
            $body['max_tokens'] = (int) $config->max_tokens;
        }

        if ($this->isDeepSeek($config)) {
            $body['thinking'] = [
                'type' => $config->thinking_enabled ? 'enabled' : 'disabled',
            ];
            $body['reasoning_effort'] = $config->reasoning_effort ?: 'high';
        } elseif ($this->isAliyun($config) && $config->thinking_enabled) {
            $body['enable_thinking'] = true;
            if ($config->reasoning_effort && $config->reasoning_effort !== 'medium') {
                $body['thinking_budget'] = match ($config->reasoning_effort) {
                    'high' => 38400,
                    'low' => 4096,
                    default => 16384,
                };
            }
        }

        $response = Http::withToken($apiKey)
            ->timeout((int) ($config->request_timeout ?: config('ai.request_timeout')))
            ->acceptJson()
            ->post($endpoint, $body);

        if (! $response->successful()) {
            throw new RuntimeException('模型调用失败：'.$response->status().' '.$response->body());
        }

        $json = $response->json();
        $content = data_get($json, 'choices.0.message.content');
        if (! is_string($content) || trim($content) === '') {
            throw new RuntimeException('模型没有返回有效脚本内容。');
        }

        // 取 DeepSeek 的思考过程（reasoning_content）
        $reasoning = data_get($json, 'choices.0.message.reasoning_content');
        if (! is_string($reasoning)) {
            $reasoning = null;
        }

        if ($config->exists) {
            $config->update(['last_usage' => data_get($json, 'usage')]);
        }

        return [
            'script' => $this->stripCodeFence($content),
            'usage' => data_get($json, 'usage'),
            'reasoning_content' => $reasoning,
        ];
    }

    private function chatMessages(string $system, string $user, array $payload): array
    {
        $images = $this->collectVisionImages($payload);
        if ($images === []) {
            return [
                ['role' => 'system', 'content' => $system],
                ['role' => 'user', 'content' => $user],
            ];
        }

        $content = [
            [
                'type' => 'text',
                'text' => $user."\n\n【视觉输入说明】下面的图片来自用户操作现场或点击点附近截图，请结合 DOM/selector/xpath/文字一起判断控件类型。",
            ],
        ];

        foreach ($images as $image) {
            if (($image['label'] ?? '') !== '') {
                $content[] = [
                    'type' => 'text',
                    'text' => '截图：'.$image['label'],
                ];
            }
            $content[] = [
                'type' => 'image_url',
                'image_url' => [
                    'url' => $image['url'],
                ],
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

            $url = null;
            if (is_string($value)) {
                $url = trim($value);
            } elseif (is_array($value)) {
                $url = trim((string) ($value['url']
                    ?? $value['image_url']
                    ?? $value['data_url']
                    ?? $value['base64']
                    ?? ''));
                $label = trim((string) ($value['label'] ?? $value['name'] ?? $label));
            }

            if (! is_string($url) || $url === '') {
                return;
            }

            if (! str_starts_with($url, 'http://')
                && ! str_starts_with($url, 'https://')
                && ! str_starts_with($url, 'data:image/')) {
                return;
            }

            $images[] = [
                'url' => $url,
                'label' => $label,
            ];
        };

        foreach (($payload['images'] ?? []) as $idx => $image) {
            $push($image, 'images['.$idx.']');
        }

        foreach (($payload['steps'] ?? []) as $idx => $step) {
            if (! is_array($step)) {
                continue;
            }

            foreach (['screenshot_url', 'screenshot_data_url', 'image_url', 'image_data_url', 'crop_image_url', 'crop_data_url'] as $key) {
                if (! empty($step[$key])) {
                    $label = 'step '.($step['step_index'] ?? ($idx + 1)).' '.$key;
                    $push($step[$key], $label);
                }
            }

            if (! empty($step['image']) && (is_string($step['image']) || is_array($step['image']))) {
                $label = 'step '.($step['step_index'] ?? ($idx + 1)).' image';
                $push($step['image'], $label);
            }
        }

        return $images;
    }

    private function consumeQuota(User $user, GenerationJob $job, string $source): void
    {
        DB::transaction(function () use ($user, $job, $source): void {
            $fresh = User::query()->lockForUpdate()->findOrFail($user->id);
            if ($fresh->free_generations > 0) {
                $fresh->decrement('free_generations');
            } elseif ($fresh->paid_generations > 0) {
                $fresh->decrement('paid_generations');
            } else {
                throw new RuntimeException('生成次数不足，请购买额度或联系管理员添加测试次数。');
            }

            QuotaLog::create([
                'user_id' => $fresh->id,
                'change_value' => -1,
                'source' => $source,
                'note' => '脚本生成任务 #'.$job->id,
            ]);
        });
    }

    private function localFallbackScript(array $payload): string
    {
        $json = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);

        return <<<PY
# 后台尚未配置 DeepSeek API Key，这是本地兜底脚本骨架。
# 配置 DeepSeek 后，系统会生成完整的 Playwright 自动化程序。

import json

FLOW = json.loads(r'''$json''')

def main():
    print("流程名称:", FLOW.get("flow_name", "未命名流程"))
    print("录制步骤数:", len(FLOW.get("steps", [])))
    print("请在后台配置 DeepSeek API Key 后重新生成正式脚本。")

if __name__ == "__main__":
    main()
PY;
    }

    private function chatEndpoint(string $baseUrl): string
    {
        $baseUrl = rtrim($baseUrl, '/');

        return str_ends_with($baseUrl, '/chat/completions')
            ? $baseUrl
            : $baseUrl.'/chat/completions';
    }

    private function isDeepSeek(ModelConfig $config): bool
    {
        return $config->provider === 'deepseek'
            || str_contains((string) $config->base_url, 'deepseek.com');
    }

    private function isAliyun(ModelConfig $config): bool
    {
        return $config->provider === 'aliyun'
            || str_contains((string) $config->base_url, 'dashscope.aliyuncs.com');
    }

    private function stripCodeFence(string $content): string
    {
        $content = trim($content);
        if (preg_match('/^```(?:python|py)?\s*(.*?)\s*```$/s', $content, $matches)) {
            return trim($matches[1]);
        }

        return $content;
    }

    private function durationMs(float $startedAt): int
    {
        return (int) round((microtime(true) - $startedAt) * 1000);
    }
}
