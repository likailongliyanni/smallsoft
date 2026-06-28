@extends('layouts.app')

@section('title', '管理员后台 - 好办法网页自动化平台')
@section('page', 'admin')
@section('hide-nav', '1')

@section('content')

{{-- 登录卡片 --}}
<div id="adminLoginPanel" class="admin-login-wrap">
    <div class="admin-login-card">
        <div class="admin-login-header">
            <span class="brand-mark">好</span>
            <h2>管理员登录</h2>
        </div>
        <form id="adminLoginForm" class="form">
            <label>账号<input name="username" autocomplete="username" required placeholder="请输入管理员账号"></label>
            <label>密码<input name="password" type="password" autocomplete="current-password" required placeholder="请输入密码"></label>
            <button class="btn" type="submit" style="width:100%">登录后台</button>
        </form>
        <pre id="adminLoginResult" class="login-result"></pre>
    </div>
</div>

{{-- 后台主界面 --}}
<div id="adminApp" class="hidden">
    {{-- 顶栏 --}}
    <div class="admin-topbar">
        <div class="admin-topbar-left">
            <span class="brand-mark">好</span>
            <strong>管理后台</strong>
        </div>
        <button id="adminLogoutBtn" class="btn btn-outline btn-sm">退出登录</button>
    </div>

    {{-- 左右布局 --}}
    <div class="admin-layout">
        {{-- 侧边栏 --}}
        <aside class="admin-sidebar">
            <nav class="admin-nav">
                <a href="#overview" class="admin-nav-item active" data-tab="overview">
                    <span class="ico">📊</span> 概览
                </a>
                <a href="#model" class="admin-nav-item" data-tab="model">
                    <span class="ico">🤖</span> 软件配置
                </a>
                <a href="#releases" class="admin-nav-item" data-tab="releases">
                    <span class="ico">📦</span> 软件发布
                </a>
                <a href="#users" class="admin-nav-item" data-tab="users">
                    <span class="ico">👤</span> 用户管理
                </a>
                <a href="#jobs" class="admin-nav-item" data-tab="jobs">
                    <span class="ico">📝</span> 生成记录
                </a>
                <a href="#orders" class="admin-nav-item" data-tab="orders">
                    <span class="ico">💳</span> 最近订单
                </a>
                <a href="#feedback" class="admin-nav-item" data-tab="feedback">
                    <span class="ico">💬</span> 客户反馈
                    <span class="badge hidden" id="feedbackBadge"></span>
                </a>
                <a href="#patterns" class="admin-nav-item" data-tab="patterns">
                    <span class="ico">🧠</span> AI 经验包
                </a>
                <a href="#announcements" class="admin-nav-item" data-tab="announcements">
                    <span class="ico">📢</span> 公告管理
                </a>
            </nav>
        </aside>

        {{-- 内容区 --}}
        <main class="admin-content">

            {{-- 概览 --}}
            <section class="tab-pane active" data-tab="overview">
                <div class="content-head">
                    <h1>数据概览</h1>
                    <p class="content-sub">系统当前运行情况</p>
                </div>
                <div id="adminStats" class="admin-stats"></div>
            </section>

            {{-- 模型配置 --}}
            <section class="tab-pane" data-tab="model">
                <div class="content-head ai-page-head">
                    <div>
                        <h1>AI 配置中心</h1>
                        <p class="content-sub">统一管理模型服务、功能绑定与运行参数</p>
                    </div>
                    <button class="btn" id="addSoftwareConfigBtn" type="button">＋ 新增 AI 功能</button>
                </div>

                <div id="softwareConfigResult" class="result-box hidden"></div>
                <div id="softwareConfigList" class="software-config-list">
                    <div class="panel muted">正在读取 AI 配置中心…</div>
                </div>

                <datalist id="aliyunModelPresets">
                    <option value="qwen-plus"></option>
                    <option value="qwen3.6-plus"></option>
                    <option value="qwen3.6-flash"></option>
                    <option value="qwen3-max"></option>
                    <option value="qwen3-coder-plus"></option>
                    <option value="qwen-vl-max-latest"></option>
                    <option value="wan2.7-image"></option>
                </datalist>

                <details class="legacy-configs">
                    <summary>旧版专项配置工具（兼容保留）</summary>

                {{-- 阿里云全家桶（新） --}}
                <div class="panel" style="margin-bottom:14px;border:1px solid #16a34a">
                    <h3 style="margin:0 0 8px;color:#16a34a">🟢 阿里云全家桶（启用中）</h3>
                    <p class="muted" style="margin:0 0 12px">
                        API Key 由服务器 <code>.env</code> 的 <code>DASHSCOPE_API_KEY</code> 提供，不存数据库。
                        生成时客户端可选模型档位。
                    </p>
                    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
                        <label style="margin:0">测试档位
                            <select id="aliyunTestKey" style="margin-left:6px">
                                <option value="code" selected>代码生成 (qwen3-coder-plus)</option>
                                <option value="balanced">平衡 (qwen3.6-plus)</option>
                                <option value="strong">强档 (qwen3-max)</option>
                                <option value="fast">快速 (qwen3.6-flash)</option>
                                <option value="vision">视觉 (qwen-vl-max-latest)</option>
                            </select>
                        </label>
                        <button class="btn" id="testAliyunBtn" type="button" style="background:#16a34a;color:#fff">🧪 测试连接</button>
                        <span id="aliyunHint" class="muted"></span>
                    </div>
                    <pre id="aliyunResult" class="result-box"></pre>
                </div>

                {{-- 图片修复模型（智能截图软件） --}}
                <div class="panel" style="margin-bottom:14px;border:1px solid #2563eb">
                    <h3 style="margin:0 0 8px;color:#2563eb">🖼️ 图片修复模型（智能截图软件）</h3>
                    <p class="muted" style="margin:0 0 12px">
                        去水印 / 去广告 / 白底上图用的阿里云百炼模型。百炼上线新模型后，在这里改模型名即可，
                        <b>无需改代码或重新发版</b>。API Key 同样取服务器 <code>DASHSCOPE_API_KEY</code>。
                    </p>
                    <form id="imageModelForm" class="form">
                        <div class="form-grid-2">
                            <label>修复模型<input name="repair_model" placeholder="wan2.7-image"></label>
                            <label>检测模型<input name="detect_model" placeholder="qwen3.6-plus"></label>
                        </div>
                        <div class="button-row">
                            <button class="btn" type="submit" style="background:#2563eb;color:#fff">保存图片模型</button>
                        </div>
                        <pre id="imageModelResult" class="result-box"></pre>
                    </form>
                </div>

                <details>
                    <summary class="muted" style="cursor:pointer;margin:6px 0 14px">▸ 旧版模型表单（已废弃，点击展开）</summary>

                <div class="panel">
                    <form id="modelForm" class="form">
                        <div class="form-grid-2">
                            <label>供应商
                                <select name="provider">
                                    <option value="aliyun">Aliyun 百炼 / Qwen</option>
                                    <option value="deepseek">DeepSeek</option>
                                    <option value="openai-compatible">OpenAI Compatible</option>
                                </select>
                            </label>
                            <label>模型名称<input name="model" value="qwen3-coder-next" placeholder="qwen3-coder-next"></label>
                        </div>
                        <label>Base URL<input name="base_url" value="https://dashscope.aliyuncs.com/compatible-mode/v1" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"></label>
                        <label>API Key<input name="api_key" type="password" placeholder="留空表示不修改已保存的 Key"></label>
                        <div class="form-grid-3">
                            <label>Temperature<input name="temperature" type="number" min="0" max="2" step="0.1" value="0.2"></label>
                            <label>Max Tokens<input name="max_tokens" type="number" min="256" max="64000" value="8192"></label>
                            <label>超时秒数<input name="request_timeout" type="number" min="30" max="600" value="180"></label>
                        </div>
                        <label>Reasoning Effort
                            <select name="reasoning_effort">
                                <option value="high">high</option>
                                <option value="medium">medium</option>
                                <option value="low">low</option>
                            </select>
                        </label>
                        <label>系统提示词<textarea name="system_prompt" rows="6"></textarea></label>
                        <div class="form-checks">
                            <label class="inline"><input name="thinking_enabled" type="checkbox" checked> 开启 Thinking</label>
                            <label class="inline"><input name="enabled" type="checkbox" checked> 启用此模型</label>
                        </div>
                        <div class="button-row">
                            <button class="btn" type="submit">保存配置</button>
                            <button id="testModelBtn" class="btn btn-outline" type="button">测试连接</button>
                        </div>
                    </form>
                    <pre id="modelResult" class="result-box"></pre>
                </div>
                </details>
                </details>
            </section>

            {{-- 软件安装包发布 --}}
            <section class="tab-pane" data-tab="releases">
                <div class="content-head release-page-head">
                    <div>
                        <h1>软件发布中心</h1>
                        <p class="content-sub">上传安装包、切换当前版本并统一生成官网下载链接</p>
                    </div>
                    <a class="btn btn-outline" href="/download" target="_blank" rel="noopener">查看下载页</a>
                </div>

                <div class="release-admin-grid">
                    <section class="panel release-upload-panel">
                        <div class="release-panel-title">
                            <span class="release-panel-icon">↑</span>
                            <div><h3>上传新版本</h3><p>上传成功后可立即作为该软件的当前下载版本</p></div>
                        </div>

                        <form id="softwareReleaseForm" class="form" enctype="multipart/form-data">
                            <label>快速选择软件
                                <select id="releasePreset">
                                    <option value="aidoc" data-name="好办法AI档案管理">好办法 AI 档案管理</option>
                                    <option value="projetx" data-name="ProjetX 录屏">ProjetX 录屏</option>
                                    <option value="snap-saver" data-name="智能截图软件">智能截图软件</option>
                                    <option value="webauto" data-name="好办法浏览器自动化">好办法浏览器自动化</option>
                                    <option value="custom" data-name="">其他软件（手动填写）</option>
                                </select>
                            </label>
                            <div class="form-grid-2">
                                <label>软件代码<input name="software_code" value="aidoc" required maxlength="60" placeholder="例如 aidoc"></label>
                                <label>软件名称<input name="software_name" value="好办法AI档案管理" required maxlength="120"></label>
                                <label>版本号<input name="version" value="1.0.0" required maxlength="40" placeholder="例如 1.0.1"></label>
                                <label>适用平台
                                    <select name="platform">
                                        <option value="windows-x64" selected>Windows 10/11 64 位</option>
                                        <option value="windows-arm64">Windows ARM64</option>
                                        <option value="macos">macOS</option>
                                        <option value="linux">Linux</option>
                                    </select>
                                </label>
                            </div>
                            <label>安装包文件
                                <input name="package" type="file" required accept=".exe,.msi,.zip,.rar,.7z">
                                <small class="field-hint">支持 exe、msi、zip、rar、7z，单个文件最大 600 MB</small>
                            </label>
                            <label>更新说明<textarea name="release_notes" rows="4" maxlength="5000" placeholder="例如：修复图片识别、增加聊天记录保存"></textarea></label>
                            <label class="release-current-check">
                                <input name="enabled" type="checkbox" value="1" checked>
                                <span><strong>上传后设为当前版本</strong><small>同一软件、同一平台的旧版本会自动停止公开下载</small></span>
                            </label>
                            <div id="releaseUploadProgress" class="release-progress hidden">
                                <div><span id="releaseProgressText">准备上传…</span><strong id="releaseProgressPercent">0%</strong></div>
                                <progress id="releaseProgressBar" max="100" value="0"></progress>
                            </div>
                            <button id="softwareReleaseSubmit" class="btn release-submit" type="submit">上传并发布</button>
                            <div id="softwareReleaseResult" class="release-result hidden"></div>
                        </form>
                    </section>

                    <aside class="panel release-guide-panel">
                        <span class="release-guide-badge">发布流程</span>
                        <h3>以后更新软件只需三步</h3>
                        <ol>
                            <li><strong>选择软件</strong><span>填写新版本号和更新说明</span></li>
                            <li><strong>上传安装包</strong><span>服务器自动计算大小和 SHA256</span></li>
                            <li><strong>设为当前版</strong><span>下载页立即显示新版本</span></li>
                        </ol>
                        <div class="release-server-note">
                            <strong>宝塔上传限制</strong>
                            <p>首次部署请把 PHP 的 <code>upload_max_filesize</code> 和 <code>post_max_size</code> 调整到 600M 以上，同时把 Nginx <code>client_max_body_size</code> 调整到 600M。</p>
                        </div>
                    </aside>
                </div>

                <section class="panel release-list-panel">
                    <header>
                        <div><h3>版本记录</h3><p>旧版本不会自动删除，可以随时切回</p></div>
                        <button id="softwareReleasesRefresh" class="btn btn-sm btn-outline" type="button">刷新</button>
                    </header>
                    <div class="table-wrap">
                        <table class="release-table">
                            <thead><tr><th>状态</th><th>软件 / 版本</th><th>安装包</th><th>SHA256</th><th>下载</th><th>发布时间</th><th>操作</th></tr></thead>
                            <tbody id="softwareReleasesTable"><tr><td colspan="7" class="empty">正在读取版本记录…</td></tr></tbody>
                        </table>
                    </div>
                </section>
            </section>

            {{-- 用户管理 --}}
            <section class="tab-pane" data-tab="users">
                <div class="content-head">
                    <h1>用户管理</h1>
                    <p class="content-sub">查看所有用户、调整付费次数、搜索定位</p>
                </div>

                <div class="panel" style="margin-bottom:14px">
                    <form id="userSearchForm" class="user-search-bar">
                        <input name="q" id="userSearchInput" placeholder="搜索：序列号 / 昵称 / 账号 / 邮箱 / 手机（回车或点搜索）">
                        <button class="btn btn-sm" type="submit">搜索</button>
                        <button class="btn btn-sm btn-outline" type="button" id="userSearchClear">清空</button>
                    </form>
                    <div id="userSoftwareTabs" class="soft-tabs"></div>
                </div>

                <div class="panel">
                    <div class="form-inline-quota" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:10px">
                        <span class="muted">充值套餐（点一下自动填张数）：</span>
                        @foreach (config('platform.snap_saver_packages', []) as $pkg)
                            <button class="btn btn-sm btn-outline" type="button"
                                data-pkg-quota="{{ $pkg['quota'] }}"
                                data-pkg-amount="{{ number_format($pkg['amount_cents'] / 100, 2) }}">
                                ¥{{ rtrim(rtrim(number_format($pkg['amount_cents'] / 100, 2), '0'), '.') }} / {{ $pkg['quota'] }}张
                            </button>
                        @endforeach
                    </div>
                    <form id="quotaForm" class="form form-inline-quota">
                        <label>用户 ID<input name="user_id" placeholder="ID" required></label>
                        <label>调整次数<input name="quota" placeholder="正数=增加，负数=减少" required></label>
                        <label>备注<input name="note" placeholder="可选"></label>
                        <button class="btn btn-sm" type="submit">调整额度</button>
                    </form>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th><th>账号(序列号)</th><th>软件</th><th>昵称</th><th>状态</th>
                                    <th>免费</th><th>付费</th><th>注册时间</th>
                                </tr>
                            </thead>
                            <tbody id="usersTable"></tbody>
                        </table>
                    </div>
                </div>
            </section>

            {{-- 生成记录 --}}
            <section class="tab-pane" data-tab="jobs">
                <div class="content-head">
                    <h1>AI 生成记录</h1>
                    <p class="content-sub">用户生成脚本的历史</p>
                </div>
                <div class="panel">
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th><th>用户</th><th>流程</th>
                                    <th>状态</th><th>步数</th><th>模型</th>
                                </tr>
                            </thead>
                            <tbody id="jobsTable"></tbody>
                        </table>
                    </div>
                </div>
            </section>

            {{-- 最近订单 --}}
            <section class="tab-pane" data-tab="orders">
                <div class="content-head">
                    <h1>最近订单</h1>
                    <p class="content-sub">付费充值记录</p>
                </div>
                <div class="panel">
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>订单号</th><th>用户</th><th>套餐</th>
                                    <th>次数</th><th>金额</th><th>状态</th><th>时间</th>
                                </tr>
                            </thead>
                            <tbody id="ordersTable"></tbody>
                        </table>
                    </div>
                </div>
            </section>

            {{-- 客户反馈 --}}
            <section class="tab-pane" data-tab="feedback">
                <div class="content-head">
                    <h1>客户反馈</h1>
                    <p class="content-sub">软件自动错误反馈 + 用户手动反馈</p>
                </div>

                <div class="feedback-tabs">
                    <button class="fb-tab active" data-fb-filter="all">全部</button>
                    <button class="fb-tab" data-fb-filter="auto_error">自动报错</button>
                    <button class="fb-tab" data-fb-filter="manual">用户反馈</button>
                    <button class="fb-tab" data-fb-filter="open">待处理</button>
                </div>

                <div class="panel">
                    <div id="feedbackList" class="feedback-list"></div>
                </div>
            </section>

            {{-- 公告管理 --}}
            <section class="tab-pane" data-tab="announcements">
                <div class="content-head">
                    <h1>📢 公告管理</h1>
                    <p class="content-sub">
                        客户端顶部会从下往上滚动显示这些公告，多条公告轮播。修改后立即生效，用户重启软件或自然刷新即可看到。
                    </p>
                </div>

                <div class="panel" style="margin-bottom:14px">
                    <form id="annForm" class="form">
                        <input type="hidden" name="id" id="annId">
                        <label>公告内容（最多 500 字符）
                            <textarea name="content" id="annContent" rows="3" required maxlength="500"
                                placeholder="例如：v1.1 新版本已发布，请点击「检查更新」获取最新经验库"></textarea>
                        </label>
                        <div class="form-grid-3">
                            <label>优先级<input name="priority" id="annPriority" type="number" min="0" max="999" value="50" placeholder="数字小的先显示"></label>
                            <label>过期时间（可选）<input name="expires_at" id="annExpires" type="datetime-local"></label>
                            <label class="inline" style="align-items:flex-end;padding-bottom:10px">
                                <input type="checkbox" name="enabled" id="annEnabled" checked> 启用
                            </label>
                        </div>
                        <div class="button-row">
                            <button class="btn" id="annSaveBtn" type="submit" style="background:#16a34a;color:#fff">💾 保存公告</button>
                            <button class="btn btn-outline" id="annResetBtn" type="button">清空表单</button>
                        </div>
                        <pre id="annResult" class="result-box"></pre>
                    </form>
                </div>

                <div class="panel">
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th style="width:60px">状态</th>
                                    <th>内容</th>
                                    <th style="width:70px">优先级</th>
                                    <th style="width:140px">过期时间</th>
                                    <th style="width:140px">创建时间</th>
                                    <th style="width:180px">操作</th>
                                </tr>
                            </thead>
                            <tbody id="annTable"></tbody>
                        </table>
                    </div>
                </div>
            </section>

            {{-- AI 经验包 --}}
            <section class="tab-pane" data-tab="patterns">
                <div class="content-head">
                    <h1>🧠 AI 经验包（学习文件）</h1>
                    <p class="content-sub">
                        遇到新场景（日期选择器、富文本、级联菜单等）只需新增一条经验，AI 立即学会，无需改代码或重新发版。
                    </p>
                </div>

                <div class="panel" style="margin-bottom:14px">
                    <div class="form-inline-quota" style="display:flex; gap:10px; align-items:center; flex-wrap:wrap">
                        <button class="btn" id="patternsRefreshBtn" type="button">🔄 刷新</button>
                        <button class="btn" id="patternsNewBtn" type="button" style="background:#16a34a;color:#fff">+ 新增经验包</button>
                        <button class="btn btn-outline" id="patternsPreviewBtn" type="button">👁 预览完整 system prompt</button>
                        <span id="patternsHint" class="muted" style="margin-left:auto"></span>
                    </div>
                </div>

                <div class="panel">
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th style="width:60px">状态</th>
                                    <th style="width:80px">分类</th>
                                    <th style="width:160px">Code</th>
                                    <th>标题</th>
                                    <th style="width:60px">优先级</th>
                                    <th style="width:170px" title="时间戳指纹：一眼看出经验是哪个时间点的版本">🏷️ 版本印记</th>
                                    <th style="width:220px">操作</th>
                                </tr>
                            </thead>
                            <tbody id="patternsTable"></tbody>
                        </table>
                    </div>
                </div>
            </section>

        </main>
    </div>
