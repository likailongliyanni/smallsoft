<?php

namespace App\Http\Controllers;

use App\Models\FeedbackLog;
use App\Models\GenerationJob;
use App\Models\ModelConfig;
use App\Models\Order;
use App\Models\QuotaLog;
use App\Models\TrainingSubmission;
use App\Models\User;
use App\Services\AliyunAiService;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Illuminate\Validation\ValidationException;
use RuntimeException;
use Throwable;

class AdminController extends Controller
{
    public function login(Request $request, TokenService $tokens): array
    {
        $data = $request->validate([
            'username' => ['required', 'string', 'max:80'],
            'password' => ['required', 'string', 'max:120'],
        ]);

        if ($data['username'] !== env('ADMIN_USERNAME') || $data['password'] !== env('ADMIN_PASSWORD')) {
            throw ValidationException::withMessages(['username' => 'Admin username or password is incorrect.']);
        }

        $admin = User::updateOrCreate(
            ['username' => $data['username']],
            [
                'name' => 'System Admin',
                'password' => Hash::make($data['password']),
                'role' => 'admin',
                'status' => 'active',
                'last_login_at' => now(),
            ],
        );

        return $this->ok([
            'token' => $tokens->createAdminToken($admin),
            'admin' => $this->adminPayload($admin),
        ]);
    }

    public function logout(Request $request, TokenService $tokens): array
    {
        $tokens->revokeAdminToken($request);

        return $this->ok();
    }

    public function me(Request $request, TokenService $tokens): array
    {
        $admin = $this->requireAdmin($request, $tokens);

        return $this->ok(['admin' => $this->adminPayload($admin)]);
    }

    public function stats(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        return $this->ok([
            'stats' => [
                'users' => User::where('role', 'user')->count(),
                'active_users' => User::where('role', 'user')->where('status', 'active')->count(),
                'generation_jobs' => GenerationJob::count(),
                'training_submissions' => TrainingSubmission::count(),
                'open_feedback' => FeedbackLog::where('status', 'open')->count(),
                'paid_orders' => Order::where('status', 'paid')->count(),
            ],
        ]);
    }

    public function users(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $q = trim((string) $request->query('q', ''));

        $query = User::where('role', 'user');
        if ($q !== '') {
            $query->where(function ($qb) use ($q) {
                $qb->where('username', 'like', "%{$q}%")
                   ->orWhere('nickname', 'like', "%{$q}%")
                   ->orWhere('name', 'like', "%{$q}%")
                   ->orWhere('mobile', 'like', "%{$q}%")
                   ->orWhere('email', 'like', "%{$q}%");
            });
        }

        $users = $query->latest('id')
            ->limit(200)
            ->get([
                'id',
                'username',
                'name',
                'nickname',
                'nickname_edit_count',
                'email',
                'mobile',
                'status',
                'free_generations',
                'paid_generations',
                'created_at',
                'last_login_at',
            ]);

        return $this->ok([
            'users' => $users->toArray(),
            'query' => $q,
            'total' => $users->count(),
        ]);
    }

