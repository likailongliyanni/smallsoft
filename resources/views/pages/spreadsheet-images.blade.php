@extends('layouts.app')

@section('title', '表格图片另存整理助手')
@section('page', 'spreadsheet-images')
@section('hide-nav', true)

@section('content')
<section class="sheet-tool">
    <header class="tool-topbar">
        <a class="tool-brand" href="/">
            <span class="tool-mark">图</span>
            <span>表格图片另存整理</span>
        </a>
        <div class="tool-user">
            <span id="sheetUserBadge" class="tool-badge">未登录</span>
            <button id="sheetLogoutBtn" class="btn btn-outline btn-sm hidden" type="button">退出</button>
        </div>
    </header>

    <div class="tool-workspace">
        <aside class="tool-panel" id="sheetLoginPanel">
            <h2>账号</h2>
            <form id="sheetLoginForm" class="tool-form">
                <label>
                    <span>用户名</span>
                    <input name="username" autocomplete="username" placeholder="中文、手机号或邮箱均可" required>
                </label>
                <label>
                    <span>密码</span>
                    <input name="password" type="password" autocomplete="current-password" minlength="6" placeholder="至少 6 位" required>
                </label>
                <div class="tool-actions">
                    <button class="btn" type="submit">登录</button>
                    <button class="btn btn-outline" id="sheetRegisterBtn" type="button">注册并登录</button>
                </div>
            </form>
            <p class="tool-result" id="sheetLoginResult"></p>
        </aside>

        <section class="tool-panel tool-main">
            <div class="tool-panel-head">
                <div>
                    <h1>表格图片另存整理</h1>
                    <p>本地读取供应商 xlsx，预览后按你的命名和整理要求导出图片包。</p>
                </div>
                <span class="tool-pill">xlsx</span>
            </div>

            <form id="sheetExportForm" class="tool-form sheet-export-form">
                <label>
                    <span>表格文件</span>
                    <input id="sheetFile" name="file" type="file" accept=".xlsx" required>
                </label>
                <div id="sheetLocalPreview" class="sheet-local-preview hidden">
                    <div id="sheetTabs" class="sheet-tabs"></div>
                    <div class="sheet-preview-layout">
                        <div class="sheet-grid-wrap">
                            <table id="sheetGridPreview"></table>
                        </div>
                        <div class="sheet-image-strip" id="sheetImagePreview"></div>
                    </div>
                </div>
                <label>
                    <span>整理要求</span>
                    <textarea id="sheetInstruction" name="instruction" rows="6" required placeholder="例如：处理所有 sheet，把商品图提取出来，用货号+颜色命名；每个 sheet 单独一个文件夹；一行多图加 -1 -2；裁掉白边，统一 800x800，尽量清晰。"></textarea>
                </label>
                <div class="tool-actions">
                    <button class="btn" id="sheetExportBtn" type="submit">开始整理</button>
                    <button class="btn btn-outline" id="sheetClearBtn" type="button">清空</button>
                </div>
            </form>

            <p class="tool-result" id="sheetExportResult"></p>
        </section>

        <section class="tool-panel tool-output">
            <div class="tool-panel-head">
                <div>
                    <h2>结果</h2>
                    <p id="sheetResultMeta">等待处理</p>
                </div>
                <button id="sheetDownloadBtn" class="btn btn-sm hidden" type="button">下载 ZIP</button>
            </div>

            <div id="sheetPlanBox" class="tool-code hidden"></div>
            <div id="sheetWarnings" class="tool-warnings hidden"></div>
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
        </section>
    </div>
</section>

<script src="/assets/spreadsheet-images-local.js?v={{ time() }}"></script>
@endsection
