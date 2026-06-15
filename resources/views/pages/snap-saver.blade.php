@extends('layouts.app')

@section('title', '智能截图软件 V1.0 - 好办法自动化')
@section('page', 'snap-saver')

@section('content')

@php
    $snapFileName = '智能截图软件_V1.0.zip';
    $cosBase = rtrim((string) env('COS_CDN_URL', ''), '/');
    if ($cosBase !== '') {
        $snapDownloadUrl = $cosBase.'/downloads/'.rawurlencode($snapFileName);
    } else {
        $snapDownloadUrl = sprintf(
            'https://%s.cos.%s.myqcloud.com/downloads/%s',
            env('COS_BUCKET', 'likailong-1349611745'),
            env('COS_REGION', 'ap-guangzhou'),
            rawurlencode($snapFileName)
        );
    }
    $snapDownloadUrl = env('SNAP_SAVER_DOWNLOAD_URL', $snapDownloadUrl);
@endphp

<section class="snap-hero">
    <div class="snap-hero-copy">
        <div class="hero-badge">智能截图软件 V1.0</div>
        <h1>打开链接，框选图片，松手自动保存</h1>
        <p>为商品采图、主图/详情归档、AI 智能筛选和批量图片修复做的 Windows 专用工具。只保留 Ctrl + 鼠标拖动这一种截图方式，流程更短，也更稳定。</p>
        <div class="hero-actions">
            <a class="btn" href="{{ $snapDownloadUrl }}" download="{{ $snapFileName }}">下载 V1.0</a>
            <a class="btn btn-outline" href="#snap-workflow">查看流程</a>
        </div>
        <div class="snap-download-line">
            下载地址：<code>{{ rawurldecode($snapDownloadUrl) }}</code>
        </div>
    </div>
    <div class="snap-hero-media">
        <img src="/assets/snap-saver-hero.png" alt="智能截图软件 V1.0 工作流示意图">
    </div>
</section>

<section id="features" class="snap-section">
    <h2>适合什么场景</h2>
    <div class="snap-grid">
        <div class="snap-card">
            <h3>商品图片采集</h3>
            <p>导入名称和链接，软件按行打开网页。你只需要在浏览器里框选需要的图片区域，松开鼠标自动落盘。</p>
        </div>
        <div class="snap-card">
            <h3>主图 / 详情自动切换</h3>
            <p>先设置每个商品要几张主图、几张详情。主图够数后自动切到详情，详情够数后自动下一行。</p>
        </div>
        <div class="snap-card">
            <h3>AI 智能修复</h3>
            <p>全部截完后先选择修复类型：去除水印、去除文字贴纸、去除营销广告、图片清爽化或白底上图。弹出缩略图后人工勾选，再批量处理。</p>
        </div>
    </div>
</section>

<section id="snap-workflow" class="snap-section snap-flow">
    <h2>使用流程</h2>
    <div class="snap-steps">
        <div><strong>1</strong><span>导入 Excel / CSV / TXT：A 列名称，B 列链接。</span></div>
        <div><strong>2</strong><span>点开始截图，软件自动打开当前行网页。</span></div>
        <div><strong>3</strong><span>按住 Ctrl，鼠标左键拖动框选图片区域，松开自动保存。</span></div>
        <div><strong>4</strong><span>截够主图和详情后，软件自动打开下一条链接。</span></div>
        <div><strong>5</strong><span>选择修复类型，点击 AI 智能修复，确认需要处理的图片后批量修复。</span></div>
    </div>
</section>

<section class="snap-section">
    <h2>保留的实用功能</h2>
    <div class="snap-feature-list">
        <span>下一行</span>
        <span>复制上一行</span>
        <span>显示主程序</span>
        <span>重开当前链接</span>
        <span>主图 / 详情手动切换</span>
        <span>AI 去水印 / 去贴纸</span>
        <span>营销广告清爽化 / 白底上图</span>
    </div>
</section>

<section class="snap-download-panel">
    <div>
        <h2>下载智能截图软件 V1.0</h2>
        <p>Windows 10/11 64 位可用。下载 zip 后解压，双击里面的 exe 运行。软件会自动显示本机 MAC 生成的软件编号，新编号默认赠送 50 张图片处理额度。任意修复类型成功处理 1 张扣 1 张，充值时把编号发给客服即可。</p>
        <p class="snap-file-note">COS 上传文件名建议保持：<code>{{ $snapFileName }}</code></p>
    </div>
    <a class="btn" href="{{ $snapDownloadUrl }}" download="{{ $snapFileName }}">立即下载</a>
</section>

@endsection
