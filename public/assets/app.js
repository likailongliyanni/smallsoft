const adminTokenKey = 'webauto_admin_token';
const userTokenKey = 'smallsoft_user_token';

function $(selector) { return document.querySelector(selector); }
function $$(selector) { return document.querySelectorAll(selector); }

function formToObject(form) { return Object.fromEntries(new FormData(form).entries()); }

function pretty(data) {
    return typeof data === 'string' ? data : JSON.stringify(data, null, 2);
}

function setText(el, data) { if (el) el.textContent = pretty(data); }

function firstValidationMessage(data) {
    const errors = data?.errors;
    if (!errors) return null;
    const first = Object.values(errors)[0];
    return Array.isArray(first) ? first[0] : first;
}

async function api(path, options = {}) {
    const headers = options.headers ? {...options.headers} : {};
    const token = localStorage.getItem(adminTokenKey);
    if (token) headers.Authorization = `Bearer ${token}`;

    let body = options.body;
    if (body && !(body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(body);
    }

    const response = await fetch(path, {
        method: options.method || 'GET',
        headers, body,
    });

    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json')
        ? await response.json() : await response.text();

    if (!response.ok || data?.ok === false) {
        throw new Error(data?.message || firstValidationMessage(data) || `请求失败：${response.status}`);
    }
    return data;
}

let feedbackCache = [];
let currentFbFilter = 'all';
let currentFbId = null;
let currentFbData = null;  // 当前打开的反馈完整数据（含 template），供复制使用

function initAdmin() {
    const loginPanel = $('#adminLoginPanel');
    const adminApp = $('#adminApp');
    const loginForm = $('#adminLoginForm');
    const loginResult = $('#adminLoginResult');
    const logoutBtn = $('#adminLogoutBtn');
    const modelForm = $('#modelForm');
    const modelResult = $('#modelResult');
    const modelForms = $$('.ai-model-form');
    const modelResults = {
        vision: $('#visionModelResult'),
        script: $('#scriptModelResult'),
    };
    const quotaForm = $('#quotaForm');

    // ── 登录 ──
    loginForm?.addEventListener('submit', async event => {
        event.preventDefault();
        setText(loginResult, '登录中...');
        try {
            const response = await api('/api/admin/login', {
                method: 'POST', body: formToObject(loginForm),
            });
            localStorage.setItem(adminTokenKey, response.token);
            setText(loginResult, '登录成功');
            await loadAdmin();
        } catch (error) {
            setText(loginResult, error.message);
        }
    });

    logoutBtn?.addEventListener('click', async () => {
        try { await api('/api/admin/logout', {method: 'POST'}); } catch (e) { console.warn(e); }
        localStorage.removeItem(adminTokenKey);
        showAdmin(false);
    });

    // ── 侧边栏导航 ──
    $$('.admin-nav-item').forEach(link => {
        link.addEventListener('click', event => {
            event.preventDefault();
            const tab = link.dataset.tab;
            switchTab(tab);
        });
    });

    // ── 模型表单 ──
    modelForm?.addEventListener('submit', async event => {
        event.preventDefault();
        setText(modelResult, '保存中...');
        try {
            const data = formToObject(modelForm);
            data.enabled = modelForm.enabled.checked;
            data.thinking_enabled = modelForm.thinking_enabled.checked;
            for (const key of ['temperature', 'max_tokens', 'request_timeout']) {
                if (data[key] === '') delete data[key];
                else data[key] = Number(data[key]);
            }
            const response = await api('/api/admin/model', { method: 'POST', body: data });
            setText(modelResult, response.model_config);
            modelForm.api_key.value = '';
        } catch (error) {
            setText(modelResult, error.message);
        }
    });

    $('#testModelBtn')?.addEventListener('click', async () => {
        setText(modelResult, '测试中...');
        try {
            const response = await api('/api/admin/model/test', { method: 'POST', body: {} });
            setText(modelResult, response);
        } catch (error) {
            setText(modelResult, error.message);
        }
    });

    // 🟢 阿里云全家桶测试
    const aliyunResult = $('#aliyunResult');
    const aliyunHint = $('#aliyunHint');
    $('#testAliyunBtn')?.addEventListener('click', async () => {
        const modelKey = $('#aliyunTestKey')?.value || 'code';
        setText(aliyunResult, '测试中（最多 30 秒）...');
        if (aliyunHint) aliyunHint.textContent = '';
        try {
            const response = await api('/api/admin/aliyun/test', {
                method: 'POST',
                body: { model_key: modelKey },
            });
            setText(aliyunResult, response);
            if (aliyunHint) {
                if (response.has_env_key) {
                    aliyunHint.textContent = response.result?.ok
                        ? '✓ Key 已配置且能调通'
                        : '⚠ Key 已配置但调用失败，看下面 message';
                    aliyunHint.style.color = response.result?.ok ? '#16a34a' : '#dc2626';
                } else {
                    aliyunHint.textContent = '⚠ 服务器未配置 DASHSCOPE_API_KEY，请去 .env 加';
                    aliyunHint.style.color = '#dc2626';
                }
            }
        } catch (error) {
            setText(aliyunResult, error.message);
            if (aliyunHint) {
                aliyunHint.textContent = '✗ 调用失败';
                aliyunHint.style.color = '#dc2626';
            }
        }
    });

    modelForms.forEach(form => {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const purpose = form.dataset.purpose || form.purpose?.value || 'script';
            const resultEl = modelResults[purpose];
            setText(resultEl, '保存中...');
            try {
                const data = formToObject(form);
                data.purpose = purpose;
                data.enabled = form.enabled.checked;
                data.thinking_enabled = form.thinking_enabled.checked;
                for (const key of ['temperature', 'max_tokens', 'request_timeout']) {
                    if (data[key] === '') delete data[key];
                    else data[key] = Number(data[key]);
                }
                const response = await api('/api/admin/model', { method: 'POST', body: data });
                setText(resultEl, response.model_config);
                form.api_key.value = '';
            } catch (error) {
                setText(resultEl, error.message);
            }
        });
    });

    $$('.test-model-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const purpose = btn.dataset.purpose || 'script';
            const resultEl = modelResults[purpose];
            setText(resultEl, '测试中...');
            try {
                const response = await api('/api/admin/model/test', {
                    method: 'POST',
                    body: { purpose },
                });
                setText(resultEl, response);
            } catch (error) {
                setText(resultEl, error.message);
            }
        });
    });

    $('#visionImageTestForm')?.addEventListener('submit', async event => {
        event.preventDefault();
        const resultEl = modelResults.vision;
        setText(resultEl, '上传图片并测试中...');
        try {
            const response = await api('/api/admin/model/test-vision', {
                method: 'POST',
                body: new FormData(event.currentTarget),
            });
            setText(resultEl, response);
        } catch (error) {
            setText(resultEl, error.message);
        }
    });

    quotaForm?.addEventListener('submit', async event => {
        event.preventDefault();
        try {
            const data = formToObject(quotaForm);
            data.user_id = Number(data.user_id);
            data.quota = Number(data.quota);
            await api('/api/admin/quota/add', { method: 'POST', body: data });
            quotaForm.reset();
            await loadUsers();
        } catch (error) {
            alert(error.message);
        }
    });

    // ── 反馈筛选 ──
    $$('.fb-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            $$('.fb-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFbFilter = btn.dataset.fbFilter;
            renderFeedback();
        });
    });

    // ── 弹窗 ──
    $('#fbModalClose')?.addEventListener('click', closeFbModal);
    $('.modal-mask')?.addEventListener('click', closeFbModal);
    ['handling', 'resolved', 'closed'].forEach(status => {
        $(`#fb${status[0].toUpperCase()+status.slice(1)}Btn`)?.addEventListener('click', () => updateFbStatus(status));
    });
    $('#fbCopyBtn')?.addEventListener('click', copyFbContent);

    loadAdmin();

    async function loadAdmin() {
        if (!localStorage.getItem(adminTokenKey)) {
            showAdmin(false);
            return;
        }
        try {
            await api('/api/admin/me');
            showAdmin(true);
            await Promise.all([
                loadStats(), loadModel(), loadUsers(),
                loadJobs(), loadOrders(), loadFeedback(),
                loadPatterns(), loadAnnouncements()
            ]);
        } catch (error) {
            localStorage.removeItem(adminTokenKey);
            showAdmin(false);
            setText(loginResult, '请登录管理员后台');
        }
    }

    function showAdmin(show) {
        loginPanel.classList.toggle('hidden', show);
        adminApp.classList.toggle('hidden', !show);
    }

    function switchTab(name) {
        $$('.admin-nav-item').forEach(n => n.classList.toggle('active', n.dataset.tab === name));
        $$('.tab-pane').forEach(p => p.classList.toggle('active', p.dataset.tab === name));
    }

    async function loadStats() {
        const response = await api('/api/admin/stats');
        const labels = {
            users: '总用户', active_users: '活跃用户',
            generation_jobs: '生成次数', training_submissions: '训练样本',
            open_feedback: '待处理反馈', paid_orders: '已支付订单',
        };
        $('#adminStats').innerHTML = Object.entries(response.stats)
            .map(([key, value]) => `
                <div class="stat">
                    <strong>${value}</strong>
                    <span>${labels[key] || key}</span>
                </div>
            `).join('');

        // 顶部待处理徽章
        const badge = $('#feedbackBadge');
        const cnt = response.stats.open_feedback || 0;
        if (cnt > 0) {
            badge.textContent = cnt;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
    }

    async function loadModel() {
        const response = await api('/api/admin/model');
        const configs = response.model_configs || {};
        const defaults = {
            vision: {provider: 'aliyun', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen3.6-plus', temperature: 0.1, max_tokens: 2048, request_timeout: 120},
            script: {provider: 'aliyun', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen3-coder-next', temperature: 0.1, max_tokens: 8192, request_timeout: 180},
        };
        modelForms.forEach(form => {
            const purpose = form.dataset.purpose || 'script';
            const config = configs[purpose] || defaults[purpose];
            form.provider.value = config.provider || defaults[purpose].provider;
            form.base_url.value = config.base_url || defaults[purpose].base_url;
            form.model.value = config.model || defaults[purpose].model;
            form.temperature.value = config.temperature ?? defaults[purpose].temperature;
            form.max_tokens.value = config.max_tokens ?? defaults[purpose].max_tokens;
            form.reasoning_effort.value = config.reasoning_effort || 'medium';
            form.request_timeout.value = config.request_timeout ?? defaults[purpose].request_timeout;
            form.system_prompt.value = config.system_prompt || '';
            form.thinking_enabled.checked = Boolean(config.thinking_enabled);
            form.enabled.checked = config.enabled !== false;
            setText(modelResults[purpose], {
                saved: Boolean(config.id),
                has_api_key: Boolean(config.has_api_key),
                provider: config.provider || defaults[purpose].provider,
                model: config.model || defaults[purpose].model,
                last_test_status: config.last_test_status || 'not tested',
                last_test_message: config.last_test_message || '',
                last_usage: config.last_usage || null,
            });
        });
        if (modelForms.length > 0) return;
        const config = response.model_config;
        if (!config) return;
        modelForm.provider.value = config.provider || 'aliyun';
        modelForm.base_url.value = config.base_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1';
        modelForm.model.value = config.model || 'qwen3-coder-next';
        modelForm.temperature.value = config.temperature ?? 0.2;
        modelForm.max_tokens.value = config.max_tokens ?? 8192;
        modelForm.reasoning_effort.value = config.reasoning_effort || 'high';
        modelForm.request_timeout.value = config.request_timeout ?? 180;
        modelForm.system_prompt.value = config.system_prompt || '';
        modelForm.thinking_enabled.checked = Boolean(config.thinking_enabled ?? true);
        modelForm.enabled.checked = Boolean(config.enabled);
        setText(modelResult, {
            已保存: true, 已配置Key: config.has_api_key,
            供应商: config.provider, 模型: config.model,
            最近测试: config.last_test_status || '未测试',
            测试信息: config.last_test_message || '',
            最近用量: config.last_usage || null,
        });
    }

    async function loadUsers(q = '') {
        const url = q ? `/api/admin/users?q=${encodeURIComponent(q)}` : '/api/admin/users';
        const response = await api(url);
        const list = response.users || [];
        $('#usersTable').innerHTML = list.map(user => `
            <tr>
                <td>${user.id}</td>
                <td><code style="font-size:11px">${escapeHtml(user.username)}</code></td>
                <td>${escapeHtml(user.nickname || '-')} ${user.nickname_edit_count >= 3 ? '<span class="fb-status closed" style="font-size:10px">🔒</span>' : ''}</td>
                <td>${escapeHtml(user.status)}</td>
                <td>${user.free_generations}</td>
                <td>${user.paid_generations}</td>
                <td>${formatTime(user.created_at)}</td>
            </tr>
        `).join('') || `<tr><td colspan="7" class="empty">${q ? '未找到匹配用户' : '暂无用户'}</td></tr>`;
    }

    // 搜索绑定
    $('#userSearchForm')?.addEventListener('submit', async e => {
        e.preventDefault();
        const q = $('#userSearchInput').value.trim();
        await loadUsers(q);
    });
    $('#userSearchClear')?.addEventListener('click', async () => {
        $('#userSearchInput').value = '';
        await loadUsers('');
    });

    async function loadJobs() {
        const response = await api('/api/admin/jobs');
        $('#jobsTable').innerHTML = response.jobs.map(job => `
            <tr>
                <td>${job.id}</td>
                <td>${escapeHtml(job.user?.username || '')}</td>
                <td>${escapeHtml(job.flow_name)}</td>
                <td>${escapeHtml(job.status)}</td>
                <td>${job.step_count}</td>
                <td>${escapeHtml(job.used_model || '')}</td>
            </tr>
        `).join('') || '<tr><td colspan="6" class="empty">暂无生成记录</td></tr>';
    }

    async function loadOrders() {
        const response = await api('/api/admin/orders');
        $('#ordersTable').innerHTML = response.orders.map(order => `
            <tr>
                <td>${escapeHtml(order.order_no)}</td>
                <td>${escapeHtml(order.user?.username || '')}</td>
                <td>${escapeHtml(order.plan_name)}</td>
                <td>${order.quota}</td>
                <td>¥${(order.amount_cents/100).toFixed(2)}</td>
                <td>${escapeHtml(order.status)}</td>
                <td>${formatTime(order.created_at)}</td>
            </tr>
        `).join('') || '<tr><td colspan="7" class="empty">暂无订单</td></tr>';
    }

    async function loadFeedback() {
        const response = await api('/api/admin/feedback');
        feedbackCache = response.feedback || [];
        renderFeedback();
    }

    function renderFeedback() {
        const list = $('#feedbackList');
        if (!list) return;

        let items = feedbackCache;
        if (currentFbFilter === 'auto_error') items = items.filter(i => (i.source || i.category) === 'auto_error');
        else if (currentFbFilter === 'manual') items = items.filter(i => ['manual', 'general'].includes(i.source || i.category));
        else if (currentFbFilter === 'open') items = items.filter(i => i.status === 'open');

        if (items.length === 0) {
            list.innerHTML = '<p class="muted" style="text-align:center;padding:40px 0">暂无反馈</p>';
            return;
        }

        list.innerHTML = items.map(item => {
            const src = item.source || item.category || 'manual';
            const srcLabel = ({
                auto_error: '🔴 自动报错',
                manual: '✋ 手动反馈',
                web: '🌐 网页反馈',
                general: '✋ 手动反馈',
            })[src] || src;
            const statusLabel = ({
                open: '待处理',
                handling: '处理中',
                resolved: '已解决',
                closed: '已关闭',
            })[item.status] || item.status;
            const errorBlock = item.error_message
                ? `<div class="fb-item-error">${escapeHtml(item.error_message.slice(0, 240))}</div>`
                : '';
            return `
                <div class="fb-item" data-fb-id="${item.id}">
                    <div class="fb-item-head">
                        <span class="fb-tag ${src}">${srcLabel}</span>
                        <span class="fb-status ${item.status}">${statusLabel}</span>
                        <span class="fb-item-title">${escapeHtml(item.flow_name || '(无流程名)')}</span>
                        <span class="fb-item-time">${formatTime(item.created_at)}</span>
                    </div>
                    <div class="fb-item-meta">
                        用户：${escapeHtml(item.user?.username || '游客')}
                        ${item.meta?.step_count ? `· ${item.meta.step_count} 步` : ''}
                    </div>
                    <div class="fb-item-content">${escapeHtml((item.content || '').slice(0, 200))}</div>
                    ${errorBlock}
                </div>
            `;
        }).join('');

        // 绑定点击
        $$('.fb-item').forEach(el => {
            el.addEventListener('click', () => showFbDetail(Number(el.dataset.fbId)));
        });
    }

    async function showFbDetail(id) {
        currentFbId = id;
        const modal = $('#feedbackModal');
        const content = $('#fbModalContent');
        const title = $('#fbModalTitle');
        modal.classList.remove('hidden');
        content.innerHTML = '<p class="muted">加载中...</p>';
        title.textContent = `反馈详情 #${id}`;

        try {
            const response = await api(`/api/admin/feedback/${id}`);
            const fb = response.feedback;
            const tpl = response.template;
            currentFbData = { fb, template: tpl };  // 缓存供复制

            title.textContent = `反馈 #${id} - ${fb.flow_name || '(无流程名)'}`;

            const src = fb.source || fb.category || 'manual';
            const srcLabel = ({
                auto_error: '🔴 自动报错',
                manual: '✋ 手动反馈',
                web: '🌐 网页反馈',
                general: '✋ 手动反馈',
            })[src] || src;

            content.innerHTML = `
                <dl class="fb-detail-grid">
                    <dt>ID</dt><dd>${fb.id}</dd>
                    <dt>类型</dt><dd><span class="fb-tag ${src}">${srcLabel}</span></dd>
                    <dt>状态</dt><dd><span class="fb-status ${fb.status}">${fb.status}</span></dd>
                    <dt>用户</dt><dd>${escapeHtml(fb.user?.username || '游客')} (ID: ${fb.user_id || '-'})</dd>
                    <dt>流程名</dt><dd>${escapeHtml(fb.flow_name || '-')}</dd>
                    <dt>步数</dt><dd>${fb.meta?.step_count || '-'}</dd>
                    <dt>提交时间</dt><dd>${formatTime(fb.created_at)}</dd>
                    <dt>文件路径</dt><dd><code style="font-size:12px;color:#64748b">${escapeHtml(fb.template_path || '-')}</code></dd>
                </dl>

                ${fb.error_message ? `
                <div class="fb-detail-section error">
                    <h4>❌ 报错信息</h4>
                    <pre>${escapeHtml(fb.error_message)}</pre>
                </div>` : ''}

                <div class="fb-detail-section">
                    <h4>💬 用户备注</h4>
                    <pre>${escapeHtml(fb.content || '(无)')}</pre>
                </div>

                ${tpl ? `
                <div class="fb-detail-section">
                    <h4>📋 流程模板 (DSL + 步骤，已脱敏)</h4>
                    <pre>${escapeHtml(JSON.stringify(tpl, null, 2))}</pre>
                </div>` : ''}
            `;
        } catch (error) {
            content.innerHTML = `<p style="color:#ef4444">加载失败：${escapeHtml(error.message)}</p>`;
        }
    }

    function closeFbModal() {
        $('#feedbackModal').classList.add('hidden');
        currentFbId = null;
        currentFbData = null;
    }

    function copyFbContent() {
        if (!currentFbData) {
            alert('反馈数据未加载');
            return;
        }
        const { fb, template } = currentFbData;
        const src = fb.source || fb.category || 'manual';
        const srcLabel = ({
            auto_error: '自动报错',
            manual: '用户手动反馈',
            web: '网页反馈',
            general: '手动反馈',
        })[src] || src;

        const lines = [
            '=== 好办法自动化 - 客户反馈 ===',
            `反馈 ID: ${fb.id}`,
            `类型: ${srcLabel}`,
            `状态: ${fb.status}`,
            `用户: ${fb.user?.username || '游客'} (ID: ${fb.user_id || '-'})`,
            `流程名: ${fb.flow_name || '-'}`,
            `步数: ${fb.meta?.step_count || '-'}`,
            `提交时间: ${fb.created_at || '-'}`,
            `文件路径: ${fb.template_path || '-'}`,
            '',
        ];

        if (fb.error_message) {
            lines.push('--- 报错信息 ---');
            lines.push(fb.error_message);
            lines.push('');
        }

        if (fb.content) {
            lines.push('--- 用户备注 ---');
            lines.push(fb.content);
            lines.push('');
        }

        if (template) {
            lines.push('--- 流程模板 (已脱敏) ---');
            lines.push(JSON.stringify(template, null, 2));
            lines.push('');
        }

        lines.push('=== END ===');
        const text = lines.join('\n');

        // 复制到剪贴板
        const btn = $('#fbCopyBtn');
        const origText = btn.textContent;

        const onSuccess = () => {
            btn.textContent = '✓ 已复制！可粘贴到聊天里发给作者';
            btn.style.background = '#059669';
            setTimeout(() => {
                btn.textContent = origText;
                btn.style.background = '#16a34a';
            }, 2500);
        };

        const onFail = () => {
            // 降级：弹窗显示内容让用户手动复制
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:80%;height:60vh;z-index:2000;padding:12px;border:2px solid #16a34a;border-radius:8px';
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); onSuccess(); } catch (e) {}
            setTimeout(() => ta.remove(), 100);
        };

        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(onSuccess).catch(onFail);
        } else {
            onFail();
        }
    }

    async function updateFbStatus(status) {
        if (!currentFbId) return;
        try {
            await api(`/api/admin/feedback/${currentFbId}`, {
                method: 'POST', body: { status },
            });
            closeFbModal();
            await loadFeedback();
            await loadStats();
        } catch (error) {
            alert('更新失败：' + error.message);
        }
    }

    // ═════════════════════════════════════
    //  AI 经验包（学习文件）管理
    // ═════════════════════════════════════

    let patternsCache = [];

    $('#patternsRefreshBtn')?.addEventListener('click', loadPatterns);
    $('#patternsNewBtn')?.addEventListener('click', () => openPatternModal(null));
    $('#patternsPreviewBtn')?.addEventListener('click', previewFullPrompt);
    $('#ptModalClose')?.addEventListener('click', closePatternModal);
    $('#ptCancelBtn')?.addEventListener('click', closePatternModal);
    $('#ptSaveBtn')?.addEventListener('click', savePattern);
    $('#ppModalClose')?.addEventListener('click', () => $('#promptPreviewModal').classList.add('hidden'));
    $('#ppCloseBtn')?.addEventListener('click', () => $('#promptPreviewModal').classList.add('hidden'));
    $('#ppCopyBtn')?.addEventListener('click', copyFullPrompt);

    async function loadPatterns() {
        const tbody = $('#patternsTable');
        if (!tbody) return;
        try {
            const resp = await api('/api/admin/ai-patterns');
            patternsCache = resp.items || [];
            $('#patternsHint').textContent = `共 ${patternsCache.length} 条经验包`;

            if (patternsCache.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无经验包，点「+ 新增经验包」开始</td></tr>';
                return;
            }

            tbody.innerHTML = patternsCache.map(p => {
                const isBuiltin = (p.source === 'builtin');
                const sourceBadge = isBuiltin
                    ? '<span style="display:inline-block;padding:1px 6px;border-radius:8px;font-size:11px;background:#dcfce7;color:#166534">内置</span>'
                    : '<span style="display:inline-block;padding:1px 6px;border-radius:8px;font-size:11px;background:#dbeafe;color:#1d4ed8">自定义</span>';
                const actions = isBuiltin
                    ? `<button class="btn btn-sm btn-outline" data-pt-view="${p.id}">📖 查看</button>
                       <span style="color:#94a3b8;font-size:12px;margin-left:6px">文件内置·只读</span>`
                    : `<button class="btn btn-sm" data-pt-edit="${p.id}" style="margin-right:4px">编辑</button>
                       <button class="btn btn-sm btn-outline" data-pt-toggle="${p.id}" style="margin-right:4px">${p.enabled ? '禁用' : '启用'}</button>
                       <button class="btn btn-sm btn-outline" data-pt-del="${p.id}" style="color:#dc2626;border-color:#dc2626">删除</button>`;
                const stamp = p.stamp || '-';
                return `
                <tr style="${isBuiltin ? 'background:#fafafa' : ''}">
                    <td>
                        ${p.enabled
                            ? '<span class="fb-status resolved">✓ 启用</span>'
                            : '<span class="fb-status closed">✗ 禁用</span>'}
                        <div style="margin-top:4px">${sourceBadge}</div>
                    </td>
                    <td>${categoryBadge(p.category)}</td>
                    <td><code style="background:#f3f4f6;padding:2px 6px;border-radius:3px;font-size:12px">${escapeHtml(p.code)}</code></td>
                    <td>${escapeHtml(p.title)}</td>
                    <td style="text-align:center">${p.priority}</td>
                    <td title="${escapeHtml(formatTime(p.updated_at))}"><code style="background:#fef3c7;color:#78350f;padding:2px 6px;border-radius:3px;font-size:11px;font-family:Consolas,monospace">${escapeHtml(stamp)}</code></td>
                    <td>${actions}</td>
                </tr>`;
            }).join('');

            // 顶部统计行
            const stats = resp.stats || {};
            if (stats.total !== undefined) {
                $('#patternsHint').textContent =
                    `共 ${stats.total} 条（📦 文件内置 ${stats.builtin || 0} · ✏️ 自定义 ${stats.custom || 0}）`;
            }

            // 绑定按钮
            tbody.querySelectorAll('[data-pt-edit]').forEach(b =>
                b.addEventListener('click', () => openPatternModal(b.dataset.ptEdit)));
            tbody.querySelectorAll('[data-pt-toggle]').forEach(b =>
                b.addEventListener('click', () => togglePattern(b.dataset.ptToggle)));
            tbody.querySelectorAll('[data-pt-del]').forEach(b =>
                b.addEventListener('click', () => deletePattern(b.dataset.ptDel)));
            tbody.querySelectorAll('[data-pt-view]').forEach(b =>
                b.addEventListener('click', () => viewBuiltinPattern(b.dataset.ptView)));
        } catch (error) {
            tbody.innerHTML = `<tr><td colspan="7" class="empty" style="color:#dc2626">加载失败：${escapeHtml(error.message)}</td></tr>`;
        }
    }

    // 分类徽标（颜色与桌面端流程卡片一致）
    function categoryBadge(cat) {
        const map = {
            common:  { label: '🌐 通用',     bg: '#f3f4f6', fg: '#475569' },
            browser: { label: '🌍 浏览器',   bg: '#dbeafe', fg: '#1d4ed8' },
            excel:   { label: '📊 Excel',    bg: '#d1fae5', fg: '#065f46' },
            word:    { label: '📝 Word',     bg: '#e0e7ff', fg: '#3730a3' },
            ps:      { label: '🎨 PS',       bg: '#fce7f3', fg: '#9d174d' },
            pdf:     { label: '📄 PDF',      bg: '#fee2e2', fg: '#991b1b' },
        };
        const c = map[cat] || map.browser;
        return `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;background:${c.bg};color:${c.fg};white-space:nowrap">${c.label}</span>`;
    }

    function viewBuiltinPattern(id) {
        const p = patternsCache.find(x => String(x.id) === String(id));
        if (!p) return;
        // 借用 promptPreviewModal 来只读展示
        const modal = $('#promptPreviewModal');
        $('#ppMeta').textContent =
            `📦 文件内置经验 · ${p.code} · 分类 ${p.category} · 优先级 ${p.priority}`;
        $('#ppContent').textContent = p.content || '(空)';
        modal.classList.remove('hidden');
    }

    function openPatternModal(id) {
        const modal = $('#patternModal');
        const title = $('#ptModalTitle');
        if (id) {
            const p = patternsCache.find(x => String(x.id) === String(id));
            if (!p) return;
            title.textContent = '编辑经验包：' + p.title;
            $('#ptId').value = p.id;
            $('#ptCode').value = p.code;
            $('#ptCode').disabled = true;  // code 不允许改
            $('#ptCategory').value = p.category || 'browser';
            $('#ptTitle').value = p.title;
            $('#ptContent').value = p.content;
            $('#ptPriority').value = p.priority;
            $('#ptEnabled').checked = !!p.enabled;
            $('#ptChangelog').value = p.changelog || '';
        } else {
            title.textContent = '新增 AI 经验包';
            $('#ptId').value = '';
            $('#ptCode').value = '';
            $('#ptCode').disabled = false;
            $('#ptCategory').value = 'browser';
            $('#ptTitle').value = '';
            $('#ptContent').value = '';
            $('#ptPriority').value = 50;
            $('#ptEnabled').checked = true;
            $('#ptChangelog').value = '';
        }
        $('#ptResult').textContent = '';
        modal.classList.remove('hidden');
    }

    function closePatternModal() {
        $('#patternModal').classList.add('hidden');
    }

    async function savePattern() {
        const data = {
            code: $('#ptCode').value.trim(),
            category: $('#ptCategory').value || 'browser',
            title: $('#ptTitle').value.trim(),
            content: $('#ptContent').value.trim(),
            priority: Number($('#ptPriority').value) || 50,
            enabled: $('#ptEnabled').checked,
            changelog: $('#ptChangelog').value.trim(),
        };
        if (!data.code || !data.title || !data.content) {
            $('#ptResult').textContent = '请填写 Code、标题、内容';
            return;
        }
        $('#ptSaveBtn').disabled = true;
        $('#ptResult').textContent = '保存中...';
        try {
            await api('/api/admin/ai-patterns', {
                method: 'POST', body: data,
            });
            $('#ptResult').textContent = '✓ 保存成功';
            await loadPatterns();
            setTimeout(closePatternModal, 800);
        } catch (error) {
            $('#ptResult').textContent = '失败：' + error.message;
        } finally {
            $('#ptSaveBtn').disabled = false;
        }
    }

    async function togglePattern(id) {
        const p = patternsCache.find(x => String(x.id) === String(id));
        if (!p || p.source === 'builtin') return;
        try {
            await api('/api/admin/ai-patterns', {
                method: 'POST',
                body: {
                    code: p.code,
                    category: p.category || 'browser',
                    title: p.title,
                    content: p.content,
                    enabled: !p.enabled,
                    priority: p.priority,
                    changelog: '通过后台切换启用状态',
                },
            });
            await loadPatterns();
        } catch (error) {
            alert('切换失败：' + error.message);
        }
    }

    async function deletePattern(id) {
        const p = patternsCache.find(x => String(x.id) === String(id));
        if (!p || p.source === 'builtin') return;
        if (!confirm(`确定删除「${p.title}」吗？\n\nCode: ${p.code}\n删除后该经验包立即从 AI 提示词中消失。`)) {
            return;
        }
        try {
            await api(`/api/admin/ai-patterns/${id}`, { method: 'DELETE' });
            await loadPatterns();
        } catch (error) {
            alert('删除失败：' + error.message);
        }
    }

    async function previewFullPrompt() {
        const modal = $('#promptPreviewModal');
        const content = $('#ppContent');
        const meta = $('#ppMeta');
        modal.classList.remove('hidden');
        content.textContent = '加载中...';
        meta.textContent = '';
        try {
            const resp = await api('/api/admin/ai-patterns/preview');
            const enabledCount = patternsCache.filter(p => p.enabled).length;
            meta.textContent = `共 ${resp.length} 字符 · 数据库经验包 ${enabledCount} 条启用 / ${patternsCache.length} 条`;
            content.textContent = resp.system_prompt || '(空)';
        } catch (error) {
            content.textContent = '加载失败：' + error.message;
        }
    }

    async function copyFullPrompt() {
        const text = $('#ppContent').textContent;
        try {
            await navigator.clipboard.writeText(text);
            $('#ppCopyBtn').textContent = '✓ 已复制';
            setTimeout(() => $('#ppCopyBtn').textContent = '📋 复制全部', 2000);
        } catch (e) {
            alert('复制失败，请手动选中复制');
        }
    }

    // ═════════════════════════════════════
    //  公告管理
    // ═════════════════════════════════════

    let annCache = [];

    $('#annForm')?.addEventListener('submit', async e => {
        e.preventDefault();
        await saveAnnouncement();
    });
    $('#annResetBtn')?.addEventListener('click', resetAnnForm);

    async function loadAnnouncements() {
        try {
            const resp = await api('/api/admin/announcements');
            annCache = resp.items || [];
            renderAnnouncementsTable();
        } catch (e) {
            $('#annTable').innerHTML = `<tr><td colspan="6" class="empty" style="color:#dc2626">加载失败：${escapeHtml(e.message)}</td></tr>`;
        }
    }

    function renderAnnouncementsTable() {
        const tbody = $('#annTable');
        if (!tbody) return;
        if (annCache.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无公告</td></tr>';
            return;
        }
        tbody.innerHTML = annCache.map(a => {
            const expired = a.expires_at && new Date(a.expires_at) < new Date();
            return `
            <tr>
                <td>${a.enabled && !expired
                    ? '<span class="fb-status resolved">✓启用</span>'
                    : (expired ? '<span class="fb-status closed">已过期</span>' : '<span class="fb-status closed">禁用</span>')}</td>
                <td style="max-width:400px">${escapeHtml(a.content)}</td>
                <td style="text-align:center">${a.priority}</td>
                <td style="font-size:12px;color:#94a3b8">${a.expires_at ? formatTime(a.expires_at) : '永久'}</td>
                <td style="font-size:12px;color:#94a3b8">${formatTime(a.created_at)}</td>
                <td>
                    <button class="btn btn-sm" data-ann-edit="${a.id}" style="margin-right:4px">编辑</button>
                    <button class="btn btn-sm btn-outline" data-ann-toggle="${a.id}" style="margin-right:4px">
                        ${a.enabled ? '禁用' : '启用'}
                    </button>
                    <button class="btn btn-sm btn-outline" data-ann-del="${a.id}" style="color:#dc2626;border-color:#dc2626">删除</button>
                </td>
            </tr>`;
        }).join('');

        tbody.querySelectorAll('[data-ann-edit]').forEach(b =>
            b.addEventListener('click', () => editAnnouncement(Number(b.dataset.annEdit))));
        tbody.querySelectorAll('[data-ann-toggle]').forEach(b =>
            b.addEventListener('click', () => toggleAnnouncement(Number(b.dataset.annToggle))));
        tbody.querySelectorAll('[data-ann-del]').forEach(b =>
            b.addEventListener('click', () => deleteAnnouncement(Number(b.dataset.annDel))));
    }

    function editAnnouncement(id) {
        const a = annCache.find(x => x.id === id);
        if (!a) return;
        $('#annId').value = a.id;
        $('#annContent').value = a.content;
        $('#annPriority').value = a.priority;
        $('#annEnabled').checked = !!a.enabled;
        if (a.expires_at) {
            // 转 datetime-local 格式
            const d = new Date(a.expires_at);
            $('#annExpires').value = d.toISOString().slice(0, 16);
        } else {
            $('#annExpires').value = '';
        }
        $('#annContent').scrollIntoView({behavior: 'smooth', block: 'center'});
    }

    function resetAnnForm() {
        $('#annId').value = '';
        $('#annContent').value = '';
        $('#annPriority').value = 50;
        $('#annEnabled').checked = true;
        $('#annExpires').value = '';
        $('#annResult').textContent = '';
    }

    async function saveAnnouncement() {
        const data = {
            content: $('#annContent').value.trim(),
            priority: Number($('#annPriority').value) || 50,
            enabled: $('#annEnabled').checked,
        };
        const id = Number($('#annId').value);
        if (id) data.id = id;
        const exp = $('#annExpires').value;
        if (exp) data.expires_at = exp.replace('T', ' ') + ':00';

        if (!data.content) {
            $('#annResult').textContent = '请填写公告内容';
            return;
        }
        $('#annSaveBtn').disabled = true;
        $('#annResult').textContent = '保存中...';
        try {
            await api('/api/admin/announcements', { method: 'POST', body: data });
            $('#annResult').textContent = '✓ 已保存';
            await loadAnnouncements();
            setTimeout(resetAnnForm, 1000);
        } catch (e) {
            $('#annResult').textContent = '失败：' + e.message;
        } finally {
            $('#annSaveBtn').disabled = false;
        }
    }

    async function toggleAnnouncement(id) {
        const a = annCache.find(x => x.id === id);
        if (!a) return;
        try {
            await api('/api/admin/announcements', {
                method: 'POST',
                body: {
                    id: a.id,
                    content: a.content,
                    priority: a.priority,
                    enabled: !a.enabled,
                    expires_at: a.expires_at,
                },
            });
            await loadAnnouncements();
        } catch (e) {
            alert('切换失败：' + e.message);
        }
    }

    async function deleteAnnouncement(id) {
        const a = annCache.find(x => x.id === id);
        if (!a) return;
        if (!confirm(`确定删除这条公告吗？\n\n${a.content.substring(0, 80)}`)) return;
        try {
            await api(`/api/admin/announcements/${id}`, { method: 'DELETE' });
            await loadAnnouncements();
        } catch (e) {
            alert('删除失败：' + e.message);
        }
    }
}

