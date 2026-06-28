<?php

namespace App\Http\Controllers;

use App\Models\ModelConfig;
use App\Services\SoftwareAiConfigService;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Validation\ValidationException;
use Throwable;

class SoftwareConfigController extends Controller
{
    public function index(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $configs = ModelConfig::query()
            ->orderByRaw("CASE software_code WHEN 'aidoc' THEN 1 WHEN 'pic' THEN 2 WHEN 'auto' THEN 3 ELSE 9 END")
            ->orderBy('software_name')
            ->orderBy('id')
            ->get()
            ->map(fn (ModelConfig $config): array => $this->payload($config))
            ->values();

        return $this->ok([
            'configs' => $configs,
            'providers' => collect(config('ai.providers', []))
                ->map(fn (array $provider, string $code): array => [
                    'code' => $code,
                    'name' => $provider['name'] ?? $code,
                    'base_url' => $provider['base_url'] ?? '',
                    'default_model' => $provider['model'] ?? '',
                    'models' => collect($provider['presets'] ?? [])->values()->all(),
                ])->values(),
        ]);
    }

    public function store(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'id' => ['nullable', 'integer', 'exists:model_configs,id'],
            'software_code' => ['required', 'string', 'max:40', 'regex:/^[a-z0-9][a-z0-9_-]*$/'],
            'software_name' => ['required', 'string', 'max:100'],
            'purpose' => ['required', 'string', 'max:30', 'regex:/^[a-z0-9][a-z0-9_-]*$/'],
            'feature_name' => ['required', 'string', 'max:100'],
            'provider' => ['required', 'string', 'in:aliyun,deepseek,openai-compatible'],
            'base_url' => ['required', 'url', 'max:255'],
            'model' => ['required', 'string', 'max:120'],
            'api_key' => ['nullable', 'string', 'max:500'],
            'system_prompt' => ['nullable', 'string', 'max:30000'],
            'knowledge_base' => ['nullable', 'string', 'max:100000'],
            'enabled' => ['nullable', 'boolean'],
            'temperature' => ['nullable', 'numeric', 'min:0', 'max:2'],
            'max_tokens' => ['nullable', 'integer', 'min:128', 'max:128000'],
            'thinking_enabled' => ['nullable', 'boolean'],
            'reasoning_effort' => ['nullable', 'string', 'in:low,medium,high'],
            'request_timeout' => ['nullable', 'integer', 'min:10', 'max:900'],
        ]);

        $duplicate = ModelConfig::query()
            ->where('software_code', $data['software_code'])
            ->where('purpose', $data['purpose']);
        if (! empty($data['id'])) {
            $duplicate->where('id', '!=', $data['id']);
        }
        if ($duplicate->exists()) {
            throw ValidationException::withMessages([
                'purpose' => '同一软件下的功能代码不能重复。',
            ]);
        }

        $config = ! empty($data['id'])
            ? ModelConfig::query()->findOrFail($data['id'])
            : new ModelConfig();

        $config->fill([
            'software_code' => trim($data['software_code']),
            'software_name' => trim($data['software_name']),
            'purpose' => trim($data['purpose']),
            'feature_name' => trim($data['feature_name']),
            'provider' => $data['provider'],
            'base_url' => rtrim($data['base_url'], '/'),
            'model' => trim($data['model']),
            'system_prompt' => $data['system_prompt'] ?? null,
            'knowledge_base' => $data['knowledge_base'] ?? null,
            'enabled' => $request->boolean('enabled'),
            'temperature' => (float) ($data['temperature'] ?? 0.2),
            'max_tokens' => (int) ($data['max_tokens'] ?? 3000),
            'thinking_enabled' => $request->boolean('thinking_enabled'),
            'reasoning_effort' => $data['reasoning_effort'] ?? 'medium',
            'request_timeout' => (int) ($data['request_timeout'] ?? 120),
        ]);

        if (isset($data['api_key']) && trim($data['api_key']) !== '') {
            $config->api_key_encrypted = Crypt::encryptString(trim($data['api_key']));
        }
        $config->save();
        ModelConfig::query()
            ->where('software_code', $config->software_code)
            ->where('software_name', '!=', $config->software_name)
            ->update(['software_name' => $config->software_name]);

        return $this->ok(['config' => $this->payload($config->fresh())]);
    }

    public function destroy(Request $request, TokenService $tokens, ModelConfig $config): array
    {
        $this->requireAdmin($request, $tokens);
        $config->delete();

        return $this->ok();
    }

    public function test(
        Request $request,
        TokenService $tokens,
        ModelConfig $config,
        SoftwareAiConfigService $ai,
    ): array {
        $this->requireAdmin($request, $tokens);

        if (data_get($config->settings, 'api_mode') === 'image_generation') {
            throw ValidationException::withMessages([
                'model' => '图片生成/编辑模型不能用文本对话测试，请在对应软件中试跑一张图片。',
            ]);
        }

        try {
            $messages = [];
            if (filled($config->system_prompt)) {
                $messages[] = ['role' => 'system', 'content' => (string) $config->system_prompt];
            }
            $messages[] = ['role' => 'user', 'content' => '这是后台连接测试。请只回复：连接成功'];
            $result = $ai->chat($config, $messages, ['max_tokens' => 80, 'temperature' => 0]);
            $content = data_get($result, 'choices.0.message.content', '连接成功');
            if (is_array($content)) {
                $content = json_encode($content, JSON_UNESCAPED_UNICODE);
            }
            $config->update([
                'last_tested_at' => now(),
                'last_test_status' => 'success',
                'last_test_message' => mb_substr((string) $content, 0, 500),
                'last_usage' => data_get($result, 'usage'),
            ]);

            return $this->ok([
                'message' => (string) $content,
                'config' => $this->payload($config->fresh()),
            ]);
        } catch (Throwable $e) {
            $config->update([
                'last_tested_at' => now(),
                'last_test_status' => 'failed',
                'last_test_message' => mb_substr($e->getMessage(), 0, 1000),
            ]);
            throw ValidationException::withMessages(['model' => $e->getMessage()]);
        }
    }

    private function payload(ModelConfig $config): array
    {
        return [
            'id' => $config->id,
            'software_code' => $config->software_code ?: 'platform',
            'software_name' => $config->software_name ?: '平台公共能力',
            'purpose' => $config->purpose,
            'feature_name' => $config->feature_name ?: $config->purpose,
            'provider' => $config->provider,
            'base_url' => $config->base_url,
            'model' => $config->model,
            'has_api_key' => filled($config->api_key_encrypted),
            'uses_server_key' => $config->provider === 'aliyun' && filled(config('ai.dashscope_api_key')),
            'system_prompt' => $config->system_prompt,
            'knowledge_base' => $config->knowledge_base,
            'enabled' => (bool) $config->enabled,
            'temperature' => $config->temperature,
            'max_tokens' => $config->max_tokens,
            'thinking_enabled' => (bool) $config->thinking_enabled,
            'reasoning_effort' => $config->reasoning_effort,
            'request_timeout' => $config->request_timeout,
            'settings' => $config->settings,
            'last_tested_at' => $config->last_tested_at,
            'last_test_status' => $config->last_test_status,
            'last_test_message' => $config->last_test_message,
            'last_usage' => $config->last_usage,
        ];
    }

    private function requireAdmin(Request $request, TokenService $tokens): void
    {
        abort_if(! $tokens->adminFromRequest($request), 401, '管理员未登录');
    }
}
