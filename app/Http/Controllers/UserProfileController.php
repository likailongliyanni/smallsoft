<?php

namespace App\Http\Controllers;

use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Validation\ValidationException;

class UserProfileController extends Controller
{
    private const MAX_NICKNAME_EDITS = 3;

    /** GET /api/me/profile */
    public function show(Request $request, TokenService $tokens): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录');

        return $this->ok([
            'nickname' => $user->nickname,
            'nickname_edit_count' => (int) $user->nickname_edit_count,
            'nickname_remaining_edits' => max(0, self::MAX_NICKNAME_EDITS - (int) $user->nickname_edit_count),
            'nickname_max_edits' => self::MAX_NICKNAME_EDITS,
            'nickname_locked' => (int) $user->nickname_edit_count >= self::MAX_NICKNAME_EDITS,
        ]);
    }

    /** POST /api/me/nickname */
    public function updateNickname(Request $request, TokenService $tokens): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录');

        $count = (int) $user->nickname_edit_count;
        if ($count >= self::MAX_NICKNAME_EDITS) {
            throw ValidationException::withMessages([
                'nickname' => '昵称已锁定（已修改 '.self::MAX_NICKNAME_EDITS.' 次），无法再改。',
            ]);
        }

        $data = $request->validate([
            'nickname' => ['required', 'string', 'min:1', 'max:40'],
        ]);

        $newNick = trim($data['nickname']);
        if ($newNick === $user->nickname) {
            // 没变化不计次
            return $this->ok([
                'nickname' => $user->nickname,
                'nickname_edit_count' => $count,
                'nickname_remaining_edits' => self::MAX_NICKNAME_EDITS - $count,
                'message' => '昵称未变化，不消耗修改次数',
            ]);
        }

        $user->nickname = $newNick;
        $user->nickname_edit_count = $count + 1;
        $user->save();

        $remaining = self::MAX_NICKNAME_EDITS - $user->nickname_edit_count;
        return $this->ok([
            'nickname' => $user->nickname,
            'nickname_edit_count' => $user->nickname_edit_count,
            'nickname_remaining_edits' => $remaining,
            'nickname_locked' => $remaining <= 0,
            'message' => $remaining > 0
                ? "修改成功，剩余 {$remaining} 次"
                : '修改成功，昵称已永久锁定',
        ]);
    }
}