async function userApi(path, options = {}) {
    const headers = options.headers ? {...options.headers} : {};
    const token = localStorage.getItem(userTokenKey);
    if (token) headers.Authorization = `Bearer ${token}`;

    let body = options.body;
    if (body && !(body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(body);
    }

    const response = await fetch(path, {
        method: options.method || 'GET',
        headers,
        body,
    });

    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json')
        ? await response.json() : await response.text();

    if (!response.ok || data?.ok === false) {
        throw new Error(data?.message || firstValidationMessage(data) || `请求失败：${response.status}`);
    }
    return data;
}

function initSpreadsheetImages() {
    if (typeof window.initSpreadsheetImagesLocal === 'function') {
        window.initSpreadsheetImagesLocal({
            userApi,
            formToObject,
            firstValidationMessage,
            escapeHtml,
            userTokenKey,
        });
        if (typeof window.initTableMergeLocal === 'function') {
            window.initTableMergeLocal({
                userApi,
                escapeHtml,
                userTokenKey,
            });
        }
        if (typeof window.initTableTidyLocal === 'function') {
            window.initTableTidyLocal({
                userApi,
                escapeHtml,
                userTokenKey,
            });
        }
        return;
    }

    const localScriptErrorEl = $('#sheetExportResult');
    if (localScriptErrorEl) {
        localScriptErrorEl.textContent = '本地处理脚本加载失败，请刷新页面重试。';
        localScriptErrorEl.classList.add('error');
    }
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function formatTime(value) {
    if (!value) return '';
    return new Date(value).toLocaleString('zh-CN', {hour12: false});
}

document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page;
    if (page === 'admin') initAdmin();
    if (page === 'excel-automation') initSpreadsheetImages();
});