    public function updateUser(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'id' => ['required', 'integer', 'exists:users,id'],
            'name' => ['nullable', 'string', 'max:80'],
            'email' => ['nullable', 'email', 'max:120'],
            'mobile' => ['nullable', 'string', 'max:40'],
            'status' => ['nullable', 'string', 'in:active,disabled'],
            'free_generations' => ['nullable', 'integer', 'min:0', 'max:100000'],
            'paid_generations' => ['nullable', 'integer', 'min:0', 'max:100000'],
        ]);

        $user = User::where('role', 'user')->findOrFail($data['id']);
        $user->fill(collect($data)->except('id')->toArray());
        $user->save();

        return $this->ok(['user' => $user->fresh()->toArray()]);
    }

    public function addQuota(Request $request, TokenService $tokens): array
    {
        $admin = $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'user_id' => ['required', 'integer', 'exists:users,id'],
            'quota' => ['required', 'integer', 'min:-10000', 'max:10000', 'not_in:0'],
            'note' => ['nullable', 'string', 'max:255'],
        ]);

        $user = DB::transaction(function () use ($data, $admin): User {
            $user = User::where('role', 'user')->lockForUpdate()->findOrFail($data['user_id']);
            $user->paid_generations = max(0, $user->paid_generations + (int) $data['quota']);
            $user->save();

            QuotaLog::create([
                'user_id' => $user->id,
                'admin_id' => $admin->id,
                'change_value' => (int) $data['quota'],
                'source' => 'admin',
                'note' => $data['note'] ?? 'Admin quota adjustment',
            ]);

            return $user->fresh();
        });

        return $this->ok(['user' => $user->toArray()]);
    }

    public function getModel(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $configs = [
            'vision' => $this->modelPayload($this->modelConfig('vision')),
            'script' => $this->modelPayload($this->modelConfig('script')),
        ];

        return $this->ok([
            'model_config' => $configs['script'],
            'model_configs' => $configs,
            'providers' => $this->providerPayload(),
        ]);
    }

    // 智能截图软件「图片修复/检测」模型——只存模型名，API Key 仍取服务器 DASHSCOPE_API_KEY。
    // 百炼上线新模型时，管理员在后台改名即可，无需改代码/部署。
    public function getImageModel(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        return $this->ok(['image_model' => $this->imageModelPayload()]);
    }

    public function saveImageModel(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'repair_model' => ['required', 'string', 'max:120'],
            'detect_model' => ['nullable', 'string', 'max:120'],
        ]);

        $this->upsertImageModel('image_repair', trim($data['repair_model']));
        if (! empty($data['detect_model'])) {
            $this->upsertImageModel('image_detect', trim($data['detect_model']));
        }

        return $this->ok(['image_model' => $this->imageModelPayload()]);
    }

    private function imageModelPayload(): array
    {
        return [
            'repair_model' => $this->imageModelName('image_repair', (string) config('ai.image_repair.model', 'wan2.7-image')),
            'detect_model' => $this->imageModelName('image_detect', (string) config('ai.defaults.vision.model', 'qwen3.6-plus')),
        ];
    }

    private function imageModelName(string $purpose, string $fallback): string
    {
        $model = trim((string) ModelConfig::query()
            ->where('purpose', $purpose)
            ->where('enabled', true)
            ->value('model'));

        return $model !== '' ? $model : $fallback;
    }

    private function upsertImageModel(string $purpose, string $model): void
    {
        $config = ModelConfig::query()->where('purpose', $purpose)->first()
            ?: new ModelConfig(['purpose' => $purpose]);
        $config->purpose = $purpose;
        $config->provider = 'aliyun';
        $config->model = $model;
        $config->enabled = true;
        $config->save();
    }

    public function saveModel(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'purpose' => ['nullable', 'string', 'in:vision,script'],
            'provider' => ['nullable', 'string', 'in:deepseek,aliyun,openai-compatible'],
            'base_url' => ['nullable', 'url', 'max:255'],
            'model' => ['nullable', 'string', 'max:120'],
            'api_key' => ['nullable', 'string', 'max:500'],
            'system_prompt' => ['nullable', 'string', 'max:12000'],
            'enabled' => ['nullable'],
            'temperature' => ['nullable', 'numeric', 'min:0', 'max:2'],
            'max_tokens' => ['nullable', 'integer', 'min:256', 'max:64000'],
            'thinking_enabled' => ['nullable'],
            'reasoning_effort' => ['nullable', 'string', 'in:low,medium,high'],
            'request_timeout' => ['nullable', 'integer', 'min:30', 'max:600'],
        ]);

        $purpose = $data['purpose'] ?? 'script';
        $defaults = config("ai.defaults.{$purpose}", []);
        $provider = $data['provider'] ?? ($defaults['provider'] ?? config('ai.default_provider', 'aliyun'));
        $defaultProvider = config("ai.providers.{$provider}", []);

        $config = $this->modelConfig($purpose) ?: new ModelConfig(['purpose' => $purpose]);
        $config->purpose = $purpose;
        $config->provider = $provider;
        $config->base_url = rtrim($data['base_url'] ?? ($defaults['base_url'] ?? ($defaultProvider['base_url'] ?? '')), '/');
        $config->model = $data['model'] ?? ($defaults['model'] ?? ($defaultProvider['model'] ?? ''));
        $config->system_prompt = $data['system_prompt'] ?? null;
        $config->enabled = $request->has('enabled') ? $request->boolean('enabled') : true;
        $config->temperature = (float) ($data['temperature'] ?? ($defaults['temperature'] ?? config('ai.temperature')));
        $config->max_tokens = (int) ($data['max_tokens'] ?? ($defaults['max_tokens'] ?? config('ai.max_tokens')));
        $config->thinking_enabled = $request->has('thinking_enabled')
            ? $request->boolean('thinking_enabled')
            : (bool) ($defaultProvider['thinking_enabled'] ?? false);
        $config->reasoning_effort = $data['reasoning_effort'] ?? ($defaultProvider['reasoning_effort'] ?? 'high');
        $config->request_timeout = (int) ($data['request_timeout'] ?? ($defaults['request_timeout'] ?? config('ai.request_timeout')));

        if (isset($data['api_key']) && trim($data['api_key']) !== '') {
            $config->api_key_encrypted = Crypt::encryptString(trim($data['api_key']));
        }

        $config->save();

        return $this->ok(['model_config' => $this->modelPayload($config)]);
    }

    public function testModel(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'purpose' => ['nullable', 'string', 'in:vision,script'],
        ]);
        $purpose = $data['purpose'] ?? 'script';

        $config = $this->modelConfig($purpose);
        if (! $config || ! $config->base_url || ! $config->model || ! $config->api_key_encrypted) {
            throw ValidationException::withMessages(['model' => '璇峰厛淇濆瓨瀹屾暣鐨勫ぇ妯″瀷閰嶇疆']);
        }

        try {
            $apiKey = Crypt::decryptString($config->api_key_encrypted);
            $endpoint = $this->chatEndpoint($config->base_url);
            $response = Http::withToken($apiKey)
                ->timeout((int) ($config->request_timeout ?: 60))
                ->acceptJson()
                ->post($endpoint, $this->testPayload($config, $purpose));

            if (! $response->successful()) {
                throw new RuntimeException($response->status().' '.$response->body());
            }

            $message = (string) data_get($response->json(), 'choices.0.message.content', 'OK');
            $config->update([
                'last_tested_at' => now(),
                'last_test_status' => 'success',
                'last_test_message' => mb_substr($message, 0, 500),
                'last_usage' => data_get($response->json(), 'usage'),
            ]);

            return $this->ok(['message' => $message, 'model_config' => $this->modelPayload($config->fresh())]);
        } catch (Throwable $e) {
            $config->update([
                'last_tested_at' => now(),
                'last_test_status' => 'failed',
                'last_test_message' => mb_substr($e->getMessage(), 0, 1000),
            ]);

            throw ValidationException::withMessages(['model' => 'Model test failed: '.$e->getMessage()]);
        }
    }

    /**
     * 阿里云全家桶 - 测试连接
     * 直接读 .env 的 DASHSCOPE_API_KEY，不依赖 model_configs 表
     */
    public function testAliyun(Request $request, TokenService $tokens, AliyunAiService $aliyun): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'model_key' => ['nullable', 'string', 'in:code,balanced,strong,fast,vision'],
        ]);

        $result = $aliyun->testKey($data['model_key'] ?? AliyunAiService::DEFAULT_KEY);

        return $this->ok([
            'result' => $result,
            'models' => $aliyun->listModels(),
            'has_env_key' => trim((string) config('ai.dashscope_api_key', '')) !== '',
        ]);
    }

    public function testVisionModel(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'image' => ['required', 'file', 'mimes:jpg,jpeg,png,webp', 'max:5120'],
            'prompt' => ['nullable', 'string', 'max:2000'],
        ]);

        $config = $this->modelConfig('vision');
        if (! $config || ! $config->base_url || ! $config->model || ! $config->api_key_encrypted) {
            throw ValidationException::withMessages(['model' => 'Please save the vision model config first.']);
        }

        $path = $request->file('image')->store('admin_ai_tests');
        $absolutePath = Storage::disk('local')->path($path);
        $mime = $request->file('image')->getMimeType() ?: 'image/jpeg';
        $dataUrl = 'data:'.$mime.';base64,'.base64_encode((string) file_get_contents($absolutePath));
        $prompt = trim((string) ($data['prompt'] ?? ''));
        if ($prompt === '') {
            $prompt = 'Analyze this browser automation screenshot. The yellow dot marks the user click. Return JSON only with target, element_type, visible_text, suggested_action, confidence, reason.';
        }

        try {
            $startedAt = microtime(true);
            $apiKey = Crypt::decryptString($config->api_key_encrypted);
            $endpoint = $this->chatEndpoint($config->base_url);
            $response = Http::withToken($apiKey)
                ->timeout((int) ($config->request_timeout ?: 120))
                ->acceptJson()
                ->post($endpoint, $this->visionTestPayload($config, $dataUrl, $prompt));

            if (! $response->successful()) {
                throw new RuntimeException($response->status().' '.$response->body());
            }

            $json = $response->json();
            $message = (string) data_get($json, 'choices.0.message.content', '');
            $parsed = json_decode($this->stripJsonFence($message), true);
            $config->update([
                'last_tested_at' => now(),
                'last_test_status' => 'success',
                'last_test_message' => mb_substr($message, 0, 500),
                'last_usage' => data_get($json, 'usage'),
            ]);

            return $this->ok([
                'message' => $message,
                'parsed' => is_array($parsed) ? $parsed : null,
                'duration_ms' => (int) round((microtime(true) - $startedAt) * 1000),
                'stored_path' => $path,
                'usage' => data_get($json, 'usage'),
                'model_config' => $this->modelPayload($config->fresh()),
            ]);
        } catch (Throwable $e) {
            $config->update([
                'last_tested_at' => now(),
                'last_test_status' => 'failed',
                'last_test_message' => mb_substr($e->getMessage(), 0, 1000),
            ]);

            throw ValidationException::withMessages(['model' => 'Vision model test failed: '.$e->getMessage()]);
        }
    }

    private function testPayload(ModelConfig $config, string $purpose = 'script'): array
    {
        $testMaxTokens = $purpose === 'script' ? 300 : 20;

        $payload = [
            'model' => $config->model,
            'messages' => [
                ['role' => 'system', 'content' => 'You are a strict API test assistant.'],
                ['role' => 'user', 'content' => $purpose === 'script'
                    ? 'Return this exact JSON object only: {"version":"1.0","name":"test","actions":[{"type":"goto","url":"https://example.com"}]}'
                    : 'Connection test. Reply OK only.'],
            ],
            'temperature' => 0,
            'max_tokens' => $testMaxTokens,
            'stream' => false,
        ];

        if ($this->isDeepSeek($config)) {
            $payload['thinking'] = ['type' => 'disabled'];
        }

        return $payload;
    }

    private function visionTestPayload(ModelConfig $config, string $dataUrl, string $prompt): array
    {
        return [
            'model' => $config->model,
            'messages' => [
                ['role' => 'system', 'content' => 'You analyze UI screenshots for browser automation. Return valid JSON only.'],
                [
                    'role' => 'user',
                    'content' => [
                        ['type' => 'text', 'text' => $prompt],
                        ['type' => 'image_url', 'image_url' => ['url' => $dataUrl]],
                    ],
                ],
            ],
            'temperature' => 0,
            'max_tokens' => min((int) ($config->max_tokens ?: 2048), 4096),
            'stream' => false,
        ];
    }

    private function modelConfig(string $purpose): ?ModelConfig
    {
        return ModelConfig::query()
            ->where('purpose', $purpose)
            ->latest('id')
            ->first();
    }

    private function stripJsonFence(string $content): string
    {
        $content = trim($content);
        if (str_starts_with($content, '```')) {
            $content = trim($content, "` \n\r\t");
            if (str_starts_with($content, 'json')) {
                $content = trim(substr($content, 4));
            }
        }

        return $content;
    }

    public function jobs(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $jobs = GenerationJob::with('user:id,username,name')
            ->latest('id')
            ->limit(100)
            ->get();

        return $this->ok(['jobs' => $jobs->toArray()]);
    }

    public function orders(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $orders = Order::with('user:id,username,name')
            ->latest('id')
            ->limit(100)
            ->get();

        return $this->ok(['orders' => $orders->toArray()]);
    }

    public function createOrder(Request $request, TokenService $tokens): array
    {
        $admin = $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'user_id' => ['required', 'integer', 'exists:users,id'],
            'plan_name' => ['required', 'string', 'max:80'],
            'quota' => ['required', 'integer', 'min:1', 'max:100000'],
            'amount_cents' => ['required', 'integer', 'min:0', 'max:100000000'],
            'status' => ['nullable', 'string', 'in:pending,paid,cancelled'],
            'payment_channel' => ['nullable', 'string', 'max:40'],
            'payment_trade_no' => ['nullable', 'string', 'max:120'],
        ]);

        $order = DB::transaction(function () use ($data, $admin): Order {
            $order = Order::create([
                'user_id' => $data['user_id'],
                'order_no' => 'M'.now()->format('YmdHis').Str::upper(Str::random(6)),
                'plan_name' => $data['plan_name'],
                'quota' => (int) $data['quota'],
                'amount_cents' => (int) $data['amount_cents'],
                'status' => $data['status'] ?? 'paid',
                'payment_channel' => $data['payment_channel'] ?? 'manual',
                'payment_trade_no' => $data['payment_trade_no'] ?? null,
                'paid_at' => ($data['status'] ?? 'paid') === 'paid' ? now() : null,
            ]);

            if ($order->status === 'paid') {
                $user = User::where('role', 'user')->lockForUpdate()->findOrFail($order->user_id);
                $user->increment('paid_generations', $order->quota);

                QuotaLog::create([
                    'user_id' => $user->id,
                    'admin_id' => $admin->id,
                    'change_value' => $order->quota,
                    'source' => 'manual_order',
                    'note' => '鎵嬪伐璁㈠崟 '.$order->order_no,
                ]);
            }

            return $order->fresh();
        });

        return $this->ok(['order' => $order->toArray()]);
    }

    public function feedback(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $items = FeedbackLog::with('user:id,username,name')
            ->latest('id')
            ->limit(200)
            ->get([
                'id', 'user_id', 'category', 'flow_name', 'source',
                'content', 'error_message', 'template_path', 'meta',
                'contact', 'status', 'created_at',
            ]);

        return $this->ok(['feedback' => $items->toArray()]);
    }

    public function feedbackDetail(Request $request, TokenService $tokens, int $id): array
    {
        $this->requireAdmin($request, $tokens);

        $item = FeedbackLog::with('user:id,username,name')->findOrFail($id);

        $templateData = null;
        $hasTemplateFile = false;
        if ($item->template_path) {
            try {
                if (Storage::disk('local')->exists($item->template_path)) {
                    $raw = Storage::disk('local')->get($item->template_path);
                    $templateData = json_decode($raw, true);
                    $hasTemplateFile = true;
                }
            } catch (Throwable $e) {
                $templateData = ['_error' => '璇诲彇妯℃澘鏂囦欢澶辫触: ' . $e->getMessage()];
            }
        }

        return $this->ok([
            'feedback' => $item->toArray(),
            'template' => $templateData,
            'has_template_file' => $hasTemplateFile,
        ]);
    }

    public function updateFeedback(Request $request, TokenService $tokens, int $id): array
    {
        $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'status' => ['required', 'string', 'in:open,handling,resolved,closed'],
        ]);

        $item = FeedbackLog::findOrFail($id);
        $item->status = $data['status'];
        $item->save();

        return $this->ok(['feedback' => $item->fresh()->toArray()]);
    }

    private function requireAdmin(Request $request, TokenService $tokens): User
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '绠＄悊鍛樻湭鐧诲綍');

        return $admin;
    }

    private function adminPayload(User $admin): array
    {
        return [
            'id' => $admin->id,
            'username' => $admin->username,
            'name' => $admin->name,
            'role' => $admin->role,
        ];
    }

    private function modelPayload(?ModelConfig $config): ?array
    {
        if (! $config) {
            return null;
        }

        return [
            'id' => $config->id,
            'purpose' => $config->purpose ?? 'script',
            'provider' => $config->provider,
            'base_url' => $config->base_url,
            'model' => $config->model,
            'has_api_key' => filled($config->api_key_encrypted),
            'system_prompt' => $config->system_prompt,
            'enabled' => $config->enabled,
            'temperature' => $config->temperature,
            'max_tokens' => $config->max_tokens,
            'thinking_enabled' => $config->thinking_enabled,
            'reasoning_effort' => $config->reasoning_effort,
            'request_timeout' => $config->request_timeout,
            'last_tested_at' => $config->last_tested_at,
            'last_test_status' => $config->last_test_status,
            'last_test_message' => $config->last_test_message,
            'last_usage' => $config->last_usage,
        ];
    }

    private function providerPayload(): array
    {
        return collect(config('ai.providers', []))
            ->map(fn (array $provider, string $key): array => [
                'key' => $key,
                'name' => $provider['name'] ?? $key,
                'base_url' => $provider['base_url'] ?? '',
                'model' => $provider['model'] ?? '',
                'thinking_enabled' => (bool) ($provider['thinking_enabled'] ?? false),
                'reasoning_effort' => $provider['reasoning_effort'] ?? 'medium',
                'presets' => $provider['presets'] ?? [],
            ])
            ->values()
            ->all();
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
}


