<?php

namespace App\Http\Controllers;

use App\Models\SoftwareRule;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;

class RulesController extends Controller
{
    private function jsonResponse(array $data)
    {
        return response()->json(
            $data,
            200,
            ['Content-Type' => 'application/json; charset=utf-8'],
            JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE
        );
    }

    /**
     * GET /api/rules
     * 返回当前激活的知识库规则。
     * 数据来源优先级：
     *   1. software_rules 表里 is_active=true 的最新一条
     *   2. storage/app/rules/active.json（文件）
     *   3. public/rules-v1.0.1.json（静态文件兜底）
     *   4. 返回空规则（让客户端用本地兜底）
     */
    public function show(Request $request)
    {
        // 1. 数据库
        try {
            $rule = SoftwareRule::active();
            if ($rule && is_array($rule->rules)) {
                return $this->jsonResponse($rule->rules);
            }
        } catch (\Throwable $e) {
            \Log::warning('Rules DB read failed: ' . $e->getMessage());
        }

        // 2. storage 文件
        try {
            if (Storage::disk('local')->exists('rules/active.json')) {
                $data = json_decode(
                    Storage::disk('local')->get('rules/active.json'),
                    true
                );
                if (is_array($data)) {
                    return $this->jsonResponse($data);
                }
            }
        } catch (\Throwable $e) {
            \Log::warning('Rules storage file read failed: ' . $e->getMessage());
        }

        // 3. public 静态文件兜底
        try {
            $publicPath = public_path('rules-v1.0.1.json');
            if (file_exists($publicPath)) {
                $raw = file_get_contents($publicPath);
                $data = json_decode($raw, true);
                if (is_array($data) && isset($data['rules'])) {
                    return $this->jsonResponse($data['rules']);
                }
                if (is_array($data)) {
                    return $this->jsonResponse($data);
                }
            }
        } catch (\Throwable $e) {
            \Log::warning('Rules public file read failed: ' . $e->getMessage());
        }

        return $this->jsonResponse([
            'no_remote_rules' => true,
            'message' => '服务器未配置规则，使用客户端默认',
        ]);
    }

    /**
     * POST /api/admin/rules
     * 管理员上传新版本知识库（同时存表 + 存文件）
     */
    public function store(Request $request)
    {
        $data = $request->validate([
            'version' => ['required', 'string', 'max:20'],
            'rules' => ['required', 'array'],
            'changelog' => ['nullable', 'string', 'max:2000'],
            'activate' => ['nullable', 'boolean'],
        ]);

        try {
            // 把当前 active 的设为非 active
            if (!empty($data['activate'])) {
                SoftwareRule::where('is_active', true)->update(['is_active' => false]);
            }

            $rule = SoftwareRule::updateOrCreate(
                ['version' => $data['version']],
                [
                    'rules' => $data['rules'],
                    'changelog' => $data['changelog'] ?? null,
                    'is_active' => (bool)($data['activate'] ?? false),
                ]
            );
        } catch (\Throwable $e) {
            \Log::error('Rules DB write failed: ' . $e->getMessage());
            return response()->json([
                'ok' => false,
                'message' => '数据库写入失败：' . $e->getMessage(),
            ], 500);
        }

        // 同时同步到文件，便于查看/备份（失败不影响主逻辑）
        if ($rule->is_active) {
            try {
                Storage::disk('local')->put(
                    'rules/active.json',
                    json_encode($data['rules'], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_INVALID_UTF8_SUBSTITUTE)
                );
            } catch (\Throwable $e) {
                \Log::warning('Rules file sync failed (non-critical): ' . $e->getMessage());
            }
        }

        return $this->jsonResponse([
            'ok' => true,
            'id' => $rule->id,
            'version' => $rule->version,
            'is_active' => $rule->is_active,
        ]);
    }

    /**
     * GET /api/admin/rules
     * 列出所有版本
     */
    public function index(): array
    {
        $rules = SoftwareRule::query()
            ->select(['id', 'version', 'is_active', 'changelog', 'created_at'])
            ->orderByDesc('id')
            ->limit(50)
            ->get();

        return $this->ok(['items' => $rules]);
    }
}
