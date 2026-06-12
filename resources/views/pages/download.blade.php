@extends('layouts.app')

@section('title', '免费下载 - 好办法浏览器自动化')
@section('page', 'download')

@section('content')

<section class="download-hero">
    <div class="hero-badge">免费试用版</div>
    <h1>立即下载体验</h1>
    <p>新用户赠送 <strong>20 次免费</strong> AI 脚本生成<br>无需注册，下载即用</p>

    @php
        // 下载文件名（中文需要 URL encode 才能让 COS 正确响应）
        $dlFileName = '好办法自动化_v2.0_BETA.rar';
        $dlUrl = sprintf(
            'https://%s.cos.%s.myqcloud.com/downloads/%s',
            env('COS_BUCKET', 'likailong-1349611745'),
            env('COS_REGION', 'ap-guangzhou'),
            rawurlencode($dlFileName)
        );
        $snapFileName = '智能截图软件_V1.0.zip';
        $cosBase = rtrim((string) env('COS_CDN_URL', ''), '/');
        if ($cosBase !== '') {
            $snapDlUrl = $cosBase.'/downloads/'.rawurlencode($snapFileName);
        } else {
            $snapDlUrl = sprintf(
                'https://%s.cos.%s.myqcloud.com/downloads/%s',
                env('COS_BUCKET', 'likailong-1349611745'),
                env('COS_REGION', 'ap-guangzhou'),
                rawurlencode($snapFileName)
            );
        }
        $snapDlUrl = env('SNAP_SAVER_DOWNLOAD_URL', $snapDlUrl);
    @endphp

    <div class="dl-card snap-download-card" id="snap-saver">
        <div class="dl-card-head">
            <div class="dl-ico">▣</div>
            <div class="dl-info">
                <div class="dl-name">智能截图软件 V1.0</div>
                <div class="dl-meta">Windows 10/11 64位 · 无需注册 · 默认 50 张图片处理额度 · 支持多种图片修复</div>
            </div>
        </div>
        <a class="btn btn-dl" href="{{ $snapDlUrl }}" download="{{ $snapFileName }}">
            下载智能截图软件 V1.0
        </a>
        <div class="dl-tips">
            <span>按住 Ctrl 拖动框选</span>
            <span>主图 / 详情自动切换</span>
            <span>自动打开下一条链接</span>
            <span>AI 去水印 / 去贴纸</span>
            <span>营销广告清爽化</span>
            <span>软件编号充值</span>
        </div>
    </div>

    <div class="dl-card">
        <div class="dl-card-head">
            <div class="dl-ico">📦</div>
            <div class="dl-info">
                <div class="dl-name">好办法浏览器自动化 v2.0 BETA</div>
                <div class="dl-meta">Windows 10/11 64位 · 含浏览器组件 · 约 162MB</div>
            </div>
        </div>
        <a class="btn btn-dl" href="{{ $dlUrl }}" id="dlBtn" download="{{ $dlFileName }}">
            ⬇  立即下载（RAR 压缩包）
        </a>
        <div class="dl-tips">
            <span>🛡️ 病毒扫描已通过</span>
            <span>🔒 仅本地运行不上传数据</span>
            <span>🎁 含 20 次免费试用</span>
            <span>🆕 v2.0 BETA：新增滚动录制、文件夹自动上传、阿里全家桶</span>
        </div>
    </div>

    <div class="dl-sys">
        <h3>系统要求</h3>
        <ul>
            <li>✅ Windows 10 / 11 64位（推荐 Win 11）</li>
            <li>✅ 内存 4GB 以上</li>
            <li>✅ 磁盘空间 500MB 以上</li>
            <li>✅ 能访问互联网（用于 AI 脚本生成）</li>
        </ul>
    </div>
</section>

<section class="dl-steps">
    <h2>3 步开始使用</h2>
    <div class="step-grid">
        <div class="step">
            <div class="step-num">1</div>
            <h3>下载并解压</h3>
            <p>下载 RAR 文件后，右键解压到任意目录（推荐 D盘 / E盘）</p>
        </div>
        <div class="step">
            <div class="step-num">2</div>
            <h3>双击运行</h3>
            <p>双击「好办法自动化.exe」启动软件，首次会自动下载浏览器组件（约200MB）</p>
        </div>
        <div class="step">
            <div class="step-num">3</div>
            <h3>开始录制</h3>
            <p>输入要自动化的网址 → 点开始录制 → 在浏览器正常操作 → 完成 → 整理 → AI 生成脚本</p>
        </div>
    </div>
</section>

<section class="dl-faq">
    <h2>常见问题</h2>
    <div class="faq-list">
        <div class="faq-item">
            <h3>解压时杀毒软件报警怎么办？</h3>
            <p>由于本软件未做代码签名，部分杀毒软件会误报。本软件开源、本地运行、不上传任何数据。可以加入信任名单后继续使用。如不放心可联系客服微信确认。</p>
        </div>
        <div class="faq-item">
            <h3>下载速度慢？</h3>
            <p>服务器在国内，正常下载速度 1-10MB/s。如果异常缓慢，可联系客服微信获取百度网盘链接。</p>
        </div>
        <div class="faq-item">
            <h3>免费次数用完之后？</h3>
            <p>当前提供 <strong>20 次免费试用</strong>。如需增加次数，请加客服微信 <strong>18033086531</strong>（备注：自动化软件用户）与作者沟通。</p>
        </div>
        <div class="faq-item">
            <h3>支持 Mac / Linux 吗？</h3>
            <p>当前仅支持 Windows 10/11 64位。Mac / Linux 版本计划中，预计 2026 年 Q3 推出。</p>
        </div>
        <div class="faq-item">
            <h3>遇到问题怎么反馈？</h3>
            <p>软件出错时会自动弹出反馈窗口，点击「发送给作者」即可一键上传错误信息（自动脱敏密码字段）。我们会尽快回复并通过经验库更新解决问题。</p>
        </div>
    </div>
</section>

<section class="dl-contact">
    <h2>需要帮助？</h2>
    <p>添加微信好友，备注「自动化软件用户」，10 分钟内回复</p>
    <div class="contact-card">
        <div class="contact-row"><span>客服微信</span><strong>18033086531</strong></div>
        <div class="contact-row"><span>邮箱</span><strong>likailongliyanni@proton.me</strong></div>
    </div>
</section>

@endsection
