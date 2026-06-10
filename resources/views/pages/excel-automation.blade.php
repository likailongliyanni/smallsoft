@extends('layouts.app')

@section('title', 'EXCEL自动化')
@section('page', 'excel-automation')
@section('hide-nav', true)

@section('content')
<section class="excel-app">
    <header class="excel-topbar">
        <a class="excel-brand" href="/">
            <span class="excel-brand-icon">X</span>
            <span>
                <strong>EXCEL自动化</strong>
                <small>让 Excel 处理更简单高效</small>
            </span>
        </a>
        <div class="excel-top-actions">
            <button class="excel-icon-btn" type="button" title="帮助">?</button>
            <button class="excel-text-btn" type="button">历史记录</button>
            <span id="sheetUserBadge" class="excel-ai-badge">AI</span>
            <button id="sheetLogoutBtn" class="excel-text-btn hidden" type="button">退出</button>
        </div>
    </header>

    <div class="excel-layout">
        <aside class="excel-sidebar">
            <div class="excel-nav-block">
                <span class="excel-nav-title">功能列表</span>
                <button class="excel-nav-item active" type="button">
                    <span class="excel-nav-icon">▧</span>
                    图片提取
                </button>
            </div>

            <div class="excel-nav-block">
                <span class="excel-nav-title">即将上线</span>
                <button class="excel-nav-item disabled" type="button" disabled>数据清洗</button>
                <button class="excel-nav-item disabled" type="button" disabled>智能分类</button>
                <button class="excel-nav-item disabled" type="button" disabled>批量翻译</button>
                <button class="excel-nav-item disabled" type="button" disabled>数据合并</button>
            </div>

            <div class="excel-nav-block">
                <span class="excel-nav-title">更多功能</span>
                <button class="excel-nav-item disabled" type="button" disabled>格式转换</button>
                <button class="excel-nav-item disabled" type="button" disabled>数据校验</button>
                <button class="excel-nav-item disabled" type="button" disabled>公式处理</button>
                <button class="excel-nav-item disabled" type="button" disabled>拆分工作表</button>
            </div>

            <div class="excel-login-box" id="sheetLoginPanel">
                <h2>账号</h2>
                <form id="sheetLoginForm" class="excel-login-form">
                    <input name="username" autocomplete="username" placeholder="用户名 / 手机号">
                    <input name="password" type="password" autocomplete="current-password" minlength="6" placeholder="密码">
                    <div class="excel-login-actions">
                        <button class="excel-mini-btn primary" type="submit">登录</button>
                        <button class="excel-mini-btn" id="sheetRegisterBtn" type="button">注册</button>
                    </div>
                </form>
                <p id="sheetLoginResult" class="excel-inline-result"></p>
            </div>
        </aside>

        <form id="sheetExportForm" class="excel-work-area">
            <main class="excel-main">
                <div class="excel-page-head">
                    <div>
                        <h1>图片提取</h1>
                        <p>从 Excel 文件中批量提取图片，并按规则保存到本地。</p>
                    </div>
                    <label class="excel-upload-btn">
                        <input id="sheetFile" name="file" type="file" accept=".xlsx" required>
                        选择文件
                    </label>
                </div>

                <div class="excel-file-row">
                    <div class="excel-file-chip">
                        <span class="excel-file-icon">X</span>
                        <span>
                            <strong id="sheetFileName">请选择一个 .xlsx 文件</strong>
                            <small id="sheetFileSize">文件只在浏览器本地读取，不上传服务器</small>
                        </span>
                    </div>
                    <div id="sheetResultMeta" class="excel-meta">等待处理</div>
                </div>

                <div id="sheetLocalPreview" class="excel-preview hidden">
                    <div class="excel-preview-toolbar">
                        <div id="sheetTabs" class="sheet-tabs"></div>
                        <div class="excel-preview-actions">
                            <span>本地预览</span>
                            <button class="excel-text-btn" type="button">全屏</button>
                        </div>
                    </div>
                    <div class="sheet-preview-layout">
                        <div class="sheet-grid-wrap">
                            <table id="sheetGridPreview"></table>
                        </div>
                        <div class="sheet-image-strip" id="sheetImagePreview"></div>
                    </div>
                </div>

                <p id="sheetExportResult" class="excel-status"></p>
            </main>

            <aside class="excel-settings">
                <div class="excel-settings-head">
                    <span class="excel-setting-icon">▧</span>
                    <div>
                        <h2>图片提取设置</h2>
                        <p>从表格中提取图片并保存到本地</p>
                    </div>
                </div>

                <div class="excel-setting-section">
                    <h3>提取范围</h3>
                    <label class="excel-radio">
                        <input type="radio" name="range_mode" checked>
                        <span>提取所有图片列</span>
                    </label>
                    <label class="excel-radio">
                        <input type="radio" name="range_mode" disabled>
                        <span>自定义列（后续开放）</span>
                    </label>
                </div>

                <div class="excel-setting-section">
                    <h3>图片提取要求</h3>
                    <textarea id="sheetInstruction" name="instruction" rows="7" required placeholder="例如：按69码创建文件夹，每个商品图片命名为 1.jpg、2.jpg、3.jpg；所有 sheet 都处理；裁掉白边，统一 800x800。"></textarea>
                </div>

                <div class="excel-setting-section">
                    <h3>保存设置</h3>
                    <label class="excel-select-label">
                        保存格式
                        <select name="format_mode">
                            <option>按要求自动判断</option>
                            <option>原格式</option>
                            <option>JPG</option>
                            <option>PNG</option>
                        </select>
                    </label>
                    <label class="excel-checkbox">
                        <input type="checkbox" checked disabled>
                        <span>按行创建子文件夹</span>
                    </label>
                </div>

                <div id="sheetWarnings" class="tool-warnings hidden"></div>
                <div id="sheetPlanBox" class="tool-code hidden"></div>

                <div class="tool-table-wrap hidden" id="sheetPreviewWrap">
                    <table>
                        <thead>
                            <tr>
                                <th>Sheet</th>
                                <th>行</th>
                                <th>序号</th>
                                <th>文件</th>
                            </tr>
                        </thead>
                        <tbody id="sheetPreviewBody"></tbody>
                    </table>
                </div>

                <button class="excel-primary-action" id="sheetExportBtn" type="submit">开始提取</button>
                <button id="sheetDownloadBtn" class="excel-secondary-action hidden" type="button">下载 ZIP</button>
                <button class="excel-secondary-action" id="sheetClearBtn" type="button">清空</button>

                <div class="excel-tip">
                    <strong>小贴士</strong>
                    <p>如果命名不符合预期，请写得更具体，例如“按69码创建文件夹，图片命名为 1.jpg、2.jpg”。</p>
                </div>
            </aside>
        </form>
    </div>
</section>

<script src="/assets/excel-automation-local.js?v={{ time() }}"></script>
@endsection