</div>

{{-- AI 经验包 编辑弹窗 --}}
<div id="patternModal" class="modal hidden">
    <div class="modal-mask"></div>
    <div class="modal-body" style="max-width:780px">
        <div class="modal-head">
            <h3 id="ptModalTitle">新增 AI 经验包</h3>
            <button class="modal-close" id="ptModalClose">×</button>
        </div>
        <div class="modal-content">
            <form id="patternForm" class="form">
                <input type="hidden" name="_id" id="ptId">
                <div class="form-grid-3">
                    <label>Code（唯一标识）<input name="code" id="ptCode" required maxlength="60"
                        placeholder="例：date-picker"></label>
                    <label>场景分类
                        <select name="category" id="ptCategory">
                            <option value="common">🌐 通用（所有场景）</option>
                            <option value="browser" selected>🌍 浏览器</option>
                            <option value="excel">📊 Excel</option>
                            <option value="word">📝 Word</option>
                            <option value="ps">🎨 Photoshop</option>
                            <option value="pdf">📄 PDF</option>
                        </select>
                    </label>
                    <label>优先级<input name="priority" id="ptPriority" type="number" min="0" max="999" value="50"
                        placeholder="0-999"></label>
                </div>
                <label>标题<input name="title" id="ptTitle" required maxlength="120"
                    placeholder="例：日期选择器（el-date-picker）处理规则"></label>
                <label>经验内容（Markdown）
                    <textarea name="content" id="ptContent" rows="14" required maxlength="20000"
                        placeholder="例：&#10;当 step.selector 含 el-date 或 description 含日期时：&#10;- 用 fill 而不是 click&#10;- value 用 YYYY-MM-DD 格式&#10;- excel_column 非空 → 必用 from_excel"></textarea>
                </label>
                <div class="form-grid-2">
                    <label class="inline"><input type="checkbox" name="enabled" id="ptEnabled" checked> 启用</label>
                    <label>变更说明（可选）<input name="changelog" id="ptChangelog" maxlength="2000"
                        placeholder="例：v1.0 新增日期选择器规则"></label>
                </div>
                <pre id="ptResult" class="result-box"></pre>
            </form>
        </div>
        <div class="modal-foot">
            <button class="btn btn-outline" id="ptCancelBtn" type="button">取消</button>
            <button class="btn" id="ptSaveBtn" type="button" style="background:#16a34a;color:#fff">💾 保存</button>
        </div>
    </div>
