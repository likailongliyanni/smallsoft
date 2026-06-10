<?php

namespace App\Http\Controllers;

use App\Models\FeedbackLog;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

class FeedbackController extends Controller
{
    /**
     * 接收用户反馈
     *
     * 两种调用形态：
     * A) 旧网页：{category, content, contact}
     * B) 新软件：{flow_name, template, note, error, source}
     *    - template 是流程的完整 JSON（meta/dsl/steps）
     *    - 按 user_id 建文件夹存到 storage/app/feedback/{user_id}/{timestamp}.json
     */
    public function store(Request $request, TokenService $tokens): array
    {
        $user = $tokens->userFromRequest($request);

        // 检测调用形态
        if ($request->filled('template') || $request->filled('flow_name')) {
            return $this->storeFromSoftware($request, $user);
        }

        return $this->storeFromWeb($request, $user);
    }

    /** 旧网页反馈 */
    private function storeFromWeb(Request $request, $user): array
    {
        $data = $request->validate([
            'category' => ['nullable', 'string', 'max:60'],
            'content' => ['required', 'string', 'max:5000'],
            'contact' => ['nullable', 'string', 'max:120'],
        ]);

        $feedback = FeedbackLog::create([
            'user_id' => $user?->id,
            'category' => $data['category'] ?? 'general',
            'source' => 'web',
            'content' => $data['content'],
            'contact' => $data['contact'] ?? null,
            'status' => 'open',
        ]);

        return $this->ok(['feedback_id' => $feedback->id]);
    }

    /** 桌面软件反馈（带流程 JSON） */
    private function storeFromSoftware(Request $request, $user): array
    {
        $data = $request->validate([
            'flow_name' => ['nullable', 'string', 'max:120'],
            'template' => ['nullable', 'array'],
            'note' => ['nullable', 'string', 'max:5000'],
            'error' => ['nullable', 'string', 'max:5000'],
            'source' => ['nullable', 'string', 'max:30'], // manual / auto_error
        ]);

        $template = $data['template'] ?? [];
        $source = $data['source'] ?? 'manual';
        $userId = $user?->id ?? 0;

        // 按 user_id 建文件夹存
        $relativePath = sprintf(
            'feedback/%d/%s_%s.json',
            $userId,
            date('Ymd_His'),
            Str::random(6)
        );

        try {
            Storage::disk('local')->put(
                $relativePath,
                json_encode([
                    'received_at' => now()->toIso8601String(),
                    'user_id' => $userId,
                    'username' => $user?->username,
                    'source' => $source,
                    'flow_name' => $data['flow_name'] ?? null,
                    'error' => $data['error'] ?? null,
                    'note' => $data['note'] ?? null,
                    'template' => $template,
                ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
            );
        } catch (\Throwable $e) {
            \Log::error('Feedback file save failed: ' . $e->getMessage());
            $relativePath = null;
        }

        // 统计 step 数量
        $stepCount = 0;
        if (isset($template['steps']) && is_array($template['steps'])) {
            $stepCount = count($template['steps']);
        } elseif (isset($template['dsl']['actions']) && is_array($template['dsl']['actions'])) {
            $stepCount = count($template['dsl']['actions']);
        }

        $feedback = FeedbackLog::create([
            'user_id' => $userId ?: null,
            'category' => $source === 'auto_error' ? 'auto_error' : 'manual',
            'flow_name' => $data['flow_name'] ?? null,
            'source' => $source,
            'content' => $data['note'] ?? '(无补充说明)',
            'error_message' => $data['error'] ?? null,
            'template_path' => $relativePath,
            'meta' => [
                'step_count' => $stepCount,
                'flow_meta' => $template['meta'] ?? null,
            ],
            'status' => 'open',
        ]);

        // 反馈奖励：自动错误反馈 → 给用户加 1 次免费生成额度
        // 三重防刷：
        //   - 24 小时内最多奖励 3 次
        //   - 单用户总可用次数（免费 + 付费）不超过 30 封顶
        //   - 真实付费的用户不受 30 限制（通过另一个字段标记，未来扩展）
        $bonus = 0;
        $bonus_reason = '';
        $MAX_TOTAL = 30;

        if ($user && in_array($source, ['auto_error', 'manual'], true)) {
            try {
                $todayCount = \App\Models\FeedbackLog::where('user_id', $user->id)
                    ->where('created_at', '>=', now()->subHours(24))
                    ->count();

                if ($todayCount > 3) {
                    $bonus_reason = '今日反馈奖励已达上限（3 次/24h）';
                } else {
                    $user->refresh();
                    $totalAvailable = (int) $user->free_generations + (int) $user->paid_generations;
                    if ($totalAvailable >= $MAX_TOTAL) {
                        $bonus_reason = "免费总额度已达上限（{$MAX_TOTAL} 次），如需更多请联系客服购买";
                    } else {
                        $user->increment('paid_generations', 1);
                        $bonus = 1;
                    }
                }
            } catch (\Throwable $e) {
                // 奖励失败不影响反馈本身
            }
        }

        return $this->ok([
            'ok' => true,
            'success' => true,
            'feedback_id' => $feedback->id,
            'stored' => $relativePath !== null,
            'bonus_generations' => $bonus,
            'bonus_reason' => $bonus_reason,
            'message' => $bonus > 0
                ? '感谢反馈！已奖励 1 次试用机会。我们会尽快处理，请稍后再试或先忙别的事。'
                : ($bonus_reason ?: '感谢反馈！我们会尽快处理。'),
        ]);
    }
}
