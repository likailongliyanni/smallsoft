@extends('layouts.app')

@section('title', 'EXCEL自动化')
@section('page', 'excel-automation')
@section('hide-nav', true)

@section('content')
<section class="excel-app">
    <header class="excel-topbar">
        <div class="excel-topbar-left">
            <button id="sidebarToggleBtn" class="excel-icon-btn" type="button" title="收起 / 展开菜单">☰</button>
            <a class="excel-brand" href="/">
                <span class="excel-brand-icon">X</span>
                <span>
                    <strong>EXCEL自动化</strong>
                    <small>让 Excel 处理更简单高效</small>
                </span>
            </a>
        </div>
        <div class="excel-top-actions">
            <button id="excelHelpBtn" class="excel-icon-btn" type="button" title="使用说明">?</button>
            <a class="excel-recharge-btn" href="/#pricing" title="查看充值方式">充值额度</a>
            <span id="sheetUserBadge" class="excel-user-chip">未登录 · 本地模式</span>
            <button id="sheetLogoutBtn" class="excel-text-btn hidden" type="button">退出</button>
        </div>
    </header>

    <div class="excel-layout">
        <aside class="excel-sidebar">
            <div class="excel-nav-block">
                <span class="excel-nav-title">功能列表</span>
                <button class="excel-nav-item active" type="button" data-panel="image-extract">
                    <span class="excel-nav-icon">▧</span>
                    图片提取
                </button>
                <button class="excel-nav-item" type="button" data-panel="table-merge">
                    <span class="excel-nav-icon">⊞</span>
                    表格整理
                </button>
            </div>

            <div class="excel-nav-block">
                <span class="excel-nav-title">即将上线</span>
                <button class="excel-nav-item disabled" type="button" disabled>数据清洗</button>
                <button class="excel-nav-item disabled" type="button" disabled>智能分类</button>
                <button class="excel-nav-item disabled" type="button" disabled>批量翻译</button>
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

                <details class="excel-help" data-help>
                    <summary>使用说明</summary>
                    <ol>
                        <li>点「选择文件」打开一个 .xlsx 表格，文件只在浏览器本地读取，<strong>不会上传服务器</strong>。</li>
                        <li>在右侧「图片提取要求」里用自己的话描述怎么保存，例如：<em>按69码创建文件夹，每个商品图片命名为 1.jpg、2.jpg；裁掉白边，统一 800x800</em>。</li>
                        <li>点「开始提取」。登录后由 AI 把口语化要求转成精确规则（只发送表头和样例摘要）；未登录走本地规则。</li>
                        <li>在右侧核对文件名预览，没问题就点「下载 ZIP」，ZIP 内附带 manifest.csv 清单。</li>
                    </ol>
                    <p>提示：要求写得越具体效果越好；「保存格式」下拉可以强制输出 JPG 或 PNG。</p>
                </details>

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
                            <button id="sheetFullscreenBtn" class="excel-text-btn" type="button">全屏</button>
                        </div>
                    </div>
                    <div class="sheet-preview-layout">
                        <div class="sheet-grid-wrap">
                            <table id="sheetGridPreview"></table>
                        </div>
                        <div class="sheet-image-strip" id="sheetImagePreview"></div>
                    </div>
                </div>
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
                    <h3>图片提取要求</h3>
                    <textarea id="sheetInstruction" name="instruction" rows="7" required placeholder="例如：按69码创建文件夹，每个商品图片命名为 1.jpg、2.jpg、3.jpg；所有 sheet 都处理；裁掉白边，统一 800x800。"></textarea>
                </div>

                <div class="excel-setting-section">
                    <h3>保存设置</h3>
                    <label class="excel-select-label">
                        保存格式
                        <select id="sheetFormatMode" name="format_mode">
                            <option value="auto">按要求自动判断</option>
                            <option value="original">原格式</option>
                            <option value="jpg">JPG</option>
                            <option value="png">PNG</option>
                        </select>
                    </label>
                </div>

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

                <details id="sheetPlanDetails" class="excel-plan-details hidden">
                    <summary>查看执行规则（调试）</summary>
                    <div id="sheetPlanBox" class="tool-code"></div>
                </details>

                <p id="sheetExportResult" class="excel-status"></p>

                <button class="excel-primary-action" id="sheetExportBtn" type="submit">开始提取</button>
                <button id="sheetDownloadBtn" class="excel-secondary-action hidden" type="button">下载 ZIP</button>
                <button class="excel-secondary-action" id="sheetClearBtn" type="button">清空</button>

                <div class="excel-tip">
                    <strong>小贴士</strong>
                    <p>如果命名不符合预期，请写得更具体，例如“按69码创建文件夹，图片命名为 1.jpg、2.jpg”。</p>
                </div>
            </aside>
        </form>

        <div id="tableMergePanel" class="excel-work-area hidden">
            <main class="excel-main">
                <div class="excel-page-head">
                    <div>
                        <h1>表格整理</h1>
                        <p>上传多个原始表（可多 sheet），AI 把写法不一的字段归类，人工确认后合并成规范表。</p>
                    </div>
                    <div class="merge-upload-group">
                        <label class="excel-upload-btn">
                            <input id="mergeSourceFiles" type="file" accept=".xlsx" multiple>
                            选择原始表
                        </label>
                        <label class="excel-upload-btn">
                            <input id="mergeTemplateFile" type="file" accept=".xlsx">
                            模板表（可选）
                        </label>
                    </div>
                </div>

                <details class="excel-help" data-help>
                    <summary>使用说明</summary>
                    <ol>
                        <li>点「选择原始表」上传一个或多个 .xlsx（支持多个 sheet），文件只在浏览器本地读取，<strong>不会上传服务器</strong>。需要固定字段和顺序时再传一个「模板表」。</li>
                        <li>（可选）在右侧写整理要求，例如：<em>只要商品名称、69码、数量</em>，或者 <em>通过订单号把快递单号匹配到订单上，按模板整理</em>。</li>
                        <li>点「AI 规划合并」：AI 会判断是「堆叠合并」还是「按键匹配」（比如订单表+快递表按电话对上），并把「商品名称 / 品名 / 名称」这类写法不一的列归成一组。</li>
                        <li>在「合并计划确认」里核对：合并方式、匹配键和匹配预检（多少行能对上一目了然），再核对每列的归属。</li>
                        <li>点「开始合并」查看预览，确认后点「下载整理结果.xlsx」。</li>
                    </ol>
                    <p>提示：登录后 AI 归类更准（未登录走本地同义词规则）；13 位条码、前导零编码都会按文本保留，不会变形。</p>
                </details>

                <div class="excel-file-row">
                    <div id="mergeFileList" class="merge-file-list">
                        <p class="merge-file-empty">还没有选择文件。原始表可多选，支持多个 sheet。</p>
                    </div>
                    <div id="mergeResultMeta" class="excel-meta">等待处理</div>
                </div>

                <div id="mergeMappingSection" class="merge-mapping hidden">
                    <div class="merge-mapping-head">
                        <h2>合并计划确认</h2>
                        <p>先核对 AI 的合并计划和匹配预检，再核对每列的字段归类。可以改合并方式、匹配键、目标字段名，或忽略不需要的列。</p>
                    </div>
                    <div id="mergePlanPanel" class="merge-plan hidden"></div>
                    <div class="merge-field-chips-row">
                        <div id="mergeFieldChips" class="merge-field-chips"></div>
                        <button id="mergeAddFieldBtn" class="excel-mini-btn" type="button">+ 新增字段</button>
                    </div>
                    <div class="tool-table-wrap merge-mapping-table">
                        <table>
                            <thead>
                                <tr>
                                    <th>文件</th>
                                    <th>Sheet</th>
                                    <th>列</th>
                                    <th>原表头</th>
                                    <th>样例</th>
                                    <th>归到目标字段</th>
                                </tr>
                            </thead>
                            <tbody id="mergeMappingBody"></tbody>
                        </table>
                    </div>
                </div>

                <div id="mergePreviewSection" class="merge-preview hidden">
                    <h2>合并结果预览（前 50 行）</h2>
                    <div class="tool-table-wrap">
                        <table id="mergePreviewTable"></table>
                    </div>
                </div>
            </main>

            <aside class="excel-settings">
                <div class="excel-settings-head">
                    <span class="excel-setting-icon">⊞</span>
                    <div>
                        <h2>表格整理设置</h2>
                        <p>文件只在浏览器本地读取，不上传服务器</p>
                    </div>
                </div>

                <div class="excel-setting-section">
                    <h3>整理要求（可选）</h3>
                    <textarea id="mergeInstruction" rows="6" placeholder="例如：把所有进货表合并成一张表，只要商品名称、69码、数量、单价。&#10;又如：通过订单号匹配人名电话快递单号，按模板整理成新表，其他的信息都不要。"></textarea>
                </div>

                <div class="excel-setting-section">
                    <h3>合并选项</h3>
                    <label class="excel-checkbox">
                        <input id="mergeSourceColumnsOpt" type="checkbox" checked>
                        <span>附加「来源文件 / 来源Sheet」两列</span>
                    </label>
                    <label class="excel-checkbox">
                        <input id="mergeDedupeOpt" type="checkbox">
                        <span>去除完全重复的行</span>
                    </label>
                </div>

                <div id="mergeWarnings" class="tool-warnings hidden"></div>

                <p id="mergeStatus" class="excel-status"></p>

                <button id="mergeClassifyBtn" class="excel-primary-action" type="button">AI 规划合并</button>
                <button id="mergeRunBtn" class="excel-secondary-action" type="button">开始合并</button>
                <button id="mergeDownloadBtn" class="excel-secondary-action hidden" type="button">下载整理结果.xlsx</button>
                <button id="mergeClearBtn" class="excel-secondary-action" type="button">清空</button>

                <div class="excel-tip">
                    <strong>小贴士</strong>
                    <p>要把两张表「对上」（比如订单表配快递单号），AI 会自己从数据里找匹配键——即使你说的键不存在，也会按实际重合的列匹配，并在计划里告诉你它用了什么。</p>
                </div>
            </aside>
        </div>
    </div>
</section>

<script src="/assets/excel-automation-local.js?v={{ time() }}"></script>
<script src="/assets/table-merge-local.js?v={{ time() }}"></script>
@endsection