</div>

{{-- AI 经验包 完整预览弹窗 --}}
<div id="promptPreviewModal" class="modal hidden">
    <div class="modal-mask"></div>
    <div class="modal-body" style="max-width:900px">
        <div class="modal-head">
            <h3>完整 System Prompt 预览</h3>
            <button class="modal-close" id="ppModalClose">×</button>
        </div>
        <div class="modal-content">
            <div class="muted" id="ppMeta" style="margin-bottom:10px"></div>
            <pre id="ppContent" style="background:#fafafa;border:1px solid #e5e7eb;border-radius:6px;padding:14px;max-height:60vh;overflow:auto;white-space:pre-wrap;font-family:Consolas,Monaco,monospace;font-size:12px"></pre>
        </div>
        <div class="modal-foot">
            <button class="btn" id="ppCopyBtn" type="button" style="background:#2563eb;color:#fff">📋 复制全部</button>
            <button class="btn btn-outline" id="ppCloseBtn" type="button">关闭</button>
        </div>
    </div>
</div>

{{-- 反馈详情弹窗 --}}
<div id="feedbackModal" class="modal hidden">
    <div class="modal-mask"></div>
    <div class="modal-body">
        <div class="modal-head">
            <h3 id="fbModalTitle">反馈详情</h3>
            <button class="modal-close" id="fbModalClose">×</button>
        </div>
        <div class="modal-content" id="fbModalContent"></div>
        <div class="modal-foot">
            <button class="btn" id="fbCopyBtn" style="background:#16a34a">📋 复制全部内容</button>
            <span style="flex:1"></span>
            <button class="btn btn-outline btn-sm" data-status="handling" id="fbHandlingBtn">标记处理中</button>
            <button class="btn btn-outline btn-sm" data-status="resolved" id="fbResolvedBtn">标记已解决</button>
            <button class="btn btn-outline btn-sm" data-status="closed" id="fbClosedBtn">关闭</button>
        </div>
    </div>
</div>

@endsection
