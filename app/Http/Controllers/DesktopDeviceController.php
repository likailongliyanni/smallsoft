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
        'aidoc' => 'AI档案管理',
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

        // 截图软件强制最新版：新版编号是 12 位网卡 MAC，旧版发的是 20 位哈希编号。
        // 旧版登记一律拒绝并提示下载新版（旧软件作废）。其它软件（如自动化）不受此限制。
        $appText = strtolower(trim((string) ($data['app'] ?? '')));
        $isSnap = str_contains($appText, 'snap') || str_contains($appText, 'pic')
            || str_contains($appText, 'shot') || str_contains($appText, '截图');
        $rawHex = preg_replace('/[^A-Fa-f0-9]/', '', $data['software_id']) ?? '';
        abort_if($isSnap && strlen($rawHex) !== 12, 426, '截图软件版本过旧，请下载并使用最新版。');

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
        // AI 档案管理（app=ai-doc）：独立软件代码 + 独立页额度，不和截图软件共用账户。
        if (str_contains($a, 'aidoc') || str_contains($a, 'ai-doc') || str_contains($a, '档案')) {
            return 'aidoc';
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
            'auto' => (int) config('platform.auto_default_quota', config('platform.snap_saver_default_quota', 10)),
            'aidoc' => (int) config('platform.aidoc_default_quota', 50),
            default => (int) config('platform.snap_saver_default_quota', 10),
        };
    }

    /**
     * 设备编号归一化：含 ≥12 位十六进制的编号统一取前 12 位格式化成 XX-XX-XX-XX-XX-XX。
     * 旧版客户端的哈希编号、新版的真实 MAC 都按同一规则归一，与历史数据迁移后的 username
     * 保持一致——所以旧软件继续登记也能对上原账户，不受影响。
     */
    private function normalizeSoftwareId(string $value): string
    {
        $hex = strtoupper(preg_replace('/[^A-Fa-f0-9]/', '', $value) ?? '');
        if (strlen($hex) >= 12) {
            return implode('-', str_split(substr($hex, 0, 12), 2));
        }

        return strtoupper(trim($value));
    }
}
