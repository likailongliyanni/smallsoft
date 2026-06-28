<?php

namespace App\Services;

use App\Models\ModelConfig;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Http;
use RuntimeException;
use Throwable;

/**
 * 统一的软件 AI 配置读取与 OpenAI 兼容调用。
 *
 * 管理员在后台修改配置后，下一次请求直接读取数据库，因此桌面软件无需重新构建或发版。
 * API Key 优先使用该功能单独保存的密钥；阿里云未单独保存时复用服务器 DASHSCOPE_API_KEY。
 */
class SoftwareAiConfigService
{
    public function find(string $softwareCode, string $purpose, bool $enabledOnly = true): ?ModelConfig
    {
        $query = ModelConfig::query()
            ->where('software_code', $softwareCode)
            ->where('purpose', $purpose);

        if ($enabledOnly) {
            $query->where('enabled', true);
        }

        $config = $query->latest('id')->first();
        if ($config) {
            return $config;
        }

        // 兼容尚未执行新迁移、或历史配置没有 software_code 的服务器数据。
        $legacy = ModelConfig::query()->where('purpose', $purpose);
        if ($enabledOnly) {
            $legacy->where('enabled', true);
        }

        return $legacy->latest('id')->first();
    }

    public function apiKey(ModelConfig $config): string
    {
        if (filled($config->api_key_encrypted)) {
            try {
                return trim(Crypt::decryptString((string) $config->api_key_encrypted));
            } catch (Throwable $e) {
                throw new RuntimeException('后台保存的 API Key 无法解密，请重新填写并保存。');
            }
        }

        return match ($config->provider) {
            'aliyun' => trim((string) config('ai.dashscope_api_key', '')),
            'deepseek' => trim((string) config('services.deepseek.api_key', '')),
            default => '',
        };
    }

    /**
     * @param  array<int, array<string, mixed>>  $messages
     * @param  array<string, mixed>  $overrides
     * @return array<string, mixed>
     */
    public function chat(ModelConfig $config, array $messages, array $overrides = []): array
    {
        if (! $config->enabled) {
            throw new RuntimeException('该 AI 功能已在后台停用。');
        }

        $baseUrl = rtrim((string) $config->base_url, '/');
        $model = trim((string) $config->model);
        $apiKey = $this->apiKey($config);
        if ($baseUrl === '' || $model === '') {
            throw new RuntimeException('后台的软件 AI 配置缺少 Base URL 或模型名称。');
        }
        if ($apiKey === '') {
            $hint = $config->provider === 'aliyun'
                ? '请在宝塔网站 .env 配置 DASHSCOPE_API_KEY，或在软件配置中单独填写 Key。'
                : '请在软件配置中填写 API Key。';
            throw new RuntimeException('没有可用的 API Key。'.$hint);
        }

        $endpoint = str_ends_with($baseUrl, '/chat/completions')
            ? $baseUrl
            : $baseUrl.'/chat/completions';

        $payload = array_merge([
            'model' => $model,
            'messages' => $messages,
            'temperature' => (float) ($config->temperature ?? 0.2),
            'max_tokens' => (int) ($config->max_tokens ?: 3000),
            'stream' => false,
        ], $overrides);

        $response = Http::withToken($apiKey)
            ->timeout((int) ($config->request_timeout ?: 120))
            ->acceptJson()
            ->post($endpoint, $payload);

        if (! $response->successful()) {
            $body = $response->body();
            $json = $response->json();
            $code = (string) data_get($json, 'error.code', data_get($json, 'code', $response->status()));
            $message = (string) data_get($json, 'error.message', data_get($json, 'message', mb_substr($body, 0, 500)));
            throw new RuntimeException($this->friendlyError($code, $message, $model));
        }

        $json = $response->json();
        if (! is_array($json)) {
            throw new RuntimeException('模型接口返回了无法解析的数据。');
        }

        return $json;
    }

    private function friendlyError(string $code, string $message, string $model): string
    {
        $text = strtolower($code.' '.$message);
        if (str_contains($text, 'invalidapikey') || str_contains($text, 'invalid_api_key') || str_contains($text, 'incorrect api key')) {
            return 'API Key 无效，请检查宝塔网站 .env 或该功能单独保存的 Key。';
        }
        if (str_contains($text, 'access_denied') || str_contains($text, 'model not exist') || str_contains($text, 'modelnotfound')) {
            return '当前账号无权调用模型（'.$model.'），请在百炼开通或到软件配置中更换模型。';
        }
        if (str_contains($text, 'arrearage')) {
            return '阿里云账户欠费，请到百炼控制台充值。';
        }
        if (str_contains($text, 'throttling') || str_contains($text, 'ratelimit') || str_contains($text, 'rate limit')) {
            return '模型接口被限流，请稍后重试。';
        }

        return '模型调用失败：'.mb_substr($code.'：'.$message, 0, 500);
    }
}
