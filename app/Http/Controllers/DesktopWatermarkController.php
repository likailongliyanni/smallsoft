<?php

namespace App\Http\Controllers;

use App\Models\QuotaLog;
use App\Models\User;
use App\Services\ImageDescribeService;
use App\Services\ProductParamsService;
use App\Services\TokenService;
use App\Services\WatermarkAiService;
use Illuminate\Support\Facades\DB;
use Illuminate\Http\Request;
use RuntimeException;
use Throwable;

class DesktopWatermarkController extends Controller
{
    public function detect(Request $request, TokenService $tokens, WatermarkAiService $service): array
    {
        @set_time_limit(120);

        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登记软件编号');

        $data = $request->validate([
            'image' => ['required', 'file', 'mimes:jpg,jpeg,png,webp', 'max:10240'],
            'mode' => ['nullable', 'string', 'in:watermark,text_sticker,marketing,clean,all'],
        ]);
        $mode = WatermarkAiService::normalizeMode($data['mode'] ?? null);

        try {
            return $this->ok($service->detect($request->file('image'), $mode));
        } catch (Throwable $e) {
            abort(422, $e->getMessage());
        }
    }

    public function remove(Request $request, TokenService $tokens, WatermarkAiService $service)
    {
        @set_time_limit(420);

        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登记软件编号');
        abort_if($user->availableGenerations() <= 0, 402, '图片处理额度不足，请把软件编号发给客服充值。');

        $data = $request->validate([
            'image' => ['required', 'file', 'mimes:jpg,jpeg,png,webp', 'max:10240'],
            'mode' => ['nullable', 'string', 'in:watermark,text_sticker,marketing,clean,all'],
        ]);
        $mode = WatermarkAiService::normalizeMode($data['mode'] ?? null);

        try {
            $bytes = $service->remove($request->file('image'), $mode);
            $remaining = $this->consumeImageQuota($user, $mode);

            return response($bytes, 200, [
                'Content-Type' => 'image/png',
                'Cache-Control' => 'no-store',
                'X-Remaining-Quota' => (string) $remaining,
            ]);
        } catch (Throwable $e) {
            abort(422, $e->getMessage());
        }
    }

    /**
     * 图片智能描述：截图 + 用户简介 → AI 生成详细中文说明（给 PDF 排版用）。
     *
     * 收费策略：config('platform.doc_describe_charge') 控制是否扣额度。
     * 默认 false（免费期）——不扣额度，但仍写一条 change_value=0 的 QuotaLog
     * 记录调用量；将来后台把开关打开即开始按 1 张/次扣费，前端代码无需改动。
     */
    public function describeImage(Request $request, TokenService $tokens, ImageDescribeService $service): array
    {
        @set_time_limit(150);

        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登记软件编号');

        $charge = (bool) config('platform.doc_describe_charge', false);
        if ($charge) {
            abort_if($user->availableGenerations() <= 0, 402, 'AI 描述额度不足，请把软件编号发给客服充值。');
        }

        $data = $request->validate([
            'image' => ['required', 'file', 'mimes:jpg,jpeg,png,webp', 'max:10240'],
            'hint' => ['nullable', 'string', 'max:200'],
            'style' => ['nullable', 'string', 'in:detail,brief,marketing'],
        ]);

        try {
            $result = $service->describe(
                $request->file('image'),
                (string) ($data['hint'] ?? ''),
                (string) ($data['style'] ?? 'detail'),
            );
            $remaining = $this->consumeDescribeQuota($user, $charge);

            return $this->ok([
                'description' => $result['description'],
                'charged' => $charge,
                'remaining' => $remaining,
            ]);
        } catch (Throwable $e) {
            abort(422, $e->getMessage());
        }
    }

    /** 一句话商品介绍 → 可编辑的商品参数表。 */
    public function generateParams(Request $request, TokenService $tokens, ProductParamsService $service): array
    {
        @set_time_limit(100);

        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登记软件编号');

        $data = $request->validate([
            'text' => ['required', 'string', 'max:1000'],
        ]);

        try {
            return $this->ok($service->generate((string) $data['text']));
        } catch (Throwable $e) {
            abort(422, $e->getMessage());
        }
    }

    /** 描述功能扣费：免费期只记账不扣额度（change_value=0），收费期扣 1。 */
    private function consumeDescribeQuota(User $user, bool $charge): int
    {
        return DB::transaction(function () use ($user, $charge): int {
            $fresh = User::query()->lockForUpdate()->findOrFail($user->id);

            if ($charge) {
                if ($fresh->free_generations > 0) {
                    $fresh->decrement('free_generations');
                } elseif ($fresh->paid_generations > 0) {
                    $fresh->decrement('paid_generations');
                } else {
                    throw new RuntimeException('AI 描述额度不足，请把软件编号发给客服充值。');
                }
            }

            QuotaLog::create([
                'user_id' => $fresh->id,
                'change_value' => $charge ? -1 : 0,
                'source' => 'snap_saver_doc_describe',
                'note' => $charge ? '智能截图软件 AI 图片描述扣除 1 次额度' : '智能截图软件 AI 图片描述（免费期，仅记录）',
            ]);

            return $fresh->fresh()->availableGenerations();
        });
    }

    private function consumeImageQuota(User $user, string $mode): int
    {
        return DB::transaction(function () use ($user, $mode): int {
            $fresh = User::query()->lockForUpdate()->findOrFail($user->id);
            if ($fresh->free_generations > 0) {
                $fresh->decrement('free_generations');
            } elseif ($fresh->paid_generations > 0) {
                $fresh->decrement('paid_generations');
            } else {
                throw new RuntimeException('图片处理额度不足，请把软件编号发给客服充值。');
            }

            QuotaLog::create([
                'user_id' => $fresh->id,
                'change_value' => -1,
                'source' => 'snap_saver_image_repair',
                'note' => '智能截图软件'.$this->modeLabel($mode).'扣除 1 张图片额度',
            ]);

            return $fresh->fresh()->availableGenerations();
        });
    }

    private function modeLabel(string $mode): string
    {
        return match ($mode) {
            'text_sticker' => '去除文字贴纸',
            'marketing' => '去除营销广告',
            'clean' => '图片清爽化',
            'all' => '白底上图',
            default => '去除水印',
        };
    }
}
