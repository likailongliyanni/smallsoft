@extends('layouts.app')

@section('title', '账号中心 - 好办法浏览器自动化')
@section('page', 'account')

@section('content')
<section class="account-hero">
    <div>
        <p class="eyebrow">账号中心</p>
        <h1>欢迎使用好办法浏览器自动化</h1>
        <p>这里提供软件下载入口、账号额度和联系方式。自动化流程录制与运行将在桌面软件里完成。</p>
    </div>
    <button id="accountLogoutBtn" class="button" type="button">退出登录</button>
</section>

<section class="account-grid">
    <div class="panel account-card account-status-card">
        <div class="card-title-row">
            <div>
                <p class="eyebrow">我的账号</p>
                <h2>账号与额度</h2>
            </div>
            <span class="pill">已登录</span>
        </div>
        <div id="accountBox" class="account-summary">正在读取账号信息...</div>
    </div>

    <div class="panel account-card download-card">
        <p class="eyebrow">软件下载</p>
        <h2>浏览器自动化工具</h2>
        <p>安装桌面软件后，在软件里登录账号，录制网页步骤并提交生成自动化脚本。</p>
        <div class="download-box">
            <div>
                <strong>Windows 版本</strong>
                <span>模拟下载地址，正式发布时替换为真实安装包。</span>
            </div>
            <a class="button primary" href="/downloads/webauto-setup.exe">下载软件</a>
        </div>
        <p class="small-note">如果下载链接暂时不可用，请先联系我获取测试版。</p>
    </div>

    <div class="panel account-card contact-card">
        <p class="eyebrow">联系支持</p>
        <h2>需要帮助可以直接联系</h2>
        <div class="contact-list">
            <a href="tel:18033086531">
                <span>微信</span>
                <strong>18033086531</strong>
            </a>
            <a href="tel:18092019659">
                <span>电话</span>
                <strong>18092019659</strong>
            </a>
            <a href="mailto:likailongliyanni@proton.me">
                <span>邮箱</span>
                <strong>likailongliyanni@proton.me</strong>
            </a>
        </div>
    </div>

    <div class="panel account-card guide-card">
        <p class="eyebrow">使用顺序</p>
        <h2>下一步怎么做</h2>
        <ol class="plain-steps">
            <li>下载并安装 Windows 桌面软件。</li>
            <li>在软件里登录当前账号。</li>
            <li>打开目标网站，按软件提示登记网页操作。</li>
            <li>流程完成后提交生成自动化脚本。</li>
        </ol>
    </div>
</section>
@endsection
