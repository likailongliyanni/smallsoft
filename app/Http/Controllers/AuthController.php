<?php

namespace App\Http\Controllers;

use App\Models\User;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;
use Illuminate\Validation\ValidationException;

class AuthController extends Controller
{
    public function register(Request $request, TokenService $tokens): array
    {
        $request->merge([
            'username' => trim((string) $request->input('username', '')),
        ]);

        $data = $request->validate([
            'username' => ['required', 'string', 'min:2', 'max:80', 'regex:/^[\p{L}\p{N}_.@\-]+$/u', 'unique:users,username'],
            'password' => ['required', 'string', 'min:6', 'max:120'],
            'name' => ['nullable', 'string', 'max:80'],
            'email' => ['nullable', 'email', 'max:120'],
            'mobile' => ['nullable', 'string', 'max:40'],
        ], [
            'username.required' => '请填写用户名。',
            'username.min' => '用户名至少 2 个字符。',
            'username.max' => '用户名最多 80 个字符。',
            'username.regex' => '用户名只能包含中文、英文、数字、下划线、横线、点号或 @。',
            'username.unique' => '这个用户名已经被注册，请换一个。',
            'password.required' => '请填写密码。',
            'password.min' => '密码至少 6 位。',
            'password.max' => '密码最多 120 位。',
        ]);

        $user = User::create([
            'username' => $data['username'],
            'password' => Hash::make($data['password']),
            'name' => $data['name'] ?? $data['username'],
            'email' => $data['email'] ?? null,
            'mobile' => $data['mobile'] ?? null,
            'role' => 'user',
            'status' => 'active',
            'free_generations' => config('platform.free_generations'),
            'paid_generations' => 0,
        ]);

        return $this->ok([
            'token' => $tokens->createUserToken($user),
            'user' => $this->publicUser($user),
        ]);
    }

    public function login(Request $request, TokenService $tokens): array
    {
        $request->merge([
            'username' => trim((string) $request->input('username', '')),
        ]);

        $data = $request->validate([
            'username' => ['required', 'string', 'max:80'],
            'password' => ['required', 'string', 'max:120'],
        ], [
            'username.required' => '请填写用户名。',
            'password.required' => '请填写密码。',
        ]);

        $user = User::where('username', $data['username'])->first();
        if (! $user || ! Hash::check($data['password'], $user->password)) {
            throw ValidationException::withMessages(['username' => '账号或密码不正确']);
        }

        if ($user->status !== 'active') {
            throw ValidationException::withMessages(['username' => '账号已被禁用']);
        }

        $user->update(['last_login_at' => now()]);

        return $this->ok([
            'token' => $tokens->createUserToken($user),
            'user' => $this->publicUser($user->fresh()),
        ]);
    }

    public function me(Request $request, TokenService $tokens): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录');

        return $this->ok(['user' => $this->publicUser($user)]);
    }

    public function usage(Request $request, TokenService $tokens): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录');

        return $this->ok([
            'free_generations' => $user->free_generations,
            'paid_generations' => $user->paid_generations,
            'available_generations' => $user->availableGenerations(),
        ]);
    }

    private function publicUser(User $user): array
    {
        return [
            'id' => $user->id,
            'username' => $user->username,
            'name' => $user->name,
            'email' => $user->email,
            'mobile' => $user->mobile,
            'role' => $user->role,
            'status' => $user->status,
            'free_generations' => $user->free_generations,
            'paid_generations' => $user->paid_generations,
            'available_generations' => $user->availableGenerations(),
        ];
    }
}
