@extends('layouts.app')

@section('title', '登录 - 好办法浏览器自动化')
@section('page', 'login')

@section('content')
<section class="page-title compact">
    <p class="eyebrow">统一登录</p>
    <h1>登录后进入对应工作区</h1>
    <p>普通用户登录后进入免费体验，管理员账号登录后进入管理后台。</p>
</section>

<section class="workspace">
    <div class="panel narrow">
        <h2>账号登录</h2>
        <form id="unifiedLoginForm" class="form">
            <label>账号<input name="username" autocomplete="username" required></label>
            <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
            <button class="button primary" type="submit">登录</button>
        </form>
        <div class="login-links">
            <a href="/console">没有账号？进入免费体验注册</a>
        </div>
        <pre id="unifiedLoginResult" class="result-box"></pre>
    </div>
</section>
@endsection
