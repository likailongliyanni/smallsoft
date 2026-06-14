function __hbf_init() {
    if (window.__hbf_injected) return;
    if (!document.body) { setTimeout(__hbf_init, 30); return; }
    window.__hbf_injected = true;

    // ⭐ 工具栏归属：全局只建一个工具栏，建在「第一个可见的 frame」里。
    // 不能用 window.top===window 判断——聚水潭订单页用户真正看到的内容其实在
    // 子 iframe 里，顶层 frame 用户根本看不到，那样工具栏会消失（"录制按钮不见了"）。
    // 做法：同源 frame 共享 window.top 上的归属标志，谁先注入谁建（一般是主内容 frame）；
    //       跨域 iframe 拿不到 top，就各自退化为本地标志（最多多一个，但不至于没有）。
    const SHOULD_SHOW_UI = (function () {
        try {
            if (!document.body) return false;
            // 找一个所有同源 frame 都能共享的 window 放归属标志
            let flagWin = window;
            try {
                // 跨域访问 window.top.location 会抛 SecurityError；能访问说明同源
                void window.top.location.href;
                flagWin = window.top;
            } catch (e) {
                flagWin = window;  // 跨域 iframe：退化为本地标志
            }
            // 已经有 frame 抢到工具栏归属 → 我只监听不建 UI
            try { if (flagWin.__hbf_toolbar_owner) return false; } catch (e) {}
            // 视口太小的隐藏 / 微型 iframe 不建
            const vw = window.innerWidth || 0, vh = window.innerHeight || 0;
            if (vw < 120 || vh < 120) return false;
            // 抢占归属
            try { flagWin.__hbf_toolbar_owner = true; } catch (e) {}
            return true;
        } catch (e) {
            return true;  // 兜底：宁可显示也不要没有按钮
        }
    })();

    // 知识库（由 Python 注入 window.__hbf_rules）
    const RULES = window.__hbf_rules || {};
    console.log("[好办法] 录制脚本已注入，规则版本:", RULES.version || "默认",
        SHOULD_SHOW_UI ? "（建工具栏）" : "（仅监听，不建 UI）", (location.href || "").substring(0, 80));

    const MAX_STEPS = 50;
    let stepCount = 0;
    let paused = false;

    // 浏览器层面的双发事件保护（不是用户的"双击"，那个要保留）
    let lastClickTime = 0;
    let lastMouse = { x: 0, y: 0, el: null, time: 0 };
    let manualVisuals = [];
    const MANUAL_HOTKEY = "Ctrl+Shift+X";
    const MANUAL_NEXT_MATCH_MS = Number(RULES.manual_screenshot_match_ms || 15000);

    // 输入框包装层 class（白名单匹配，不会误伤 -node/-menu/-item）
    // 注意：这个列表不再用于"跳过 click"，只供未来的可视化提示用
    const WRAPPER_CLASSES = new Set(RULES.input_wrapper_classes || []);
    // 下拉触发器 class（点击会展开下拉菜单，必须记录这一步）
    const TRIGGER_CLASSES = new Set(RULES.trigger_wrapper_classes || []);
    // 下拉菜单选项 class
    const OPTION_CLASSES = new Set(RULES.option_classes || []);

    // 滚动追踪（横竖都记录）
    let lastRecordedScrollX = Math.round(window.scrollX || window.pageXOffset || 0);
    let lastRecordedScrollY = Math.round(window.scrollY || window.pageYOffset || 0);
    let scrollDebounceTimer = null;
    const SCROLL_THRESHOLD = Number(RULES.scroll_threshold || 120);

    // 上传检测：追踪最近一次 click，用于在 input[type=file].change 触发时升级它为 upload
    let lastClickInfo = null;  // { target, label, selector, scoped, time, stepIndex }
    const UPLOAD_DETECT_WINDOW_MS = 8000;  // 8 秒内的 click 可被升级为 upload

    /* ───── 样式 ───── */
    const style = document.createElement("style");
    style.textContent = `
        #hbf-toolbar{position:fixed;top:12px;right:12px;z-index:2147483646;background:#1a1a1a;color:#fff;border-radius:12px;padding:8px 14px 8px 6px;font-family:"Microsoft YaHei",sans-serif;font-size:13px;display:flex;align-items:center;gap:10px;box-shadow:0 4px 20px rgba(0,0,0,0.35);user-select:none;transition:opacity 0.2s,width 0.2s}
        #hbf-toolbar:hover{opacity:1}
        #hbf-toolbar.hbf-faded{opacity:0.35}
        #hbf-toolbar .hbf-drag{width:18px;height:24px;display:flex;align-items:center;justify-content:center;cursor:move;color:#9ca3af;font-size:14px;line-height:1;border-radius:5px}
        #hbf-toolbar .hbf-drag:hover{background:#2d3748;color:#fff}
        #hbf-toolbar .dot{width:10px;height:10px;border-radius:50%;background:#ef4444;animation:hbf-blink 1s infinite;flex-shrink:0}
        #hbf-toolbar.paused .dot{background:#94a3b8;animation:none}
        @keyframes hbf-blink{50%{opacity:0.3}}
        #hbf-toolbar .ct{background:#16a34a;padding:3px 11px;border-radius:10px;font-weight:700;font-size:12px;flex-shrink:0}
        #hbf-toolbar .ct.warn{background:#f97316}
        #hbf-toolbar .ct.over{background:#dc2626}
        #hbf-toolbar button{border:none;padding:6px 11px;border-radius:7px;cursor:pointer;font:inherit;font-size:12px;font-weight:600;flex-shrink:0}
        #hbf-toolbar .pause{background:#374151;color:#fff}
        #hbf-toolbar .pause:hover{background:#4b5563}
        #hbf-toolbar .done{background:#16a34a;color:#fff}
        #hbf-toolbar .done:hover{background:#15803d}
        #hbf-toolbar .hbf-min{background:transparent;color:#9ca3af;padding:4px 7px;font-size:14px;line-height:1}
        #hbf-toolbar .hbf-min:hover{background:#2d3748;color:#fff}
        #hbf-toolbar .hbf-body{display:flex;align-items:center;gap:10px;transition:opacity 0.15s,max-width 0.2s,margin 0.2s}
        #hbf-toolbar.hbf-collapsed{padding:8px 8px;gap:0}
        #hbf-toolbar.hbf-collapsed .hbf-body{max-width:0;overflow:hidden;margin:0;opacity:0;pointer-events:none}
        #hbf-toolbar.hbf-collapsed .hbf-min{background:#16a34a;color:#fff}
        #hbf-toolbar.hbf-collapsed .hbf-min:hover{background:#15803d}

        #hbf-banner{position:fixed;top:0;left:0;right:0;z-index:2147483645;background:#fef3c7;color:#78350f;font-family:"Microsoft YaHei",sans-serif;font-size:13px;padding:8px 16px;display:flex;align-items:center;justify-content:center;gap:8px;box-shadow:0 2px 4px rgba(0,0,0,0.08);transition:opacity 0.25s}
        #hbf-banner.hbf-faded{opacity:0.25}
        #hbf-banner:hover{opacity:1 !important}
        #hbf-banner.warn{background:#fee2e2;color:#7f1d1d}
        #hbf-banner .close{background:transparent;border:none;cursor:pointer;font-size:18px;color:inherit;padding:0 6px}
        #hbf-flash{position:fixed;z-index:2147483644;pointer-events:none;border:2px solid #16a34a;border-radius:4px;box-shadow:0 0 0 4px rgba(22,163,74,0.2);transition:opacity 0.4s;background:rgba(22,163,74,0.08)}
        #hbf-toast{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#f97316;color:#fff;padding:10px 22px;border-radius:9px;font-family:"Microsoft YaHei";font-size:14px;font-weight:600;box-shadow:0 8px 24px rgba(249,115,22,0.4);animation:hbf-slide 0.25s}
        @keyframes hbf-slide{from{opacity:0;transform:translate(-50%,20px)}to{opacity:1;transform:translate(-50%,0)}}
    `;
    document.head.appendChild(style);

    /* ───── 顶部提示条 ─────
       点 × 一次 → 当次录制隐藏
       点 × 两次（24 小时内） → 永久隐藏（除非清除浏览器数据）
       小提示：用户点了 × 后 24 小时内的所有录制都不会再弹这个条 */
    const BANNER_DISMISS_KEY = "__hbf_banner_dismissed_until";
    function _isBannerDismissed() {
        try {
            const v = localStorage.getItem(BANNER_DISMISS_KEY);
            if (!v) return false;
            const expireAt = Number(v);
            if (!Number.isFinite(expireAt)) return false;
            return Date.now() < expireAt;
        } catch (e) { return false; }
    }

    // banner 提到函数作用域，避免 showOverWarn 在 iframe 里报 ReferenceError
    let banner = null;
    if (SHOULD_SHOW_UI && !_isBannerDismissed()) {
        banner = document.createElement("div");
        banner.id = "hbf-banner";
        banner.innerHTML = `💡 录制中：动作间隔 3-5 秒更准确；右上角工具栏可<b>按住 ⠿ 拖动</b>或点 <b>▣</b> 最小化；截图请将鼠标放到目标上按 ${MANUAL_HOTKEY}。<button class="close" id="hbf-banner-close" title="关闭（24 小时内不再显示）">×</button>`;
        document.body.appendChild(banner);
        document.getElementById("hbf-banner-close").onclick = () => {
            banner.style.display = "none";
            // 记住"关掉了"，24 小时内不再显示
            try {
                const expireAt = Date.now() + 24 * 60 * 60 * 1000;
                localStorage.setItem(BANNER_DISMISS_KEY, String(expireAt));
            } catch (e) {}
        };

        // banner 3 秒后自动半透明（鼠标移上去恢复）
        let _bannerFadeTimer = setTimeout(() => { banner.classList.add("hbf-faded"); }, 3000);
        banner.addEventListener("mouseenter", () => {
            if (_bannerFadeTimer) clearTimeout(_bannerFadeTimer);
            banner.classList.remove("hbf-faded");
        });
        banner.addEventListener("mouseleave", () => {
            if (_bannerFadeTimer) clearTimeout(_bannerFadeTimer);
            _bannerFadeTimer = setTimeout(() => { banner.classList.add("hbf-faded"); }, 2500);
        });
    }

    /* ───── 工具栏（可拖动 + 可最小化）─────
       只在顶层 frame 创建。iframe 里不渲染 UI，但仍然抓点击/输入并上报 Python。 */
    let toolbar = null;
    if (SHOULD_SHOW_UI) {
    toolbar = document.createElement("div");
    toolbar.id = "hbf-toolbar";
    toolbar.innerHTML = `
        <div class="hbf-drag" id="hbf-drag" title="按住拖动 / 双击吸边">⠿</div>
        <div class="hbf-body" id="hbf-body">
            <div class="dot" id="hbf-dot"></div>
            <span id="hbf-state">录制中</span>
            <span class="ct" id="hbf-ct">0 步</span>
            <button class="pause" id="hbf-undo" title="删除上一步记录">↶ 撤销</button>
            <button class="pause" id="hbf-pause">⏸ 暂停</button>
            <button class="done" id="hbf-done">✅ 完成</button>
        </div>
        <button class="hbf-min" id="hbf-min" title="最小化 / 展开">▣</button>
    `;
    document.body.appendChild(toolbar);

    document.getElementById("hbf-undo").onclick = () => {
        if (stepCount <= 0) return;
        stepCount--;
        updateCount();
        try { window.__hbf_undo(); } catch (e) {}
    };
    document.getElementById("hbf-pause").onclick = () => {
        const next = !paused;
        // 本地立即应用（视觉反馈不等 Python 广播）
        _applyPausedLocal(next);
        // 上报 Python，由 Python 广播给所有 iframe 同步
        try { window.__hbf_pause(next); } catch (e) {}
    };
    document.getElementById("hbf-done").onclick = () => {
        try { window.__hbf_done(); } catch (e) {}
    };

    /* ───── 拖动 + 最小化 + 位置记忆 ───── */
    const TB_POS_KEY = "__hbf_toolbar_pos_v1";
    const TB_MIN_KEY = "__hbf_toolbar_min_v1";

    function _savePos(left, top) {
        try { localStorage.setItem(TB_POS_KEY, JSON.stringify({ left, top })); } catch (e) {}
    }
    function _loadPos() {
        try {
            const s = localStorage.getItem(TB_POS_KEY);
            if (!s) return null;
            const p = JSON.parse(s);
            if (typeof p.left !== "number" || typeof p.top !== "number") return null;
            return p;
        } catch (e) { return null; }
    }
    function _clampToViewport(left, top) {
        const r = toolbar.getBoundingClientRect();
        const maxLeft = Math.max(0, window.innerWidth - r.width - 4);
        const maxTop = Math.max(0, window.innerHeight - r.height - 4);
        return {
            left: Math.max(4, Math.min(left, maxLeft)),
            top: Math.max(4, Math.min(top, maxTop)),
        };
    }
    function _applyPos(left, top) {
        toolbar.style.left = left + "px";
        toolbar.style.top = top + "px";
        toolbar.style.right = "auto";  // 拖动后取消默认的 right: 12px
    }

    // 还原上次位置（如有）
    (function _restorePos() {
        const p = _loadPos();
        if (p) {
            // 等下一帧布局完成后 clamp，避免取不到尺寸
            requestAnimationFrame(() => {
                const c = _clampToViewport(p.left, p.top);
                _applyPos(c.left, c.top);
            });
        }
    })();

    // 拖动逻辑
    let _dragging = false;
    let _dragStart = { x: 0, y: 0, left: 0, top: 0 };
    const dragHandle = document.getElementById("hbf-drag");

    dragHandle.addEventListener("mousedown", function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        _dragging = true;
        const r = toolbar.getBoundingClientRect();
        _dragStart = { x: e.clientX, y: e.clientY, left: r.left, top: r.top };
        document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", function (e) {
        if (!_dragging) return;
        e.preventDefault();
        const dx = e.clientX - _dragStart.x;
        const dy = e.clientY - _dragStart.y;
        const c = _clampToViewport(_dragStart.left + dx, _dragStart.top + dy);
        _applyPos(c.left, c.top);
    }, true);

    document.addEventListener("mouseup", function (e) {
        if (!_dragging) return;
        _dragging = false;
        document.body.style.userSelect = "";
        const r = toolbar.getBoundingClientRect();
        _savePos(Math.round(r.left), Math.round(r.top));
    }, true);

    // 双击拖柄 → 吸到右上角
    dragHandle.addEventListener("dblclick", function (e) {
        e.preventDefault();
        e.stopPropagation();
        const r = toolbar.getBoundingClientRect();
        const left = Math.max(4, window.innerWidth - r.width - 12);
        const top = 12;
        _applyPos(left, top);
        _savePos(left, top);
    });

    // 最小化 / 展开
    const minBtn = document.getElementById("hbf-min");
    function _setCollapsed(collapsed) {
        toolbar.classList.toggle("hbf-collapsed", collapsed);
        minBtn.textContent = collapsed ? "▢" : "▣";
        minBtn.title = collapsed ? "展开工具栏" : "最小化";
        try { localStorage.setItem(TB_MIN_KEY, collapsed ? "1" : "0"); } catch (e) {}
        // 收起后重新 clamp，避免溢出
        requestAnimationFrame(() => {
            const r = toolbar.getBoundingClientRect();
            const c = _clampToViewport(r.left, r.top);
            _applyPos(c.left, c.top);
        });
    }
    minBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        _setCollapsed(!toolbar.classList.contains("hbf-collapsed"));
    });
    // 还原上次最小化状态
    try {
        if (localStorage.getItem(TB_MIN_KEY) === "1") {
            requestAnimationFrame(() => _setCollapsed(true));
        }
    } catch (e) {}

    // 鼠标移开 3 秒后半透明（让用户看到下面的页面），鼠标移入恢复
    let _fadeTimer = null;
    function _scheduleFade() {
        if (_fadeTimer) clearTimeout(_fadeTimer);
        toolbar.classList.remove("hbf-faded");
        _fadeTimer = setTimeout(() => {
            if (!_dragging) toolbar.classList.add("hbf-faded");
        }, 3000);
    }
    toolbar.addEventListener("mouseenter", () => {
        if (_fadeTimer) clearTimeout(_fadeTimer);
        toolbar.classList.remove("hbf-faded");
    });
    toolbar.addEventListener("mouseleave", _scheduleFade);
    _scheduleFade();

    // 窗口尺寸变化时重新 clamp（防止位置失效）
    window.addEventListener("resize", () => {
        const r = toolbar.getBoundingClientRect();
        const c = _clampToViewport(r.left, r.top);
        _applyPos(c.left, c.top);
    });
    }  // ← SHOULD_SHOW_UI 工具栏块结束

    /* ───── 跨 frame / 跨标签页同步全局 step 总数 ─────
       Python 端在收到任意 frame 的 record 后，调用每个 frame 的
       window.__hbf_set_global_count(N)，让主页面工具栏的数字始终是
       "所有 frame 累计点击数"。iframe 也会收到调用但工具栏不存在，
       updateCount 会自动跳过。 */
    window.__hbf_set_global_count = function (n) {
        if (typeof n !== "number" || n < 0) return;
        stepCount = n;
        updateCount();
    };

    /* ───── 跨 frame 同步 paused 状态 ─────
       top frame 点暂停时通过 window.__hbf_pause 上报 Python，Python 遍历
       所有 frame 调用 __hbf_set_paused，这样 iframe 里的 click 监听器也
       能跟着停下来，不会继续偷偷记录。 */
    function _applyPausedLocal(b) {
        paused = !!b;
        if (SHOULD_SHOW_UI && toolbar) {
            toolbar.classList.toggle("paused", paused);
            const stateEl = document.getElementById("hbf-state");
            const pauseEl = document.getElementById("hbf-pause");
            if (stateEl) stateEl.textContent = paused ? "已暂停" : "录制中";
            if (pauseEl) pauseEl.textContent = paused ? "▶ 继续" : "⏸ 暂停";
        }
    }

    window.__hbf_set_paused = function (b) {
        if (typeof b !== "boolean") return;
        _applyPausedLocal(b);
    };

    function updateCount() {
        if (!SHOULD_SHOW_UI || !toolbar) return;  // iframe 无工具栏，跳过
        const c = document.getElementById("hbf-ct");
        if (!c) return;
        c.textContent = stepCount + " 步";
        c.classList.remove("warn", "over");
        if (stepCount > MAX_STEPS) {
            c.classList.add("over");
            showOverWarn();
        } else if (stepCount >= MAX_STEPS - 10) {
            c.classList.add("warn");
        }
    }

    function showOverWarn() {
        if (!SHOULD_SHOW_UI || !banner) return;
        if (banner.classList.contains("warn")) return;
        banner.classList.add("warn");
        banner.innerHTML = `⚠️ 已超过 50 步上限，整理时需要取消多余步骤。<button class="close" id="hbf-banner-close">×</button>`;
        document.getElementById("hbf-banner-close").onclick = () => banner.style.display = "none";
    }

    function showToast(msg, color = "#f97316") {
        if (!SHOULD_SHOW_UI) return;  // iframe 弹 toast 用户看不全，跳过
        const old = document.getElementById("hbf-toast");
        if (old) old.remove();
        const t = document.createElement("div");
        t.id = "hbf-toast";
        t.textContent = msg;
        t.style.background = color;
        document.body.appendChild(t);
        setTimeout(() => { try { t.remove(); } catch(e){} }, 2000);
    }

    /* ───── 选择器构造 ───── */
    function bestSelector(el) {
        const tag = el.tagName.toLowerCase();
        const cfg = RULES.selector_priority || {};
        const idBlack = cfg.id_blacklist_prefixes || ["__", "el-id-", "n-id-", "ant-"];
        const idMax = cfg.id_max_length || 40;
        const dataAttrs = cfg.data_attrs || ["data-testid", "data-cy", "data-test", "data-id"];

        // 1. 稳定的 ID
        if (el.id && el.id.length < idMax) {
            const blocked = idBlack.some(p => el.id.startsWith(p));
            if (!blocked) return "#" + el.id.replace(/"/g, '\\"');
        }

        // 2. data-* 属性
        for (const attr of dataAttrs) {
            const v = el.getAttribute(attr);
            if (v) return `[${attr}="${v}"]`;
        }

        // 3. name 属性
        const name = el.getAttribute("name");
        if (name) return `${tag}[name="${name}"]`;

        // 4. 按钮/链接：优先用可见文本（最稳健）
        const useText = cfg.button_use_text !== false;
        const textMax = cfg.button_text_max_length || 30;
        const isButton = tag === "button" || tag === "a"
            || el.getAttribute("role") === "button"
            || (el.className && /\b(btn|button)\b/i.test(el.className));
        if (useText && isButton) {
            const text = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
            if (text && text.length > 0 && text.length < textMax) {
                return `${tag}:has-text("${text.replace(/"/g, '\\"')}")`;
            }
        }

        // 5. 下拉选项 / 菜单项：用文本（这些通常没有稳定 ID）
        if (el.className && typeof el.className === "string") {
            const classList = el.className.trim().split(/\s+/);
            const isOption = classList.some(c => OPTION_CLASSES.has(c));
            if (isOption) {
                const text = (el.innerText || el.textContent || "").trim();
                if (text && text.length > 0 && text.length < 40) {
                    return `text="${text.replace(/"/g, '\\"')}"`;
                }
            }
        }

        // 6. input 的 placeholder/type
        if (tag === "input" || tag === "textarea") {
            const ph = el.getAttribute("placeholder");
            if (ph) return `${tag}[placeholder="${ph}"]`;
            const tp = el.getAttribute("type");
            if (tp) return `${tag}[type="${tp}"]`;
        }

        // 7. 业务 class（过滤掉框架通用 class）
        const genericPrefixes = cfg.generic_class_prefixes || ["el-", "ant-", "n-", "van-"];
        if (el.className && typeof el.className === "string") {
            const classes = el.className.trim().split(/\s+/).filter(c => {
                if (!c || c.length <= 3) return false;
                return !genericPrefixes.some(p => c.startsWith(p));
            });
            if (classes.length > 0) {
                let sel = tag + "." + classes[0];
                const text = (el.innerText || el.textContent || "").trim();
                if (text && text.length > 0 && text.length < 20) {
                    sel += `:has-text("${text.replace(/"/g, '\\"')}")`;
                }
                return sel;
            }
        }

        // 8. 文本兜底
        const text = (el.innerText || el.textContent || "").trim().substring(0, 20);
        if (text) return `text="${text.replace(/"/g, '\\"')}"`;

        return tag;
    }

    /* ───── label 提取 ───── */
    function elementLabel(el) {
        const cfg = RULES.label_extraction || {};

        if (cfg.aria_label !== false) {
            const al = el.getAttribute("aria-label");
            if (al) return cleanLabel(al);
        }
        if (cfg.for_attribute !== false && el.id) {
            const lbl = document.querySelector(`label[for="${el.id}"]`);
            if (lbl) return cleanLabel(lbl.innerText);
        }
        // 父级 label
        if (cfg.parent_label !== false) {
            let p = el.parentElement;
            for (let i = 0; i < 6 && p; i++) {
                if (p.tagName === "LABEL") return cleanLabel(p.innerText);
                const cls = p.className && typeof p.className === "string" ? p.className : "";
                const isFormItem = (cfg.form_item_containers || []).some(k =>
                    new RegExp("\\b" + k.replace(/[-_]/g, "[-_]") + "\\b").test(cls)
                );
                if (isFormItem) {
                    const selectors = cfg.form_item_label_selectors || ["label"];
                    for (const s of selectors) {
                        try {
                            const inner = p.querySelector(s);
                            if (inner) {
                                const t = cleanLabel(inner.innerText);
                                if (t) return t;
                            }
                        } catch (e) {}
                    }
                }
                p = p.parentElement;
            }
        }
        // 前面的兄弟节点
        let prev = el.previousElementSibling;
        for (let i = 0; i < 3 && prev; i++) {
            const tag = prev.tagName;
            if (tag === "LABEL" || tag === "SPAN" || tag === "DIV") {
                const t = cleanLabel(prev.innerText);
                if (t && t.length < 30 && t.length > 0) return t;
            }
            prev = prev.previousElementSibling;
        }
        const ph = el.getAttribute("placeholder");
        if (ph) return cleanLabel(ph);
        const nm = el.getAttribute("name");
        if (nm) return nm;
        const txt = (el.innerText || el.textContent || "").trim();
        if (txt) return txt.substring(0, 16);
        return "";
    }

    function cleanLabel(s) {
        if (!s) return "";
        let v = s.trim();
        const prefixes = (RULES.label_extraction && RULES.label_extraction.placeholder_strip_prefix) ||
            ["请输入", "请选择", "请填写"];
        for (const p of prefixes) {
            if (v.startsWith(p)) {
                v = v.substring(p.length).trim();
                break;
            }
        }
        return v.replace(/[:：*\s]+$/, "").trim().substring(0, 24);
    }

    function elementText(el) {
        return (el.innerText || el.textContent || "").trim().substring(0, 40);
    }

    /* ───── 把点击目标"提升"到真正的可点击祖先 ─────
       关键修复：用户点 <span>新 增</span> 时，自动提升到外层 <button>，
       这样 selector 是 button:has-text("新 增") 而不是 text="新 增"，
       触发下拉菜单/对话框更可靠。 */
    function findClickableTarget(el) {
        if (!el || el === document.body) return el;
        let n = el;
        for (let i = 0; i < 6 && n && n !== document.body; i++) {
            const tag = n.tagName ? n.tagName.toLowerCase() : "";
            if (tag === "button" || tag === "a") return n;
            const role = n.getAttribute ? n.getAttribute("role") : "";
            if (role === "button" || role === "link" || role === "menuitem"
                || role === "option" || role === "tab") return n;
            const cls = (n.className && typeof n.className === "string") ? n.className : "";
            // 已知可点击容器（含菜单项）
            if (/(^|\s)(el-button|el-dropdown-item|el-dropdown-menu__item|el-menu-item|el-option|el-cascader-node|el-select-dropdown__item|el-tabs__item|el-radio|el-checkbox|ant-btn|ant-dropdown-item|ant-select-item-option|ant-cascader-menu-item|ant-menu-item|ant-radio|ant-checkbox|n-button|n-base-select-option|n-cascader-option|n-menu-item|van-button|van-cell--clickable|btn|button)(\s|$)/i.test(cls)) {
                return n;
            }
            n = n.parentElement;
        }
        return el;
    }

    /* ───── XPath（兜底定位）───── */
    function getXPath(el) {
        if (!el || el.nodeType !== 1) return "";
        if (el.id && !/^(__|el-id-|n-id-|ant-)/.test(el.id) && el.id.length < 40) {
            return `//*[@id="${el.id}"]`;
        }
        if (el === document.documentElement) return "/html";
        if (el === document.body) return "/html/body";
        const parts = [];
        let n = el;
        while (n && n.nodeType === 1 && n !== document.body && n !== document.documentElement) {
            let idx = 1;
            let sib = n.previousElementSibling;
            while (sib) {
                if (sib.tagName === n.tagName) idx++;
                sib = sib.previousElementSibling;
            }
            const tag = n.tagName.toLowerCase();
            parts.unshift(tag + (idx > 1 ? `[${idx}]` : ""));
            n = n.parentElement;
        }
        return "/html/body/" + parts.join("/");
    }

    /* ───── 带 form-item 范围的选择器 ─────
       用 label 文本锚定，对任何元素（input/div/button）都有效
       这是修复"下拉框用 text=当前显示值"的核心 */
    function scopedSelector(el) {
        // 找最近的 form-item 容器（最多向上 8 层）
        let fi = null;
        let cur = el.parentElement;
        for (let i = 0; i < 8 && cur; i++) {
            const cls = cur.className && typeof cur.className === "string" ? cur.className : "";
            // 兼容多种框架的 form-item 容器：
            //   element/ant/naive/avue/通用，以及聚水潭的 goods-form-item / goods-form-item-row
            if (/(\b|^)(el-form-item|ant-form-item|n-form-item|avue-form-item|form-item|form_item|form-group|goods-form-item|goods-form-item-row)(\b|$)/i.test(cls)) {
                fi = cur;
                break;
            }
            cur = cur.parentElement;
        }
        if (!fi) return null;

        // 在 form-item 里找 label 文本（优先 <label>，回退到带 label class 的元素）
        const labels = fi.querySelectorAll("label, [class*='label']:not([class*='content']):not([class*='wrap'])");
        let labelText = "";
        for (const l of labels) {
            const t = (l.innerText || l.textContent || "").trim()
                .replace(/[:：*]/g, "").trim();
            if (t && t.length < 30) { labelText = t; break; }
        }
        if (!labelText) return null;

        // 找出 form-item 容器的标识 class（兼容聚水潭 goods- 前缀）
        const fiClass = (fi.className || "").split(/\s+/).find(c =>
            /^(el-form-item|ant-form-item|n-form-item|avue-form-item|form-item|form-group|goods-form-item|goods-form-item-row)$/.test(c)
        ) || "form-item";

        const tag = el.tagName.toLowerCase();
        const elCls = (el.className && typeof el.className === "string") ? el.className : "";

        // 元素自身的结构化标识（优先用框架类，不要用当前文本）
        // 这是关键：避免 text="集采不含运" 这种动态值
        let inner = tag;

        // 找一个稳定的结构化 class（el-select, avue-select, ant-select 等）
        const stableClassRegex = /^(el-|ant-|n-|van-|avue-)[a-z-]+/i;
        const elClasses = elCls.trim().split(/\s+/).filter(c => stableClassRegex.test(c));
        if (elClasses.length > 0) {
            // 用第一个结构化 class（最有可能是组件根类）
            inner = "." + elClasses[0];
        } else if (tag === "button" || tag === "a") {
            // 按钮：仍然用文本（按钮文字一般是固定的）
            const text = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
            if (text && text.length < 30) {
                inner = `${tag}:has-text("${text.replace(/"/g, '\\"')}")`;
            }
        } else if (tag === "input" || tag === "textarea") {
            inner = tag;
        }

        return `.${fiClass}:has-text("${labelText.replace(/"/g, '\\"')}") ${inner}`;
    }

    /* ───── 容器类型判断 ───── */
    // 是否是"下拉触发器"（el-select / el-cascader / el-date-picker 等）
    // 这种容器的 click 必须记录（用户在打开下拉菜单）
    function isTriggerWrapper(el) {
        let n = el;
        for (let i = 0; i < 5 && n; i++) {
            const cls = (n.className && typeof n.className === "string") ? n.className.trim() : "";
            if (cls) {
                const parts = cls.split(/\s+/);
                for (const c of parts) {
                    if (TRIGGER_CLASSES.has(c)) return n;  // 返回触发器节点
                }
            }
            n = n.parentElement;
        }
        return null;
    }

    // 是否是"纯文本输入框"容器（el-input 等）
    // 这种容器的 click 跳过（用户只是聚焦，blur 时再用 fill 记录）
    function isInputWrapper(el) {
        let n = el;
        for (let i = 0; i < 5 && n; i++) {
            const tag = n.tagName ? n.tagName.toLowerCase() : "";
            // input/textarea：readonly 的算触发器（select 显示框），不跳过
            if (tag === "input" || tag === "textarea") {
                if (n.readOnly || n.hasAttribute("readonly")) {
                    return false;  // readonly = 下拉显示框，不跳过
                }
                return true;
            }
            const cls = (n.className && typeof n.className === "string") ? n.className.trim() : "";
            if (cls) {
                const parts = cls.split(/\s+/);
                for (const c of parts) {
                    if (WRAPPER_CLASSES.has(c)) return true;
                }
            }
            n = n.parentElement;
        }
        return false;
    }

    /* ───── 元素是否是下拉选项（应该被记录的）───── */
    function isOptionElement(el) {
        let n = el;
        for (let i = 0; i < 4 && n; i++) {
            const cls = (n.className && typeof n.className === "string") ? n.className.trim() : "";
            if (cls) {
                const parts = cls.split(/\s+/);
                for (const c of parts) {
                    if (OPTION_CLASSES.has(c)) return true;
                }
            }
            n = n.parentElement;
        }
        return false;
    }

    function e_isHbfElement(el) {
        if (!el) return false;
        return !!(el.closest && (el.closest("#hbf-toolbar") || el.closest("#hbf-banner") || el.closest("#hbf-flash") || el.closest("#hbf-toast")));
    }

    function flash(el) {
        return;
        try {
            const r = el.getBoundingClientRect();
            const f = document.createElement("div");
            f.id = "hbf-flash";
            f.style.left = r.left + "px";
            f.style.top = r.top + "px";
            f.style.width = r.width + "px";
            f.style.height = r.height + "px";
            document.body.appendChild(f);
            setTimeout(() => f.style.opacity = "0", 100);
            setTimeout(() => f.remove(), 500);
        } catch (e) {}
    }

    /* ───── 视口 + 滚动快照 ───── */
    function getViewportData() {
        return {
            width: window.innerWidth,
            height: window.innerHeight,
            device_scale_factor: window.devicePixelRatio || 1,
            scrollX: Math.round(window.scrollX || window.pageXOffset || 0),
            scrollY: Math.round(window.scrollY || window.pageYOffset || 0),
            scrollWidth: document.documentElement.scrollWidth,
            scrollHeight: document.documentElement.scrollHeight,
        };
    }

    /* ───── DOM 上下文（提升展开菜单 / 表格单元格的录制精度）───── */
    function captureDomContext(el) {
        if (!el || !el.tagName) return null;
        const ctx = {};

        // 1. 父级链（最多 6 层，记录 tag + 关键 class + role）
        const parents = [];
        let p = el.parentElement;
        for (let i = 0; i < 6 && p && p !== document.body; i++) {
            const cls = (p.className && typeof p.className === "string") ? p.className.trim() : "";
            const tag = p.tagName.toLowerCase();
            const role = (p.getAttribute && p.getAttribute("role")) || "";
            if (cls || role) {
                const topClasses = cls.split(/\s+/).filter(Boolean).slice(0, 4).join(" ");
                parents.push({ tag, class: topClasses, role: role || undefined });
            }
            p = p.parentElement;
        }
        if (parents.length) ctx.parents = parents;

        // 2. 兄弟位置（第几个 / 共几个）
        if (el.parentElement) {
            const siblings = el.parentElement.children;
            const sameTags = [];
            let idx = -1;
            for (let i = 0; i < siblings.length; i++) {
                if (siblings[i].tagName === el.tagName) {
                    if (siblings[i] === el) idx = sameTags.length;
                    sameTags.push(siblings[i]);
                }
            }
            if (sameTags.length > 1) {
                ctx.nth = idx;
                ctx.nth_total = sameTags.length;
            }
        }

        // 3. 表格 / 网格单元格上下文
        const td = el.closest("td, th, [role='cell'], [role='gridcell']");
        if (td) {
            const tr = td.closest("tr, [role='row']");
            if (tr && tr.parentElement) {
                const rows = tr.parentElement.children;
                const cols = tr.children;
                let rowIdx = -1, colIdx = -1;
                for (let i = 0; i < rows.length; i++) { if (rows[i] === tr) { rowIdx = i; break; } }
                for (let i = 0; i < cols.length; i++) { if (cols[i] === td) { colIdx = i; break; } }
                ctx.table_cell = { row: rowIdx, col: colIdx, row_count: rows.length, col_count: cols.length };
            }
        }

        // 4. 弹层 / 下拉容器识别
        const popupSel = ".el-dropdown-menu, .el-cascader-menus, .el-select-dropdown, .el-popper, " +
            ".el-dialog, .el-drawer, .el-popover, " +
            ".ant-dropdown, .ant-select-dropdown, .ant-cascader-menus, .ant-modal, .ant-drawer, .ant-popover, " +
            ".n-base-select-menu, .n-cascader-menu, .n-modal, .n-drawer, " +
            "[role='menu'], [role='listbox'], [role='dialog'], [role='tree']";
        try {
            const popup = el.closest(popupSel);
            if (popup) {
                const popCls = (popup.className || "").trim().split(/\s+/).filter(Boolean).slice(0, 3).join(" ");
                const popRole = (popup.getAttribute && popup.getAttribute("role")) || "";
                ctx.popup_container = { class: popCls, role: popRole || undefined, tag: popup.tagName.toLowerCase() };
            }
        } catch (e) {}

        // 5. data-* 属性（过滤掉 vue 内部的 data-v-xxx）
        try {
            const dAttrs = {};
            for (let i = 0; i < el.attributes.length; i++) {
                const a = el.attributes[i];
                if (a.name.startsWith("data-") && a.value && !/^data-v-/.test(a.name)) {
                    dAttrs[a.name] = a.value.substring(0, 60);
                }
            }
            if (Object.keys(dAttrs).length) ctx.data_attrs = dAttrs;
        } catch (e) {}

        // 6. aria 属性补充
        try {
            const ariaLabel = el.getAttribute("aria-label");
            const title = el.getAttribute("title");
            if (ariaLabel) ctx.aria_label = ariaLabel.substring(0, 60);
            if (title) ctx.title = title.substring(0, 60);
        } catch (e) {}

        return Object.keys(ctx).length ? ctx : null;
    }

    function record(step) {
        if (paused) return;
        // 滚动步骤不受硬上限限制（但计数照常 +1）
        if (step.action_type !== "scroll" && stepCount >= MAX_STEPS + 20) return;
        stepCount++;
        step.step_index = stepCount;
        step.url = location.href;
        // 兜底定位
        try {
            if (step._el) {
                try {
                    const rect = step._el.getBoundingClientRect();
                    const cx = Number.isFinite(step.click_x) ? step.click_x : (rect.left + rect.width / 2);
                    const cy = Number.isFinite(step.click_y) ? step.click_y : (rect.top + rect.height / 2);
                    step.target_box = {
                        x: Math.round(rect.left),
                        y: Math.round(rect.top),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        cx: Math.round(cx),
                        cy: Math.round(cy),
                    };
                    step.viewport = getViewportData();
                } catch (e) {}
                step.xpath = getXPath(step._el);
                // 优先用 click handler 已经算好的 scoped_hint，避免重复计算
                let scoped = step._scoped_hint;
                if (!scoped) {
                    try { scoped = scopedSelector(step._el); } catch (e) {}
                }
                if (scoped) step.scoped_selector = scoped;
                // DOM 上下文（提升菜单/单元格/弹层内元素的录制精度）
                try {
                    const domCtx = captureDomContext(step._el);
                    if (domCtx) step.dom_context = domCtx;
                } catch (e) {}
            }
        } catch (e) {}
        // 无 _el 的步骤（如 scroll）也补上 viewport
        if (!step.viewport) {
            step.viewport = getViewportData();
        }
        if (!step.visual_key) {
            const matchedVisual = consumeManualVisualForStep(step);
            if (matchedVisual) {
                step.visual_key = matchedVisual.key;
                step.screenshot_match = matchedVisual.match;
            }
        }
        delete step._el;
        delete step._scoped_hint;
        updateCount();
        try { window.__hbf_record(JSON.stringify(step)); }
        catch (e) { console.error("[好办法] 上报失败:", e); }
        // 同步滚动基线，避免紧跟操作的微小滚动被误记
        lastRecordedScrollX = Math.round(window.scrollX || window.pageXOffset || 0);
        lastRecordedScrollY = Math.round(window.scrollY || window.pageYOffset || 0);
    }

    function elementAtMouse() {
        const el = document.elementFromPoint(lastMouse.x, lastMouse.y) || lastMouse.el;
        if (!el || e_isHbfElement(el)) return null;
        return findClickableTarget(el);
    }

    function manualVisualPayload(target, key) {
        const r = target.getBoundingClientRect();
        let scoped = null;
        try { scoped = scopedSelector(target); } catch (err) {}
        return {
            visual_key: key,
            manual: true,
            created_at: Date.now(),
            click_x: Math.round(lastMouse.x),
            click_y: Math.round(lastMouse.y),
            selector: bestSelector(target),
            xpath: getXPath(target),
            scoped_selector: scoped || "",
            label: elementLabel(target),
            text: elementText(target).substring(0, 30),
            target_box: {
                x: Math.round(r.left),
                y: Math.round(r.top),
                width: Math.round(r.width),
                height: Math.round(r.height),
                cx: Math.round(lastMouse.x),
                cy: Math.round(lastMouse.y),
            },
            viewport: getViewportData(),
        };
    }

    function captureManualVisual() {
        if (paused) return;
        const target = elementAtMouse();
        if (!target || !target.tagName) {
            showToast("没有识别到鼠标下的网页元素", "#dc2626");
            return;
        }
        const key = Date.now() + "_" + Math.random().toString(36).slice(2, 10);
        const payload = manualVisualPayload(target, key);
        try {
            window.__hbf_prepare_visual(JSON.stringify(payload));
            manualVisuals.push(payload);
            manualVisuals = manualVisuals.slice(-12);
            showToast("截图已保存，请在 3-5 秒内点击同一目标完成关联", "#2563eb");
        } catch (err) {
            showToast("截图请求失败", "#dc2626");
        }
    }

    function consumeManualVisualForStep(step) {
        const now = Date.now();
        let best = null;
        let bestScore = -1;
        let bestIndex = -1;
        manualVisuals = manualVisuals.filter(v => now - Number(v.created_at || now) <= MANUAL_NEXT_MATCH_MS);
        manualVisuals.forEach((v, idx) => {
            let score = 0;
            if (v.xpath && step.xpath && v.xpath === step.xpath) score += 100;
            if (v.scoped_selector && step.scoped_selector && v.scoped_selector === step.scoped_selector) score += 80;
            if (v.selector && step.selector && v.selector === step.selector) score += 60;
            if (Number.isFinite(v.click_x) && Number.isFinite(step.click_x)
                && Number.isFinite(v.click_y) && Number.isFinite(step.click_y)) {
                const dx = Number(v.click_x) - Number(step.click_x);
                const dy = Number(v.click_y) - Number(step.click_y);
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist <= 60) score += 50;
                else if (dist <= 160) score += 25;
            }
            const age = now - Number(v.created_at || now);
            if (age <= MANUAL_NEXT_MATCH_MS) score += Math.max(0, 15 - age / 1000);
            if (score > bestScore) {
                bestScore = score;
                best = v;
                bestIndex = idx;
            }
        });
        if (!best || bestScore < 25) return null;
        manualVisuals.splice(bestIndex, 1);
        return {
            key: best.visual_key,
            match: {
                type: "manual_before_click",
                score: Math.round(bestScore),
                delta_ms: Date.now() - Number(best.created_at || Date.now()),
            },
        };
    }

    document.addEventListener("mousemove", function (e) {
        lastMouse = { x: e.clientX, y: e.clientY, el: e.target, time: Date.now() };
    }, true);

    document.addEventListener("keydown", function (e) {
        if (e.ctrlKey && e.shiftKey && !e.altKey && (e.key || "").toLowerCase() === "x") {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            captureManualVisual();
        }
    }, true);

    /* ───── 上传触发器静态识别 ─────
       某些 DOM 结构本质上就是上传触发，不用等 change 事件：
         • <label for="file-input-id">
         • <label><input type="file">...</label>
         • <div class="el-upload">...<input type="file">...</div>
         • <div class="ant-upload">...
       这种结构点击必然弹文件对话框，直接当 upload 步骤记录最稳。

       为了保险：只匹配明确的"上传容器"类名 + 内部确实有 file input。 */
    const UPLOAD_CONTAINER_RE = /(^|\s)(el-upload(__\S*)?|ant-upload(-\S*)?|n-upload(__\S*)?|van-uploader(__\S*)?|upload(er)?(__\S*)?|file-upload(er)?|btn-upload)(\s|$)/i;

    function isUploadTrigger(el) {
        if (!el || !el.tagName) return null;

        // 关键：如果 el 自身就是 input[type=file]，跳过静态识别
        // 这种情况说明：刚才已经识别过外层 label/upload container 并 record 过了，
        // 现在是浏览器把 click 转发给隐藏的 input，要让它走到 case 4 默默 return
        if (el.tagName.toLowerCase() === "input") {
            const t = (el.getAttribute("type") || el.type || "").toLowerCase();
            if (t === "file") return null;
        }

        // 从 el 自身往上找最多 5 层（捕获 span 在 div.el-upload 里的情况）
        let cur = el;
        for (let i = 0; i < 5 && cur && cur !== document.body; i++) {
            const tag = cur.tagName.toLowerCase();
            const cls = (cur.className && typeof cur.className === "string") ? cur.className : "";

            // label[for] 指向 file input
            if (tag === "label") {
                const forId = cur.getAttribute("for");
                if (forId) {
                    try {
                        const target = document.getElementById(forId);
                        if (target && target.tagName === "INPUT" &&
                            (target.getAttribute("type") || target.type || "").toLowerCase() === "file") {
                            return { container: cur, fileInput: target };
                        }
                    } catch (err) {}
                }
            }

            // 是已知的上传容器类（el-upload / ant-upload 等）
            // 或 label 包裹（不限于框架）
            const isUploadContainer = tag === "label" || UPLOAD_CONTAINER_RE.test(cls);
            if (isUploadContainer) {
                try {
                    // 在这个容器内部找 file input（任意深度，因为框架包很多层）
                    const inner = cur.querySelector('input[type="file"], input[type="FILE"]');
                    if (inner) {
                        return { container: cur, fileInput: inner };
                    }
                } catch (err) {}
            }

            cur = cur.parentElement;
        }

        return null;
    }

    /* ───── 点击监听 ─────
       核心原则：用户每点一下都要记录，绝不省略，绝不去重。
       去重的责任在用户的"撤销"按钮，不在我们这里偷做主。
       下拉/多级菜单/搜索框/隐藏选项都是多步操作，漏掉任何一步都会让脚本跑不通。 */
    document.addEventListener("click", function (e) {
        if (e_isHbfElement(e.target)) return;
        if (paused) return;

        // 浏览器层面的双发事件保护（< 50ms 同一目标视为一次）
        // 注意：这只挡浏览器抽风，挡不住用户连点 —— 用户的连点都必须记录
        const tNow = Date.now();
        if (tNow - lastClickTime < 50 && e.target === window.__hbf_lastTarget) {
            return;
        }
        lastClickTime = tNow;
        window.__hbf_lastTarget = e.target;

        // 提升到可点击祖先（span → button）
        const el = findClickableTarget(e.target);
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute("type") || "").toLowerCase();

        // ───── 0. 上传触发器预检测（label / el-upload / ant-upload 等）─────
        // 这种结构点了一定会弹文件对话框，直接当 upload 步骤记录，不用等 change 事件
        const uploadDetect = isUploadTrigger(el);
        if (uploadDetect && uploadDetect.fileInput && uploadDetect.container) {
            const ucontainer = uploadDetect.container;
            const ufileInput = uploadDetect.fileInput;
            let uploadSel = "";
            try { uploadSel = bestSelector(ucontainer); } catch (err) { uploadSel = 'input[type="file"]'; }
            let uploadScoped = null;
            try { uploadScoped = scopedSelector(ucontainer); } catch (err) {}
            const isMulti = !!ufileInput.multiple;
            record({
                action_type: "upload",
                action_label: isMulti ? "上传文件（multiple）" : "上传文件",
                selector: uploadSel,
                label: elementLabel(ucontainer) || elementLabel(ufileInput) || "文件上传",
                text: elementText(ucontainer).substring(0, 30),
                tag: ucontainer.tagName.toLowerCase(),
                input_type: "file",
                triggers_file_chooser: true,
                files_count_recorded: 0,  // 静态识别时还没选文件
                click_x: Math.round(e.clientX),
                click_y: Math.round(e.clientY),
                _el: ucontainer,
                _scoped_hint: uploadScoped && uploadScoped !== uploadSel ? uploadScoped : null,
            });
            flash(ucontainer);
            // 清空 lastClickInfo，防止后续 change 事件再升级一次
            lastClickInfo = null;
            // 标记跳过：让 change 事件不要再创建一条 upload
            window.__hbf_skipNextChange = ufileInput;
            return;
        }

        // ───── 1. checkbox / radio ─────
        if (tag === "input" && (type === "checkbox" || type === "radio")) {
            setTimeout(() => {
                record({
                    action_type: type === "checkbox" ? "check" : "click",
                    action_label: type === "checkbox" ? "勾选" : "选择",
                    selector: bestSelector(el),
                    label: elementLabel(el),
                    value: el.checked,
                    tag: tag,
                    click_x: Math.round(e.clientX),
                    click_y: Math.round(e.clientY),
                    _el: el,
                });
                flash(el);
            }, 0);
            return;
        }

        // ───── 2. 识别：选项 / 触发器 ─────
        const isOption = isOptionElement(el);
        const triggerNode = isOption ? null : isTriggerWrapper(el);

        // ───── 3. 决定记录目标 ─────
        const target = triggerNode || el;
        const targetTag = target.tagName.toLowerCase();

        // ───── 4. 原生输入框的 click 跳过（focus 触发，用 blur 抓最终文本）─────
        // 但 readonly input 是下拉框的"显示部分"，必须记录（点开下拉）
        if ((targetTag === "input" || targetTag === "textarea") && !isOption && !triggerNode) {
            if (!(target.readOnly || target.hasAttribute("readonly"))) {
                return;
            }
        }
        if (targetTag === "select") return;  // 原生 select 由 change 监听器处理

        // ───── 5. 生成选择器 ─────
        // 关键修复：用 scoped_selector（form-item label 锚定）当主选择器
        // 这样不管下拉框现在显示什么文字，定位都稳的
        let sel = bestSelector(target);
        let scoped = null;
        try { scoped = scopedSelector(target); } catch (err) {}

        // 不稳定 selector 的判定：text=... 或 :has-text(当前显示值)
        const unstableTextSel =
            /^text=/.test(sel) ||
            (triggerNode && sel.indexOf(':has-text(') >= 0);
        if (scoped && unstableTextSel) {
            sel = scoped;  // 用 scoped 顶上来当主
        }

        // ───── 6. action 类型 ─────
        let actionType, actionLabel;
        if (isOption) {
            actionType = "select_option";
            actionLabel = "选择菜单项";
        } else if (triggerNode) {
            actionType = "click";
            actionLabel = "打开下拉";
        } else {
            actionType = "click";
            actionLabel = "点击";
        }

        // ───── 7. 上报 ─────
        record({
            action_type: actionType,
            action_label: actionLabel,
            selector: sel,
            label: elementLabel(target),
            text: elementText(target).substring(0, 30),
            tag: targetTag,
            is_trigger: !!triggerNode,
            is_option: isOption,
            click_x: Math.round(e.clientX),
            click_y: Math.round(e.clientY),
            _el: target,
            _scoped_hint: scoped && scoped !== sel ? scoped : null,
        });

        // 记下这次 click，方便后续 input[type=file].change 把它升级为 upload
        // 只对"非选项/非触发器"的纯 click 起作用（点开下拉/选选项跟上传无关）
        if (!isOption && !triggerNode) {
            lastClickInfo = {
                target: target,
                label: elementLabel(target),
                selector: sel,
                scoped: scoped,
                text: elementText(target).substring(0, 30),
                click_x: Math.round(e.clientX),
                click_y: Math.round(e.clientY),
                time: tNow,
                stepIndex: stepCount,
            };
        }
        flash(target);
    }, true);

    /* ───── 输入框失焦记录 ───── */
    const inputTracker = new WeakMap();
    document.addEventListener("focus", function (e) {
        const el = e.target;
        if (!el || !el.tagName) return;
        const tag = el.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || el.isContentEditable) {
            const type = (el.getAttribute("type") || "").toLowerCase();
            if (type === "checkbox" || type === "radio") return;
            inputTracker.set(el, el.value || el.innerText || "");
        }
    }, true);

    document.addEventListener("blur", function (e) {
        const el = e.target;
        if (!el || !el.tagName) return;
        if (e_isHbfElement(el)) return;
        const tag = el.tagName.toLowerCase();
        if (tag !== "input" && tag !== "textarea" && !el.isContentEditable) return;
        const type = (el.getAttribute("type") || "").toLowerCase();
        if (type === "checkbox" || type === "radio") return;

        // 关键：readonly / disabled 的输入不记录（这通常是 select/cascader 的显示框）
        const blurCfg = RULES.blur_record || {};
        if (blurCfg.skip_readonly !== false &&
            (el.readOnly || el.hasAttribute("readonly"))) {
            return;
        }
        if (blurCfg.skip_disabled !== false && el.disabled) return;

        const newVal = el.value !== undefined ? el.value : (el.innerText || "");
        const oldVal = inputTracker.get(el) || "";
        if (newVal === oldVal) return;
        if (!newVal && !oldVal) return;

        record({
            action_type: "input",
            action_label: type === "password" ? "输入密码" : "输入",
            selector: bestSelector(el),
            label: elementLabel(el),
            value: newVal,
            tag: tag,
            input_type: type || "text",
            _el: el,
        });
        flash(el);
    }, true);

    /* ───── 原生 select 的 change ───── */
    document.addEventListener("change", function (e) {
        const el = e.target;
        if (!el || !el.tagName) return;
        if (e_isHbfElement(el)) return;
        const tag = el.tagName.toLowerCase();
        if (tag !== "select") return;
        const opt = el.options[el.selectedIndex];
        record({
            action_type: "select",
            action_label: "选择",
            selector: bestSelector(el),
            label: elementLabel(el),
            value: el.value,
            text: opt ? opt.text : "",
            tag: tag,
            _el: el,
        });
        flash(el);
    }, true);

    /* ───── 📁 文件上传自动检测 ─────
       当 input[type=file] 触发 change（说明用户刚从资源管理器选完文件回来），
       回头看最近 8 秒内的 click —— 那一定是触发资源管理器的按钮。
       把那个 click 升级为 upload 步骤（撤销 + 重新记录），
       selector 用按钮，运行时走 click + file_chooser 双策略。 */
    document.addEventListener("change", function (e) {
        const el = e.target;
        if (!el || !el.tagName) return;
        if (e_isHbfElement(el)) return;
        if (el.tagName.toLowerCase() !== "input") return;
        const inputType = (el.getAttribute("type") || el.type || "").toLowerCase();
        if (inputType !== "file") return;
        if (paused) return;

        // 如果这个 input 已经被静态识别为上传触发，跳过 change 重复处理
        if (window.__hbf_skipNextChange === el) {
            window.__hbf_skipNextChange = null;
            // 更新 files_count_recorded 到刚刚记录的 upload 步（如果可能）
            // 这里简单做：让 Python 端的步骤上的 value 是文件名(选了 N 个)
            return;
        }

        const files = el.files;
        const fileCount = files ? files.length : 0;
        const sampleName = (files && files[0]) ? files[0].name : "";

        // 找最近能升级的 click（必须 8 秒内 + 同一上传上下文）
        const now = Date.now();
        let upgradeFromClick = null;
        if (lastClickInfo && (now - lastClickInfo.time) < UPLOAD_DETECT_WINDOW_MS) {
            upgradeFromClick = lastClickInfo;
        }

        // 选择器策略：
        //   - 优先用刚才那个 click 的按钮 selector（运行时走 click + file_chooser）
        //   - 兜底用 input[type=file]（运行时走 set_input_files）
        let triggerSel = "";
        let triggerLabel = "";
        let triggerScoped = "";
        let triggerText = "";
        let triggerEl = el;
        if (upgradeFromClick) {
            triggerSel = upgradeFromClick.selector;
            triggerLabel = upgradeFromClick.label;
            triggerScoped = upgradeFromClick.scoped;
            triggerText = upgradeFromClick.text;
            triggerEl = upgradeFromClick.target;
        } else {
            try { triggerSel = bestSelector(el); } catch (err) { triggerSel = 'input[type="file"]'; }
            try { triggerLabel = elementLabel(el) || "文件上传"; } catch (err) { triggerLabel = "文件上传"; }
        }

        // 撤销刚才那个 click（如果有）
        if (upgradeFromClick) {
            try { window.__hbf_undo(); } catch (err) {}
            stepCount = Math.max(0, stepCount - 1);
            updateCount();
        }

        // 录入 upload 步骤
        record({
            action_type: "upload",
            action_label: fileCount > 1 ? `上传 ${fileCount} 个文件` : "上传文件",
            selector: triggerSel,
            label: triggerLabel || "文件上传",
            text: triggerText,
            value: sampleName || `(录制时选了 ${fileCount} 个文件)`,
            tag: triggerEl.tagName.toLowerCase(),
            input_type: "file",
            triggers_file_chooser: true,
            files_count_recorded: fileCount,
            _el: triggerEl,
            _scoped_hint: triggerScoped && triggerScoped !== triggerSel ? triggerScoped : null,
        });

        // 清掉 lastClickInfo，避免再被识别一次
        lastClickInfo = null;

        flash(triggerEl);
    }, true);

    /* ───── 滚动监听（横竖都记录）─────
       用 debounce 合并连续滚动为一条记录，阈值内忽略微小抖动。
       同时监听 window scroll（主页面）和捕获阶段的 scroll（弹窗/抽屉内滚动）。 */
    function handleScrollEnd(scrollEl) {
        if (paused) return;
        let fromX, fromY, toX, toY;
        const isWindow = !scrollEl || scrollEl === window || scrollEl === document || scrollEl === document.documentElement;
        if (isWindow) {
            toX = Math.round(window.scrollX || window.pageXOffset || 0);
            toY = Math.round(window.scrollY || window.pageYOffset || 0);
            fromX = lastRecordedScrollX;
            fromY = lastRecordedScrollY;
        } else {
            toX = Math.round(scrollEl.scrollLeft || 0);
            toY = Math.round(scrollEl.scrollTop || 0);
            fromX = Number(scrollEl.__hbfLastScrollX) || 0;
            fromY = Number(scrollEl.__hbfLastScrollY) || 0;
        }
        const dx = toX - fromX;
        const dy = toY - fromY;
        if (Math.abs(dx) < SCROLL_THRESHOLD && Math.abs(dy) < SCROLL_THRESHOLD) return;

        const stepData = {
            action_type: "scroll",
            action_label: "滚动页面",
            selector: "",
            label: "",
            tag: "",
            scroll_from: { x: fromX, y: fromY },
            scroll_to: { x: toX, y: toY },
            scroll_delta: { x: dx, y: dy },
        };

        if (!isWindow) {
            // 记录滚动发生在哪个容器内（弹窗/抽屉）
            try {
                const cls = (scrollEl.className || "").trim().split(/\s+/).filter(Boolean).slice(0, 3).join(" ");
                stepData.scroll_container = {
                    tag: scrollEl.tagName.toLowerCase(),
                    class: cls,
                    selector: bestSelector(scrollEl),
                };
            } catch (e) {}
            scrollEl.__hbfLastScrollX = toX;
            scrollEl.__hbfLastScrollY = toY;
        }

        record(stepData);
    }

    // 主页面滚动
    let winScrollTimer = null;
    window.addEventListener("scroll", function () {
        if (paused) return;
        clearTimeout(winScrollTimer);
        winScrollTimer = setTimeout(function () { handleScrollEnd(null); }, 400);
    }, { passive: true });

    // 捕获阶段：弹窗 / 抽屉 / 可滚动面板内部的滚动
    let containerScrollTimer = null;
    let containerScrollTarget = null;
    document.addEventListener("scroll", function (e) {
        if (paused) return;
        const t = e.target;
        if (!t || t === document || t === document.documentElement) return;
        if (e_isHbfElement(t)) return;
        containerScrollTarget = t;
        clearTimeout(containerScrollTimer);
        containerScrollTimer = setTimeout(function () {
            handleScrollEnd(containerScrollTarget);
        }, 400);
    }, { capture: true, passive: true });

    updateCount();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", __hbf_init);
    setTimeout(__hbf_init, 100);
} else {
    __hbf_init();
}
