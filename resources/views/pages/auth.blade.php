@extends('layouts.app')

@section('title', '注册 / 登录 - 好办法浏览器自动化')
@section('page', 'auth')

@section('content')
<section class="auth-page">
    <div class="panel auth-panel">
        <div class="tabs">
            <button class="tab active" data-auth-tab="login">登录</button>
            <button class="tab" data-auth-tab="register">注册</button>
        </div>

        <form id="authLoginForm" class="form">
            <label>账号<input name="username" autocomplete="username" required></label>
            <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
            <button class="button primary" type="submit">登录</button>
            <p class="form-note">管理员账号登录后进入后台；普通用户登录后进入账号中心。</p>
        </form>

        <form id="authRegisterForm" class="form hidden">
            <label>账号<input name="username" autocomplete="username" required></label>
            <label>密码<input name="password" type="password" autocomplete="new-password" required minlength="6"></label>
            <label>昵称<input name="name" autocomplete="name"></label>
            <button class="button primary" type="submit">注册账号</button>
            <p class="form-note">注册成功后自动登录。</p>
        </form>

        <pre id="authResult" class="result-box"></pre>
    </div>
</section>
@endsection
