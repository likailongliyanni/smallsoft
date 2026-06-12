<?php

namespace App\Http\Controllers;

use App\Models\QuotaLog;
use App\Models\User;
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
