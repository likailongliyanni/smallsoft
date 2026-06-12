<?php

namespace App\Http\Controllers;

use App\Models\QuotaLog;
use App\Models\User;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Str;

class DesktopDeviceController extends Controller
{
    public function register(Request $request, TokenService $tokens): array
    {
        $data = $request->validate([
            'software_id' => ['required', 'string', 'max:40', 'regex:/^[A-Fa-f0-9:-]{12,40}$/'],
            'app' => ['nullable', 'string', 'max:40'],
            'version' => ['nullable', 'string', 'max:20'],
        ]);

        $softwareId = $this->normalizeSoftwareId($data['software_id']);
        $defaultQuota = (int) config('platform.snap_saver_default_quota', 50);

        $user = DB::transaction(function () use ($softwareId, $defaultQuota): User {
            $existing = User::where('username', $softwareId)->lockForUpdate()->first();
            if ($existing) {
                $existing->update(['last_login_at' => now()]);
                return $existing->fresh();
            }

            $user = User::create([
                'username' => $softwareId,
                'name' => '智能截图软件 '.$softwareId,
                'password' => Hash::make(Str::random(48)),
                'role' => 'user',
                'status' => 'active',
                'free_generations' => $defaultQuota,
                'paid_generations' => 0,
                'last_login_at' => now(),
            ]);

            QuotaLog::create([
                'user_id' => $user->id,
                'change_value' => $defaultQuota,
                'source' => 'desktop_device',
                'note' => '智能截图软件首次登记默认图片处理额度',
            ]);

            return $user;
        });

        abort_if($user->status !== 'active', 403, '该软件编号已被禁用，请联系客服。');

        return $this->ok([
            'token' => $tokens->createUserToken($user),
            'software_id' => $softwareId,
            'quota' => [
                'free' => (int) $user->free_generations,
                'paid' => (int) $user->paid_generations,
                'available' => $user->availableGenerations(),
            ],
        ]);
    }

    public function status(Request $request, TokenService $tokens): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登记软件编号');

        return $this->ok([
            'software_id' => $user->username,
            'quota' => [
                'free' => (int) $user->free_generations,
                'paid' => (int) $user->paid_generations,
                'available' => $user->availableGenerations(),
            ],
        ]);
    }

    private function normalizeSoftwareId(string $value): string
    {
        $hex = strtoupper(preg_replace('/[^A-Fa-f0-9]/', '', $value) ?? '');
        if (strlen($hex) >= 12) {
            $hex = substr($hex, 0, 12);
            return implode('-', str_split($hex, 2));
        }

        return strtoupper($value);
    }
}
