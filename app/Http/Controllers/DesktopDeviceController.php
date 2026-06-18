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
    /** 各软件中文名（用于 users.name 展示）。 */
    private const SOFTWARE_NAMES = [
        'pic' => '截图/图片软件',
        'auto' => '自动化软件',
    ];

    public function register(Request $request, TokenService $tokens): array
    {
        $data = $request->validate([
            'software_id' => ['required', 'string', 'max:60', 'regex:/^[A-Za-z0-9:_-]{8,60}$/'],
            'legacy_id' => ['nullable', 'string', 'max:60', 'regex:/^[A-Za-z0-9:_-]{8,60}$/'],
            'app' => ['nullable', 'string', 'max:40'],
            'version' => ['nullable', 'string', 'max:20'],
        ]);

        $code = $this->softwareCode($data['app'] ?? '');
        // username = 设备编号 + 软件代码，使不同软件即便编号相同也分开管理
        $username = $this->normalizeSoftwareId($data['software_id']).'-'.$code;
        $defaultQuota = $this->defaultQuota($code);
        $name = (self::SOFTWARE_NAMES[$code] ?? '软件').' '.$username;
        $legacyId = trim((string) ($data['legacy_id'] ?? ''));

        $user = DB::transaction(function () use ($username, $code, $defaultQuota, $name, $legacyId): User {
            $existing = User::where('username', $username)->lockForUpdate()->first();
            if ($existing) {
                $update = ['last_login_at' => now()];
                if (! $existing->software_code) {
                    $update['software_code'] = $code;
                }
                $existing->update($update);

                return $existing->fresh();
            }

            // 老编号迁移：新编号首次登记、但旧编号已有账户 → 把旧账户改名到新编号，
            // 额度/付费/记录全部无缝保留。迁移后旧编号不再存在，配置即便被拷到别的电脑也不会重复迁移。
            if ($legacyId !== '') {
                $legacyUsername = $this->normalizeSoftwareId($legacyId).'-'.$code;
                if ($legacyUsername !== $username) {
                    $old = User::where('username', $legacyUsername)->lockForUpdate()->first();
                    if ($old) {
                        $old->update([
                            'username' => $username,
                            'software_code' => $code,
                            'last_login_at' => now(),
                        ]);

                        return $old->fresh();
                    }
                }
            }

            $user = User::create([
                'username' => $username,
                'software_code' => $code,
                'name' => $name,
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
                'note' => ($name).' 首次登记默认额度',
            ]);

            return $user;
        });

        abort_if($user->status !== 'active', 403, '该软件编号已被禁用，请联系客服。');

        return $this->ok([
            'token' => $tokens->createUserToken($user),
            'software_id' => $user->username,
            'software_code' => $user->software_code,
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
            'software_code' => $user->software_code,
            'quota' => [
                'free' => (int) $user->free_generations,
                'paid' => (int) $user->paid_generations,
                'available' => $user->availableGenerations(),
            ],
        ]);
    }

    /** 从客户端上报的 app 标识推断软件代码（不改客户端，沿用其已在传的 app 字段）。 */
    private function softwareCode(string $app): string
    {
        $a = strtolower(trim($app));
        if ($a === '') {
            return 'pic';
        }
        if (str_contains($a, 'auto') || str_contains($a, 'web') || str_contains($a, '自动化')) {
            return 'auto';
        }
        if (str_contains($a, 'snap') || str_contains($a, 'pic') || str_contains($a, 'image')
            || str_contains($a, 'shot') || str_contains($a, '截图') || str_contains($a, '图片')) {
            return 'pic';
        }

        return 'pic';
    }

    private function defaultQuota(string $code): int
    {
        return match ($code) {
            'auto' => (int) config('platform.auto_default_quota', config('platform.snap_saver_default_quota', 50)),
            default => (int) config('platform.snap_saver_default_quota', 50),
        };
    }

    /** 设备编号归一化：十六进制取前 12 位格式化成 MAC 样式；其它形式原样大写保留。 */
    private function normalizeSoftwareId(string $value): string
    {
        $raw = strtoupper(trim($value));
        $hex = preg_replace('/[^A-F0-9]/', '', $raw) ?? '';
        if (strlen($hex) >= 12 && strlen($hex) === strlen(preg_replace('/[^A-F0-9-]/', '', $raw))) {
            // 纯十六进制（含分隔符）的编号 → 取前 12 位做 MAC 样式
            return implode('-', str_split(substr($hex, 0, 12), 2));
        }

        return $raw;
    }
}
