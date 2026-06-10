<?php

namespace App\Services;

use App\Models\AdminToken;
use App\Models\User;
use App\Models\UserToken;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class TokenService
{
    public function createUserToken(User $user): string
    {
        $plain = Str::random(80);

        UserToken::create([
            'user_id' => $user->id,
            'token_hash' => hash('sha256', $plain),
            'expires_at' => now()->addDays(config('platform.user_token_days')),
        ]);

        return $plain;
    }

    public function createAdminToken(User $admin): string
    {
        $plain = Str::random(80);

        AdminToken::create([
            'user_id' => $admin->id,
            'token_hash' => hash('sha256', $plain),
            'expires_at' => now()->addDays(config('platform.admin_token_days')),
        ]);

        return $plain;
    }

    public function userFromRequest(Request $request): ?User
    {
        $token = $this->bearerToken($request);
        if (! $token) {
            return null;
        }

        $record = UserToken::with('user')
            ->where('token_hash', hash('sha256', $token))
            ->where(function ($query): void {
                $query->whereNull('expires_at')->orWhere('expires_at', '>', now());
            })
            ->first();

        if (! $record || ! $record->user || $record->user->status !== 'active') {
            return null;
        }

        return $record->user;
    }

    public function adminFromRequest(Request $request): ?User
    {
        $token = $this->bearerToken($request);
        if (! $token) {
            return null;
        }

        $record = AdminToken::with('user')
            ->where('token_hash', hash('sha256', $token))
            ->where(function ($query): void {
                $query->whereNull('expires_at')->orWhere('expires_at', '>', now());
            })
            ->first();

        if (! $record || ! $record->user || $record->user->role !== 'admin' || $record->user->status !== 'active') {
            return null;
        }

        return $record->user;
    }

    public function revokeAdminToken(Request $request): void
    {
        $token = $this->bearerToken($request);
        if (! $token) {
            return;
        }

        AdminToken::where('token_hash', hash('sha256', $token))->delete();
    }

    private function bearerToken(Request $request): ?string
    {
        $token = $request->bearerToken();
        return is_string($token) && $token !== '' ? $token : null;
    }
}
