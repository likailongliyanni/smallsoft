@extends('layouts.app')

@section('title', '智能截图软件 V2.0.0 - 好办法自动化')
@section('page', 'snap-saver')

@section('content')

@php
    $snapVersion = 'V2.0.0';
    $snapFileName = '智能截图软件_V2.0.0_Setup.exe';
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
        <div class="hero-badge">智能截图软件 {{ $snapVersion }} · 大版本更新</div>
        <h1>商品采图、AI 修复、单图场景主图，一套工具完成</h1>
        <p>面向电商商品图片采集的 Windows 桌面软件。导入名称和链接后自动打开网页，按住 Ctrl 框选图片即可保存；后续可批量去水印、去贴纸、去营销广告、白底上图，并支持单张商品图生成 AI 场景主图。</p>
        <div class="hero-actions">
            <a class="btn" href="{{ $snapDownloadUrl }}" download="{{ $snapFileName }}">下载 {{ $snapVersion }} 安装包</a>
            <a class="btn btn-outline" href="#snap-workflow">查看流程</a>
        </div>
        <div class="snap-download-line">
            下载地址：<code>{{ rawurldecode($snapDownloadUrl) }}</code>
        </div>
    </div>
    <div class="snap-hero-media">
        <img src="/assets/snap-saver-hero.png" alt="智能截图软件 V2.0.0 工作流示意图">
    </div>
</section>

<section id="features" class="snap-section">
    <h2>V2.0.0 适合什么场景</h2>
    <div class="snap-grid">
        <div class="snap-card">
            <h3>商品图片采集</h3>
            <p>导入 Excel / CSV / TXT 的「名称 + 链接」，软件按行打开商品网页。你在网页上按住 Ctrl 拖框，松手后图片自动保存到对应商品目录。</p>
        </div>
        <div class="snap-card">
            <h3>主图 / 详情自动切换</h3>
            <p>先设置每个商品需要几张主图、几张详情。主图截够自动切详情，详情截够自动进入下一条链接，减少人工切目录和改文件名。</p>
        </div>
        <div class="snap-card">
            <h3>AI 图片修复</h3>
            <p>支持去除水印、文字贴纸、营销广告、图片清爽化、白底上图。先显示缩略图人工勾选，再批量处理，避免误扣不需要处理的图片。</p>
        </div>
        <div class="snap-card">
            <h3>单图 AI 场景主图</h3>
            <p>从已采集图片里只勾选 1 张干净商品图，即可生成电商场景主图、详情页头图、使用场景图或宣传海报。V2.0.0 暂停多图组合，重点优化单图效果和稳定性。</p>
        </div>
        <div class="snap-card">
            <h3>整理成文档</h3>
            <p>内置图文编辑器，可把采集结果整理成文档，支持导出 PDF / 长图，适合给客户、同事或运营人员快速核对。</p>
        </div>
        <div class="snap-card">
            <h3>安装包发布</h3>
            <p>新版改为 Windows 安装程序，用户电脑无需安装 Node.js、npm 或 Python。安装后直接运行，开始菜单和桌面快捷方式都可打开。</p>
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
        <div><strong>6</strong><span>需要做场景图时，只勾选 1 张商品图，点击 AI 场景主图，选择比例、用途、风格后生成。</span></div>
    </div>
</section>

<section class="snap-section">
    <h2>V2.0.0 功能清单</h2>
    <div class="snap-feature-list">
        <span>Windows 安装包</span>
        <span>无需安装 npm / Python</span>
        <span>Ctrl 拖框截图</span>
        <span>下一行</span>
        <span>复制上一行</span>
        <span>显示主程序</span>
        <span>重开当前链接</span>
        <span>主图 / 详情手动切换</span>
        <span>AI 去水印 / 去贴纸</span>
        <span>营销广告清爽化 / 白底上图</span>
        <span>单图 AI 场景主图</span>
        <span>详情页头图 / 使用场景图</span>
        <span>单图宣传海报</span>
        <span>本地文案 / 角标叠加</span>
        <span>导出 PDF / 长图</span>
    </div>
</section>

<section class="snap-download-panel">
    <div>
        <h2>下载智能截图软件 {{ $snapVersion }}</h2>
        <p>Windows 10/11 64 位可用。新版是安装程序，下载后双击安装即可，用户电脑不需要安装 npm、Node.js 或 Python。软件会自动读取本机 MAC 生成软件编号，新编号默认赠送图片处理额度；AI 修复或 AI 场景主图成功处理 1 张扣 1 张，充值时把编号发给客服即可。</p>
        <p>本版本属于大改版：Electron 新界面、内置 Python 后端、安装包发布、AI 修复流程升级、单图 AI 场景主图上线，并暂停不稳定的多图组合海报功能。</p>
        <p class="snap-file-note">COS 上传文件名建议保持：<code>{{ $snapFileName }}</code></p>
    </div>
    <a class="btn" href="{{ $snapDownloadUrl }}" download="{{ $snapFileName }}">立即下载</a>
</section>

@endsection
