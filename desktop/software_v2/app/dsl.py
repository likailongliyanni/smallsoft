"""
JSON 指令解释器（多策略定位 + 可见性过滤）
"""

import threading
import time
from pathlib import Path
from typing import Callable, Optional


class DSLError(Exception):
    pass


START_BUTTON_JS = """
() => {
    if (document.getElementById('__hbf_start_btn')) return;
    const style = document.createElement('style');
    style.id = '__hbf_start_style';
    style.textContent = `
        @keyframes hbf-pulse {
            0%, 100% { transform: translateX(-50%) scale(1); box-shadow: 0 8px 24px rgba(22,163,74,0.4); }
            50% { transform: translateX(-50%) scale(1.06); box-shadow: 0 12px 32px rgba(22,163,74,0.6); }
        }
    `;
    document.head.appendChild(style);

    const btn = document.createElement('div');
    btn.id = '__hbf_start_btn';
    btn.innerHTML = '▶ 开始工作';
    btn.style.cssText = `
        position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
        z-index: 2147483647; background: #16a34a; color: white;
        padding: 14px 36px; border-radius: 12px; font-size: 17px;
        font-weight: 700; cursor: pointer;
        font-family: "Microsoft YaHei", sans-serif; user-select: none;
        animation: hbf-pulse 2s infinite;
    `;

    const tip = document.createElement('div');
    tip.id = '__hbf_start_tip';
    tip.style.cssText = `
        position: fixed; top: 78px; left: 50%; transform: translateX(-50%);
        z-index: 2147483646; background: rgba(0,0,0,0.82); color: white;
        padding: 8px 18px; border-radius: 8px;
        font-family: "Microsoft YaHei"; font-size: 13px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    `;
    tip.textContent = '请完成登录/导航等准备工作，然后点击上方按钮开始执行';
    document.body.appendChild(tip);

    btn.onclick = () => {
        btn.remove();
        tip.remove();
        try { window.__hbf_user_start(); } catch(e) {}
    };
    document.body.appendChild(btn);
}
"""

REMOVE_BUTTON_JS = """
() => {
    const b = document.getElementById('__hbf_start_btn'); if (b) b.remove();
    const t = document.getElementById('__hbf_start_tip'); if (t) t.remove();
    const s = document.getElementById('__hbf_start_style'); if (s) s.remove();
}
"""

MANUAL_DIALOG_DRAG_INIT_JS = """
() => {
    if (window.__hbf_setup_dialog_drag) return;
    window.__hbf_setup_dialog_drag = function (box) {
        if (!box || box.__hbf_drag_inited) return;
        box.__hbf_drag_inited = true;

        const POS_KEY = '__hbf_manual_pos_v1';
        const FADE_MS = 3500;

        // 顶部加一个拖柄横条
        const handle = document.createElement('div');
        handle.textContent = '⠿ 按住拖动 · 双击吸到顶部';
        handle.title = '按住拖动到任意位置';
        handle.style.cssText = `
            cursor: move;
            user-select: none;
            font-size: 11px;
            color: rgba(255,255,255,0.5);
            padding: 4px 0 7px;
            margin: -4px -6px 8px;
            text-align: center;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            font-family: "Microsoft YaHei", sans-serif;
            font-weight: 600;
            letter-spacing: 1px;
        `;
        box.insertBefore(handle, box.firstChild);

        // 让弹窗有透明度过渡
        box.style.transition = 'opacity 0.25s';

        // 还原上次位置
        try {
            const s = localStorage.getItem(POS_KEY);
            if (s) {
                const p = JSON.parse(s);
                if (typeof p.left === 'number' && typeof p.top === 'number') {
                    requestAnimationFrame(() => {
                        const r = box.getBoundingClientRect();
                        const left = Math.max(4, Math.min(p.left, window.innerWidth - r.width - 4));
                        const top = Math.max(4, Math.min(p.top, window.innerHeight - r.height - 4));
                        box.style.left = left + 'px';
                        box.style.top = top + 'px';
                        box.style.transform = 'none';
                    });
                }
            }
        } catch (e) {}

        // 拖动
        let dragging = false;
        let startX, startY, startLeft, startTop;
        handle.addEventListener('mousedown', e => {
            if (e.button !== 0) return;
            e.preventDefault();
            e.stopPropagation();
            dragging = true;
            const r = box.getBoundingClientRect();
            startX = e.clientX; startY = e.clientY;
            startLeft = r.left; startTop = r.top;
            box.style.transform = 'none';
            document.body.style.userSelect = 'none';
            box.style.opacity = '1';
        });
        document.addEventListener('mousemove', e => {
            if (!dragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            const r = box.getBoundingClientRect();
            const left = Math.max(4, Math.min(startLeft + dx, window.innerWidth - r.width - 4));
            const top = Math.max(4, Math.min(startTop + dy, window.innerHeight - r.height - 4));
            box.style.left = left + 'px';
            box.style.top = top + 'px';
        }, true);
        document.addEventListener('mouseup', e => {
            if (!dragging) return;
            dragging = false;
            document.body.style.userSelect = '';
            const r = box.getBoundingClientRect();
            try {
                localStorage.setItem(POS_KEY, JSON.stringify({
                    left: Math.round(r.left),
                    top: Math.round(r.top)
                }));
            } catch (e) {}
        }, true);

        // 双击拖柄 → 吸回顶部居中
        handle.addEventListener('dblclick', e => {
            e.preventDefault();
            e.stopPropagation();
            const r = box.getBoundingClientRect();
            const left = Math.max(4, Math.round((window.innerWidth - r.width) / 2));
            const top = 18;
            box.style.left = left + 'px';
            box.style.top = top + 'px';
            box.style.transform = 'none';
            try {
                localStorage.setItem(POS_KEY, JSON.stringify({ left, top }));
            } catch (e) {}
        });

        // 鼠标移开 N 秒后半透明，移入恢复
        let fadeTimer = null;
        function scheduleFade() {
            if (fadeTimer) clearTimeout(fadeTimer);
            box.style.opacity = '1';
            fadeTimer = setTimeout(() => {
                if (!dragging && box.parentElement) box.style.opacity = '0.35';
            }, FADE_MS);
        }
        box.addEventListener('mouseenter', () => {
            if (fadeTimer) clearTimeout(fadeTimer);
            box.style.opacity = '1';
        });
        box.addEventListener('mouseleave', scheduleFade);
        scheduleFade();
    };
}
"""

MANUAL_CHECKPOINT_PROMPT_JS = """
({index, skip}) => {
    const old = document.getElementById('__hbf_manual_pause');
    if (old) old.remove();
    window.__hbf_manual_decision = null;

    const box = document.createElement('div');
    box.id = '__hbf_manual_pause';
    box.style.cssText = `
        position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
        z-index: 2147483647; width: min(720px, calc(100vw - 32px));
        background: #111827; color: #fff; border-radius: 12px;
        padding: 14px 16px; font-family: "Microsoft YaHei", sans-serif;
        box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    `;
    box.innerHTML = `
        <div style="font-weight:700;font-size:15px;margin-bottom:6px;">第 ${index} 步已完成</div>
        <div style="font-size:13px;line-height:1.5;color:#e5e7eb;margin-bottom:10px;">
            是否从这里开始人工介入？如果选择人工介入，后续每一轮都会在第 ${index} 步完成后暂停。一个流程可以设置多个介入点。
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button id="__hbf_manual_never" style="border:0;border-radius:7px;padding:8px 14px;background:#4b5563;color:#fff;font-weight:700;cursor:pointer;">本轮不再提示</button>
            <button id="__hbf_manual_skip" style="border:0;border-radius:7px;padding:8px 14px;background:#2563eb;color:#fff;font-weight:700;cursor:pointer;">接下来 ${skip} 步不提示</button>
            <button id="__hbf_manual_yes" style="border:0;border-radius:7px;padding:8px 14px;background:#16a34a;color:#fff;font-weight:700;cursor:pointer;">从这里人工介入</button>
        </div>
    `;
    document.body.appendChild(box);
    if (window.__hbf_setup_dialog_drag) window.__hbf_setup_dialog_drag(box);
    document.getElementById('__hbf_manual_yes').onclick = () => {
        window.__hbf_manual_decision = 'manual';
        box.remove();
    };
    document.getElementById('__hbf_manual_skip').onclick = () => {
        window.__hbf_manual_decision = 'skip';
        box.remove();
    };
    document.getElementById('__hbf_manual_never').onclick = () => {
        window.__hbf_manual_decision = 'never';
        box.remove();
    };
}
"""

MANUAL_RECORDER_INIT_JS = """
() => {
    // 静默样本记录器：人工接管期间记录用户的点击/输入
    if (window.__hbf_manual_recorder_inited) return;
    window.__hbf_manual_recorder_inited = true;
    window.__hbf_manual_actions = [];
    window.__hbf_manual_recording = false;

    function _shortText(el, max) {
        return ((el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, max || 50));
    }

    function _getXPath(el) {
        if (!el || el.nodeType !== 1) return '';
        if (el.id && el.id.length < 40 && !/^(__|el-id-|n-id-|ant-)/.test(el.id))
            return `//*[@id="${el.id}"]`;
        if (el === document.documentElement) return '/html';
        if (el === document.body) return '/html/body';
        const parts = [];
        let n = el;
        while (n && n.nodeType === 1 && n !== document.body && n !== document.documentElement) {
            let idx = 1;
            let sib = n.previousElementSibling;
            while (sib) { if (sib.tagName === n.tagName) idx++; sib = sib.previousElementSibling; }
            const tag = n.tagName.toLowerCase();
            parts.unshift(tag + (idx > 1 ? `[${idx}]` : ''));
            n = n.parentElement;
        }
        return '/html/body/' + parts.join('/');
    }

    function _bestSelector(el) {
        if (!el || !el.tagName) return '';
        const tag = el.tagName.toLowerCase();
        if (el.id && el.id.length < 40 && !/^(__|el-id-|n-id-|ant-)/.test(el.id))
            return '#' + el.id.replace(/"/g, '\\\\"');
        for (const attr of ['data-testid', 'data-cy', 'data-test', 'data-id', 'name']) {
            const v = el.getAttribute(attr);
            if (v) return `[${attr}="${v}"]`;
        }
        if (tag === 'button' || tag === 'a') {
            const text = _shortText(el, 30);
            if (text) return `${tag}:has-text("${text.replace(/"/g, '\\\\"')}")`;
        }
        if (tag === 'input' || tag === 'textarea') {
            const ph = el.getAttribute('placeholder');
            if (ph) return `${tag}[placeholder="${ph}"]`;
        }
        if (el.className && typeof el.className === 'string') {
            const cls = el.className.trim().split(/\\s+/).filter(c => c.length > 3 && !/^(el-|ant-|n-|van-)/.test(c));
            if (cls.length) return tag + '.' + cls[0];
        }
        return tag;
    }

    function _findClickable(el) {
        let n = el;
        for (let i = 0; i < 6 && n && n !== document.body; i++) {
            const tag = n.tagName ? n.tagName.toLowerCase() : '';
            if (tag === 'button' || tag === 'a') return n;
            const role = n.getAttribute ? n.getAttribute('role') : '';
            if (['button', 'link', 'menuitem', 'option', 'tab'].includes(role)) return n;
            n = n.parentElement;
        }
        return el;
    }

    function _isHbfDialog(el) {
        return !!(el.closest && el.closest('#__hbf_manual_pause'));
    }

    function _record(type, el, extra) {
        if (!window.__hbf_manual_recording) return;
        if (!el || _isHbfDialog(el)) return;
        try {
            const r = el.getBoundingClientRect();
            const action = Object.assign({
                type: type,
                t: Date.now() - window.__hbf_manual_recording_start_t,
                tag: el.tagName ? el.tagName.toLowerCase() : '',
                selector: _bestSelector(el),
                xpath: _getXPath(el),
                text: _shortText(el),
                target_box: {
                    x: Math.round(r.left), y: Math.round(r.top),
                    width: Math.round(r.width), height: Math.round(r.height),
                },
                url: location.href,
            }, extra || {});
            window.__hbf_manual_actions.push(action);
        } catch (e) {}
    }

    // 监听点击
    document.addEventListener('click', function(e) {
        if (!window.__hbf_manual_recording) return;
        const target = _findClickable(e.target);
        _record('click', target, {
            click_x: Math.round(e.clientX),
            click_y: Math.round(e.clientY),
        });
    }, true);

    // 监听输入框失焦
    const _inputBefore = new WeakMap();
    document.addEventListener('focus', function(e) {
        const el = e.target;
        if (!el || !el.tagName) return;
        const tag = el.tagName.toLowerCase();
        if (tag === 'input' || tag === 'textarea')
            _inputBefore.set(el, el.value || '');
    }, true);
    document.addEventListener('blur', function(e) {
        if (!window.__hbf_manual_recording) return;
        const el = e.target;
        if (!el || !el.tagName) return;
        const tag = el.tagName.toLowerCase();
        if (tag !== 'input' && tag !== 'textarea') return;
        const newVal = el.value || '';
        const oldVal = _inputBefore.get(el) || '';
        if (newVal === oldVal || (!newVal && !oldVal)) return;
        _record('input', el, { value: newVal });
    }, true);

    // 监听原生 select
    document.addEventListener('change', function(e) {
        if (!window.__hbf_manual_recording) return;
        const el = e.target;
        if (!el || el.tagName !== 'SELECT') return;
        _record('select', el, {
            value: el.value,
            selected_text: (el.options[el.selectedIndex] || {}).text || '',
        });
    }, true);
}
"""

MANUAL_RECOVERY_JS = """
({index, stepType, errorMsg, hasRow}) => {
    const old = document.getElementById('__hbf_manual_pause');
    if (old) old.remove();
    window.__hbf_manual_decision = null;

    const box = document.createElement('div');
    box.id = '__hbf_manual_pause';
    box.style.cssText = `
        position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
        z-index: 2147483647; width: min(820px, calc(100vw - 32px));
        background: #7f1d1d; color: #fff; border-radius: 12px;
        padding: 16px 18px; font-family: "Microsoft YaHei", sans-serif;
        box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        border: 2px solid #fca5a5;
    `;

    const skipRowBtn = hasRow
        ? `<button id="__hbf_skip_row" style="border:0;border-radius:7px;padding:9px 14px;background:#0369a1;color:#fff;font-weight:700;cursor:pointer;">⏭ 跳过本行</button>`
        : '';

    box.innerHTML = `
        <div style="font-weight:700;font-size:15px;margin-bottom:8px;display:flex;align-items:center;gap:8px;">
            <span style="background:#fbbf24;color:#7c2d12;padding:2px 8px;border-radius:4px;font-size:12px;">人工接管</span>
            第 ${index} 步（${stepType}）出错，已暂停
        </div>
        <div style="font-size:13px;color:#fff;line-height:1.6;margin-bottom:8px;">
            请在浏览器里<b>手动完成当前操作</b>（或修正错误状态），完成后选择：
        </div>
        <pre style="font-size:12px;line-height:1.5;color:#fecaca;margin:0 0 12px;max-height:140px;overflow:auto;background:#450a0a;padding:8px 10px;border-radius:6px;white-space:pre-wrap;word-break:break-all;">${errorMsg}</pre>
        <div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">
            <button id="__hbf_stop" style="border:0;border-radius:7px;padding:9px 14px;background:#4b5563;color:#fff;font-weight:700;cursor:pointer;">🛑 停止运行</button>
            ${skipRowBtn}
            <button id="__hbf_skip_step" style="border:0;border-radius:7px;padding:9px 14px;background:#7c3aed;color:#fff;font-weight:700;cursor:pointer;">⏩ 跳过这步</button>
            <button id="__hbf_retry" style="border:0;border-radius:7px;padding:9px 14px;background:#f59e0b;color:#fff;font-weight:700;cursor:pointer;">🔁 重试当前步</button>
            <button id="__hbf_continue" style="border:0;border-radius:7px;padding:9px 16px;background:#16a34a;color:#fff;font-weight:700;cursor:pointer;font-size:14px;">✅ 已手动完成 → 下一步</button>
        </div>
    `;
    document.body.appendChild(box);
    if (window.__hbf_setup_dialog_drag) window.__hbf_setup_dialog_drag(box);
    document.getElementById('__hbf_continue').onclick = () => { window.__hbf_manual_decision = 'continue'; box.remove(); };
    document.getElementById('__hbf_retry').onclick = () => { window.__hbf_manual_decision = 'retry'; box.remove(); };
    document.getElementById('__hbf_skip_step').onclick = () => { window.__hbf_manual_decision = 'skip_step'; box.remove(); };
    if (hasRow) {
        document.getElementById('__hbf_skip_row').onclick = () => { window.__hbf_manual_decision = 'skip_row'; box.remove(); };
    }
    document.getElementById('__hbf_stop').onclick = () => { window.__hbf_manual_decision = 'stop'; box.remove(); };
}
"""

MANUAL_TASK_JS = """
({index}) => {
    const old = document.getElementById('__hbf_manual_pause');
    if (old) old.remove();
    window.__hbf_manual_decision = null;

    const box = document.createElement('div');
    box.id = '__hbf_manual_pause';
    box.style.cssText = `
        position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
        z-index: 2147483647; width: min(720px, calc(100vw - 32px));
        background: #111827; color: #fff; border-radius: 12px;
        padding: 14px 16px; font-family: "Microsoft YaHei", sans-serif;
        box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    `;
    box.innerHTML = `
        <div style="font-weight:700;font-size:15px;margin-bottom:6px;">人工介入：第 ${index} 步后暂停</div>
        <div style="font-size:13px;line-height:1.5;color:#e5e7eb;margin-bottom:10px;">
            请在页面上手动完成这部分工作。完成后点击「继续执行剩余步骤」。
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button id="__hbf_manual_stop" style="border:0;border-radius:7px;padding:8px 14px;background:#dc2626;color:#fff;font-weight:700;cursor:pointer;">停止运行</button>
            <button id="__hbf_manual_continue" style="border:0;border-radius:7px;padding:8px 14px;background:#16a34a;color:#fff;font-weight:700;cursor:pointer;">继续执行剩余步骤</button>
        </div>
    `;
    document.body.appendChild(box);
    if (window.__hbf_setup_dialog_drag) window.__hbf_setup_dialog_drag(box);
    document.getElementById('__hbf_manual_continue').onclick = () => {
        window.__hbf_manual_decision = 'continue';
        box.remove();
    };
    document.getElementById('__hbf_manual_stop').onclick = () => {
        window.__hbf_manual_decision = 'stop';
        box.remove();
    };
}
"""


def _pick_visible_frame(page):
    """挑一个用户「看得见」的 frame 来放开始按钮。

    聚水潭订单页是 frameset：主 frame 是空壳（用户看不到），真正的内容在子
    iframe 里。如果把按钮画进主 frame，用户根本看不到「开始工作」按钮。
    这里选视口面积最大的 frame（主内容页几乎总是最大的那个）。
    普通单页站点只有主 frame，自然就返回主 frame，行为不变。
    """
    best = None
    best_area = -1
    try:
        frames = list(page.frames)
    except Exception:
        frames = []
    for fr in frames:
        try:
            if fr.is_detached():
                continue
            size = fr.evaluate(
                "() => (document && document.body) "
                "? [window.innerWidth||0, window.innerHeight||0] : [0,0]")
            area = (size[0] or 0) * (size[1] or 0)
            if area > best_area:
                best_area = area
                best = fr
        except Exception:
            continue
    return best or page.main_frame


def wait_for_user_start(page, on_log: Optional[Callable[[str], None]] = None) -> bool:
    started = threading.Event()
    # binding 在 context 级注册（对所有 frame 生效），按钮按钮点击才能回调到 Python
    try:
        page.context.expose_function("__hbf_user_start", lambda: started.set())
    except Exception:
        # 已注册过 / 不支持 context 级别时，退回 page 级
        try:
            page.expose_function("__hbf_user_start", lambda: started.set())
        except Exception:
            pass

    target = _pick_visible_frame(page)
    try:
        target.evaluate(START_BUTTON_JS)
    except Exception:
        # 兜底：主 frame 再画一次，至少不会完全没有按钮
        try:
            page.evaluate(START_BUTTON_JS)
        except Exception:
            pass
    if on_log:
        on_log("⏸ 等待用户点击「开始工作」按钮...")
    while not started.is_set():
        try:
            page.wait_for_timeout(400)
        except Exception:
            return False
    # 移除按钮：所有 frame 都清一遍（不确定画在哪个 frame）
    try:
        for fr in list(page.frames):
            try:
                fr.evaluate(REMOVE_BUTTON_JS)
            except Exception:
                continue
    except Exception:
        pass
    if on_log:
        on_log("▶ 用户已确认，开始执行")
    return True


class Interpreter:
    """JSON 指令解释器（多策略定位 + 远程可配）"""

    def __init__(self, page, on_log: Optional[Callable[[str], None]] = None,
                 runner_config: Optional[dict] = None,
                 learning_dir: Optional[Path] = None):
        self.page = page
        self.on_log = on_log or (lambda s: None)
        # 学习样本存储目录（人工接管时录到的操作往这里存）
        # 通常 = 流程目录（runner 传入），不传则不存样本
        self.learning_dir = learning_dir
        cfg = runner_config or {}
        self.default_timeout = cfg.get("default_timeout_ms", 15000)
        self.poll_ms = cfg.get("find_visible_poll_ms", 250)
        self.max_loops = cfg.get("find_visible_max_loops", 60)
        self.select_wait = cfg.get("select_option_wait_after_ms", 400)
        self.click_wait = cfg.get("click_wait_after_ms", 600)
        self.fill_fallback = cfg.get("fill_retry_with_type", True)
        self.manual_checkpoint_enabled = cfg.get("manual_checkpoint_enabled", True)
        self.manual_prompt_skip_steps = int(cfg.get("manual_prompt_skip_steps", 5))
        self.manual_after_indices: set[int] = set()
        self._manual_prompt_skip_until = 0
        # select_option 类型执行前主动等下拉菜单出现（动画/数据加载）
        # 多级菜单各级数据量差异大，默认放到 800ms 更保险
        self.select_pre_wait = cfg.get("select_option_pre_wait_ms", 800)
        self._last_fill_action: Optional[dict] = None
        self._last_fill_value = ""
        self._last_fill_at = 0.0

    def log(self, msg: str):
        try:
            self.on_log(msg)
        except Exception:
            pass

    SEARCHABLE_DROPDOWN_KEYWORDS = (
        "品牌", "brand", "制造商", "厂家", "产地品牌",
        "供应商", "经销商", "商家", "物流商",
        "地区", "省", "市", "区", "region",
        "分类", "类目", "category",
        "材质", "款式", "颜色", "系列", "型号",
        "sku", "spu", "搜索", "过滤",
    )

    def _looks_like_searchable_dropdown_fill(self, action: dict) -> bool:
        text = " ".join(
            str(action.get(k, ""))
            for k in ("selector", "scoped_selector", "from_excel", "label", "description")
        )
        low = text.lower()
        has_keyword = any(k in text or k in low for k in self.SEARCHABLE_DROPDOWN_KEYWORDS)
        has_dropdown_hint = any(
            k in low
            for k in ("select", "combobox", "dropdown", "cascader", "picker", "avue", "n-base")
        )
        # 生成器给可搜索下拉的 fill 通常会带 wait_after=600；普通文本输入一般没有。
        return has_keyword and (has_dropdown_hint or bool(action.get("wait_after")))

    def _wait_after_if_needed(self, action: dict):
        wait_after = action.get("wait_after")
        if wait_after:
            try:
                self.page.wait_for_timeout(int(wait_after))
            except Exception:
                pass

    def _type_into_search_input(self, action: dict, text: str) -> bool:
        """给可搜索下拉的输入框打字；用于品牌/供应商等远程搜索下拉。"""
        if not text:
            return False
        try:
            item, _used = self._find_visible_locator(action, 3000)
            item.click(timeout=2500, force=True)
            self.page.wait_for_timeout(120)
            eh = item.element_handle()
            try:
                self.page.evaluate(
                    """(el) => {
                        if (!el) return;
                        el.removeAttribute('readonly');
                        el.readOnly = false;
                        el.removeAttribute('disabled');
                        el.disabled = false;
                        el.focus();
                    }""",
                    eh
                )
            except Exception:
                pass

            try:
                self.page.keyboard.press("Control+A")
                self.page.keyboard.insert_text(text)
            except Exception:
                self.page.evaluate(
                    """(args) => {
                        const el = args.el;
                        if (!el) return;
                        const proto = el instanceof HTMLTextAreaElement
                            ? window.HTMLTextAreaElement.prototype
                            : window.HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                        if (setter) setter.call(el, args.value);
                        else el.value = args.value;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
                    }""",
                    {"el": eh, "value": text}
                )
            return True
        except Exception as e:
            self.log(f"  搜索输入兜底失败: {e}")
            return False

    def _resolve(self, action: dict, row: Optional[dict]) -> str:
        if "from_excel" in action and row is not None:
            col = action["from_excel"]
            v = row.get(col, "")
            return "" if v is None else str(v)
        return str(action.get("value", ""))

    # ────────────────────────────────────────────────
    #  「学习资料」吸收的招数 - 解决 click 卡 30s 问题
    # ────────────────────────────────────────────────
    #  根因：Playwright 的 text="X" 会定位到文字所在的最小元素（通常是 <span>），
    #        但 <span> 没有 click 事件 / pointer-events: none / 被覆盖，
    #        于是 Playwright 的 actionability 检查死循环 → 30s 超时
    #
    #  招 1：smart_select_match() —— 生成"找父级容器"的 CSS + XPath
    #  招 2：_click_via_js() —— 用 JS dispatchEvent 直接派发合成事件，绕过 actionability
    # ────────────────────────────────────────────────

    # 下拉/菜单"可点击容器" class 列表
    _OPTION_CONTAINER_CLASSES = [
        "el-cascader-node",
        "el-cascader-menu__item",
        "el-select-dropdown__item",
        "el-dropdown-menu__item",
        "ant-cascader-menu-item",
        "ant-select-item-option",
        "ant-dropdown-menu-item",
        "avue-cascader-node",
        "avue-select-dropdown__item",
        "n-base-select-option",
        "n-cascader-option",
        "van-picker-column__item",
    ]

    @staticmethod
    def _xpath_literal(text: str) -> str:
        """XPath 字面量：把可能含单/双引号的字符串安全嵌入 XPath"""
        if "'" not in text:
            return f"'{text}'"
        if '"' not in text:
            return f'"{text}"'
        # 两种引号都有：concat('a', "'", 'b')
        parts = text.split("'")
        return "concat(" + ', "\'", '.join(f"'{p}'" for p in parts) + ")"

    def _smart_select_match(self, val: str) -> dict:
        """
        给定 Excel 值，返回"找可点击容器"的选择器组合（CSS + XPath）。
        关键：定位 <li> / <node> / [role=option]，而不是 <span>。
        """
        esc_d = val.replace("\\", "\\\\").replace('"', '\\"')
        lit = self._xpath_literal(val)

        # CSS: 逗号分隔的多容器 + :has-text 文字匹配（Playwright 引擎扩展）
        css_parts = []
        for cls in self._OPTION_CONTAINER_CLASSES:
            css_parts.append(f'.{cls}:not(.is-disabled):has-text("{esc_d}")')
        # role 兜底
        css_parts.append(f'[role="menuitem"]:not(.is-disabled):has-text("{esc_d}")')
        css_parts.append(f'[role="option"]:not(.is-disabled):has-text("{esc_d}")')
        # li 通用兜底（最后）
        css_parts.append(f'li:not(.is-disabled):has-text("{esc_d}")')

        # XPath: 元素自己 OR 任意子孙 normalize-space()=lit 才命中（学习资料的关键技巧）
        # 这样 <li><span>VAL</span></li> 命中的是 <li>，点的就是可点击容器
        xpath = (
            f"//*[(@role='menuitem' or @role='option' or self::li"
            f" or contains(@class,'-item') or contains(@class,'-node') or contains(@class,'-option'))]"
            f"[not(contains(@class,'is-disabled'))]"
            f"[normalize-space()={lit} or .//*[normalize-space()={lit}]]"
        )
        return {
            "selector": ", ".join(css_parts),
            "xpath": xpath,
        }

    # ── JS dispatchEvent 兜底点击（学习资料的 CLICK_VISIBLE_TEXT_JS）──
    # 绕过 Playwright 的 actionability 检查，强制派发合成 MouseEvent
    _CLICK_VIA_JS_SCRIPT = r"""
(text) => {
    const normalize = v => String(v || '').replace(/\s+/g, ' ').trim();
    const isVisible = node => {
        if (!node || node.nodeType !== 1) return false;
        const s = window.getComputedStyle(node);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = node.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const selectors = [
        '.el-cascader-node', '.el-cascader-menu__item',
        '.el-select-dropdown__item', '.el-dropdown-menu__item',
        '.ant-cascader-menu-item', '.ant-select-item-option',
        '.ant-dropdown-menu-item', '.avue-cascader-node',
        '.avue-select-dropdown__item', '.n-base-select-option',
        '.n-cascader-option', '[role="menuitem"]', '[role="option"]',
        '.el-popper li', '.el-popper span'
    ];
    for (const sel of selectors) {
        for (const node of document.querySelectorAll(sel)) {
            if (!isVisible(node)) continue;
            const nText = normalize(node.innerText || node.textContent);
            if (nText !== text) continue;
            const target = node.closest(
                '.el-cascader-node, .el-cascader-menu__item, .el-select-dropdown__item, ' +
                '.el-dropdown-menu__item, .ant-cascader-menu-item, .ant-select-item-option, ' +
                '.ant-dropdown-menu-item, .avue-cascader-node, .avue-select-dropdown__item, ' +
                '.n-base-select-option, .n-cascader-option, [role="menuitem"], [role="option"], li'
            ) || node;
            target.scrollIntoView({block: 'center', inline: 'nearest'});
            target.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
            target.click();
            target.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
            return normalize(target.innerText || target.textContent);
        }
    }
    return null;
}
"""

    def _click_via_js(self, text: str) -> bool:
        """JS 派发合成事件点击 —— 终极兜底"""
        try:
            result = self.page.evaluate(self._CLICK_VIA_JS_SCRIPT, text)
            if result:
                self.log(f"  ✓ JS 兜底点击成功：{result}")
                return True
            self.log(f"  ✗ JS 兜底没找到匹配「{text}」的容器")
        except Exception as e:
            self.log(f"  ✗ JS 兜底异常: {e}")
        return False

    # ── 等待 Element UI 的 el-loading-mask 消失 ──
    # 【关键修复 - EXP-030】
    # 主图上传完、表单提交后等场景会显示 <div class="el-loading-mask">,
    # 它会拦截 pointer events 让所有 click 失败:
    #   <div class="el-loading-mask">…</div> intercepts pointer events
    _MASK_CHECK_JS = r"""
    () => {
        const masks = Array.from(document.querySelectorAll('.el-loading-mask'));
        return masks.filter(m => {
            const rect = m.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return false;
            const style = getComputedStyle(m);
            return style.display !== 'none' && style.visibility !== 'hidden';
        }).length;
    }
    """
    _MASK_FORCE_REMOVE_JS = r"""
    () => {
        document.querySelectorAll('.el-loading-mask').forEach(el => {
            el.style.display = 'none';
            el.style.pointerEvents = 'none';
            el.style.opacity = '0';
        });
    }
    """

    def _wait_loading_mask_gone(self, timeout_ms: int = 10000, force_remove: bool = True) -> bool:
        """等 el-loading-mask 消失,超时则 JS 强制隐藏。"""
        end = time.time() + timeout_ms / 1000
        last_count = -1
        while time.time() < end:
            try:
                count = self.page.evaluate(self._MASK_CHECK_JS)
                if count == 0:
                    return True
                if count != last_count:
                    self.log(f"  等待 el-loading-mask 消失 (当前 {count} 个)...")
                    last_count = count
            except Exception:
                pass
            try:
                self.page.wait_for_timeout(200)
            except Exception:
                break

        if force_remove:
            self.log(f"  ⚠ el-loading-mask 持续未消失,JS 强制隐藏")
            try:
                self.page.evaluate(self._MASK_FORCE_REMOVE_JS)
                return True
            except Exception:
                return False
        return False

    # ── XPath 变体（解决 /html/body/div[3] vs div[4] 弹层层级飘移）──
    @staticmethod
    def _xpath_variants(xpath: str) -> list[str]:
        if not xpath or not xpath.startswith(("/html/body/div[", "/html[1]/body[1]/div[")):
            return [xpath] if xpath else []
        result = [xpath]
        for old in ("/html/body/div[2]", "/html/body/div[3]", "/html/body/div[4]",
                    "/html[1]/body[1]/div[2]", "/html[1]/body[1]/div[3]", "/html[1]/body[1]/div[4]"):
            if xpath.startswith(old):
                suffix = xpath[len(old):]
                for idx in range(2, 10):
                    for prefix in (f"/html/body/div[{idx}]", f"/html[1]/body[1]/div[{idx}]"):
                        cand = prefix + suffix
                        if cand not in result:
                            result.append(cand)
                break
        return result

    # ── 自动救火：找一个可见的下拉触发器点开 ──
    # 老 flow 没记录"点击打开下拉"步骤时，运行时直接 select_option 必然找不到选项
    # 这里主动扫描页面上可见的 .el-select / .el-cascader 等触发器，按优先级点开
    DROPDOWN_TRIGGER_SELECTORS = [
        # Element-UI
        ".el-select:visible",
        ".el-cascader:visible",
        ".el-date-editor:visible",
        ".el-time-editor:visible",
        ".el-dropdown:visible",
        # Ant Design
        ".ant-select:visible",
        ".ant-cascader-picker:visible",
        ".ant-picker:visible",
        ".ant-dropdown-trigger:visible",
        # Naive UI
        ".n-base-selection:visible",
        ".n-cascader:visible",
        ".n-date-picker:visible",
        # Vant
        ".van-dropdown-menu__item:visible",
        # 通用兜底：role=combobox
        "[role='combobox']:visible",
        "[aria-haspopup='listbox']:visible",
    ]

    def _auto_open_dropdown(self, action: dict) -> Optional[str]:
        """
        在当前页面找一个还没展开的下拉触发器，点一下并返回 selector。
        优先策略：
          1) action.label 非空 → 找标签匹配的触发器
          2) 否则：点页面上第一个看起来"未展开"的下拉触发器
        返回值：成功点开则返回触发器的描述；否则返回 None
        """
        label = (action.get("label") or "").strip()

        # 策略 1：用 label 精确定位
        if label:
            # 找 form-item 里 label 文本匹配，并且内部有 .el-select / .el-cascader
            for fi_cls in ("el-form-item", "ant-form-item", "n-form-item", "form-item"):
                xpath = (
                    f"//div[contains(@class,'{fi_cls}')]"
                    f"[.//label[contains(normalize-space(.), '{label}')] or .//*[contains(@class,'label') and contains(normalize-space(.), '{label}')]]"
                    f"//*[contains(@class,'el-select') or contains(@class,'el-cascader') or contains(@class,'el-date-editor')"
                    f" or contains(@class,'ant-select') or contains(@class,'ant-cascader') or contains(@class,'ant-picker')"
                    f" or contains(@class,'n-base-selection') or contains(@class,'n-cascader') or contains(@class,'n-date-picker')]"
                )
                try:
                    loc = self.page.locator(f"xpath={xpath}").first
                    if loc.count() > 0 and loc.is_visible():
                        loc.click(timeout=2000)
                        return f"label='{label}'"
                except Exception:
                    continue

        # 策略 2：扫所有可见触发器，点第一个 "看起来未展开" 的
        for sel in self.DROPDOWN_TRIGGER_SELECTORS:
            try:
                loc = self.page.locator(sel)
                cnt = loc.count()
                for i in range(min(cnt, 10)):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                        # 跳过已经展开的（class 里有 is-focus 或 ant-select-open）
                        cls = el.get_attribute("class") or ""
                        if any(k in cls for k in ("is-focus", "ant-select-open", "n-base-selection--active")):
                            continue
                        el.click(timeout=2000)
                        return sel
                    except Exception:
                        continue
            except Exception:
                continue

        return None

    # ── 多策略定位核心 ──
    # 多级菜单 / 下拉的常见容器 class（用于把 text="VALUE" 限定到当前打开的菜单里）
    MENU_CONTAINER_CLASSES = [
        # Element-UI
        "el-cascader-menu", "el-cascader-panel",
        "el-select-dropdown", "el-dropdown-menu",
        "el-popper",  # 通用气泡/弹层
        # Ant Design
        "ant-cascader-menu", "ant-select-dropdown",
        "ant-dropdown-menu", "ant-picker-panel",
        # Avue
        "avue-cascader-menu", "avue-select-dropdown",
        # Naive
        "n-base-select-menu", "n-cascader-menu",
        "n-dropdown-menu",
        # Vant
        "van-popup", "van-dropdown-item__content",
        # 通用 role 兜底
        "[role='listbox']", "[role='menu']",
    ]

    def _candidates(self, action: dict) -> list[str]:
        """按优先级返回所有可用的选择器策略"""
        cands = []
        # 1. scoped_selector (form-item + label 范围)
        scoped = action.get("scoped_selector")
        if scoped:
            cands.append(scoped)

        # 2. ⭐ 菜单容器范围 + Excel 文本（防止匹配到侧边栏/标题等其他 text）
        # 当 action 有 _match_value（Excel 动态生成的）时，前置一批菜单容器范围候选
        match_val = action.get("_match_value")
        if match_val:
            # 转义引号
            esc = match_val.replace('"', '\\"')
            for ctx in self.MENU_CONTAINER_CLASSES:
                # Playwright 引擎链：CSS 容器（可见的）→ 内部 text=
                if ctx.startswith("["):
                    cands.append(f'{ctx}:visible >> text="{esc}"')
                else:
                    cands.append(f'.{ctx}:visible >> text="{esc}"')

        # 3. 主选择器（通常是 text="VALUE" 或框架样式）
        sel = action.get("selector")
        if sel:
            cands.append(sel)

        # 4. ⭐ Label 智能 fallback（v2.0+）
        # 当主 selector 是「动态 placeholder」或「过于宽泛的 input[type="text"]」时
        # 自动用 label 文本 + 各种 form-item 容器 做兜底匹配
        # 适配 聚水潭(goods-)/Element UI(el-)/Ant Design(ant-)/generic 多种框架
        label = (action.get("label") or "").strip()
        action_type = action.get("action_type") or action.get("type") or ""
        if label and len(label) < 40 and label not in ("按钮", "复选框", "输入框", "下拉框"):
            esc = label.replace('"', '\\"').replace("\n", " ")[:30]
            # 输入框 fill 用 input/textarea
            is_input_like = action_type in ("input", "fill") or sel and ("input" in sel.lower())
            if is_input_like:
                # 聚水潭、Element UI、Ant Design、通用 — 按层级 + 标签锚定
                cands.extend([
                    f'.goods-form-item:visible:has-text("{esc}") input:not([type="hidden"])',
                    f'.goods-form-item:visible:has-text("{esc}") textarea',
                    f'.goods-form-item-row:visible:has-text("{esc}") input:not([type="hidden"])',
                    f'.el-form-item:visible:has-text("{esc}") input:not([type="hidden"])',
                    f'.ant-form-item:visible:has-text("{esc}") input:not([type="hidden"])',
                    f'[class*="form-item"]:visible:has-text("{esc}") input:not([type="hidden"])',
                    # 直接找 label 关联的 input
                    f'label:has-text("{esc}") + * input:not([type="hidden"])',
                    f'label:has-text("{esc}") ~ * input:not([type="hidden"])',
                ])
            elif action_type == "click":
                # 点击带文字的元素，先按 button/a/label 匹配，再 generic
                cands.extend([
                    f'button:visible:has-text("{esc}")',
                    f'a:visible:has-text("{esc}")',
                    f'label:visible:has-text("{esc}")',
                    # 聚水潭/Element/Ant 树形组件节点
                    f'.goods-tree-node-content-wrapper:visible:has-text("{esc}")',
                    f'.goods-tree-treenode:visible:has-text("{esc}")',
                    f'.el-tree-node__content:visible:has-text("{esc}")',
                    f'.ant-tree-node-content-wrapper:visible:has-text("{esc}")',
                    # 下拉选项（el-select / ant-select / 聚水潭 goods-select 等）
                    f'.el-select-dropdown__item:visible:has-text("{esc}")',
                    f'.ant-select-item:visible:has-text("{esc}")',
                    f'.goods-select-dropdown__item:visible:has-text("{esc}")',
                    f'li:visible:has-text("{esc}")',
                    # form-item 范围
                    f'.goods-form-item:visible:has-text("{esc}")',
                    f'.el-form-item:visible:has-text("{esc}")',
                ])

        # 5. xpath 兜底
        xp = action.get("xpath")
        if xp:
            cands.append("xpath=" + xp)
        return cands

    def _find_visible_locator(self, action: dict, timeout: int, require_visible: bool = True):
        """逐个尝试选择器，返回第一个**真正可见**的 locator（防 0×0 隐藏占位）。

        v2.0+ 增强：
        - 主文档找不到时，**自动扫描所有 iframe** 再找一遍（聚水潭等 ERP 必需）
        - 找到后会记录是在哪个 frame 里命中，方便排查

        【关键修复 - EXP-029】
        Vue/Element UI 经常有 0 尺寸 (width=0 height=0) 的隐藏占位元素 (模板预渲染)。
        Playwright 的 is_visible() **不会**过滤这种元素 (只过滤 display:none/visibility:hidden)。
        必须额外用 bounding_box() 检查实际尺寸 > 0。
        """
        cands = self._candidates(action)
        if not cands:
            raise DSLError("没有可用的选择器")

        end_time = time.time() + timeout / 1000
        last_err: Optional[Exception] = None
        attempt = 0
        last_attempted_in_iframes = False
        while time.time() < end_time:
            attempt += 1
            # —— Phase 1: 主文档 ——
            for sel in cands:
                try:
                    loc = self.page.locator(sel)
                    cnt = loc.count()
                    if cnt == 0:
                        continue
                    if require_visible:
                        for i in range(min(cnt, 20)):
                            item = loc.nth(i)
                            try:
                                if not item.is_visible():
                                    continue
                                try:
                                    box = item.bounding_box()
                                    if not box or box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                                        continue
                                except Exception:
                                    continue
                                return item, sel
                            except Exception:
                                continue
                    else:
                        return loc.first, sel
                except Exception as e:
                    last_err = e
                    continue

            # —— Phase 2: 主文档没找到 → 扫所有 iframe 再试 ——
            # 不每轮都扫（性能），间隔 3 轮扫一次
            should_scan_frames = (attempt % 3 == 1)
            if should_scan_frames:
                try:
                    frames = list(self.page.frames)
                except Exception:
                    frames = []
                main_frame = None
                try:
                    main_frame = self.page.main_frame
                except Exception:
                    pass
                for frame in frames:
                    if main_frame is not None and frame == main_frame:
                        continue
                    try:
                        if not frame or frame.is_detached():
                            continue
                    except Exception:
                        continue
                    for sel in cands:
                        try:
                            loc = frame.locator(sel)
                            cnt = loc.count()
                            if cnt == 0:
                                continue
                            if require_visible:
                                for i in range(min(cnt, 20)):
                                    item = loc.nth(i)
                                    try:
                                        if not item.is_visible():
                                            continue
                                        try:
                                            box = item.bounding_box()
                                            if not box or box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                                                continue
                                        except Exception:
                                            continue
                                        try:
                                            fu = (frame.url or "")[:60]
                                        except Exception:
                                            fu = ""
                                        self.log(f"  ↗ 在 iframe ({fu}) 内找到「{sel[:60]}」")
                                        last_attempted_in_iframes = True
                                        return item, sel
                                    except Exception:
                                        continue
                            else:
                                last_attempted_in_iframes = True
                                return loc.first, sel
                        except Exception as e:
                            last_err = e
                            continue

            try:
                self.page.wait_for_timeout(self.poll_ms)
            except Exception:
                break

        # 失败时给出更多信息
        try:
            frame_count = len(self.page.frames) - 1  # 减掉主 frame
        except Exception:
            frame_count = 0
        extra = f"，含 {frame_count} 个 iframe" if frame_count > 0 else ""
        raise DSLError(
            f"元素未找到/不可见 (已过滤 0×0 占位)，已尝试 {len(cands)} 种策略 × {attempt} 轮{extra}："
            + " | ".join(c[:60] for c in cands)
        )

    # ── 执行 ──
    def execute(self, actions: list, row: Optional[dict] = None, loop_index: int = 1):
        # 用 while 循环而不是 for，方便用户选「重试」时 i 不递增
        i = 0
        total = len(actions)
        while i < total:
            i += 1
            a = actions[i - 1]
            t = a.get("type", "")
            try:
                self._run_one(a, row)
            except Exception as e:
                # 任何错误（DSLError 或其他）都进入「人工接管」模式
                err_msg = str(e) if isinstance(e, DSLError) else f"{type(e).__name__}: {e}"
                decision = self._on_step_error(i, t, err_msg, has_row=(row is not None))

                if decision == "continue":
                    # 用户已手动完成 → 继续下一步
                    self.log(f"▶ 用户已手动完成第 {i} 步，继续下一步")
                elif decision == "retry":
                    # 重试当前步
                    self.log(f"🔁 重试第 {i} 步")
                    i -= 1  # 抵消下次循环的 +1
                    continue
                elif decision == "skip_step":
                    # 跳过当前步
                    self.log(f"⏩ 用户跳过第 {i} 步")
                elif decision == "skip_row":
                    # 跳过本行剩余所有步骤
                    self.log(f"⏭ 用户跳过本行剩余 {total - i + 1} 步")
                    return
                else:  # stop
                    # 真的停下来
                    if isinstance(e, DSLError):
                        raise
                    raise DSLError(f"第 {i} 条指令（{t}）执行失败: {e}")

            self._manual_checkpoint_after_action(i, loop_index)

    def _on_step_error(self, index: int, step_type: str, error_msg: str, has_row: bool) -> str:
        """
        步骤出错时弹"人工接管"对话框，让用户选择下一步动作。
        同时静默记录用户在浏览器里的操作，攒成学习样本。
        返回：continue / retry / skip_step / skip_row / stop
        """
        self.log(f"⚠ 第 {index} 步（{step_type}）出错：{error_msg[:200]}")
        self.log(f"⏸ 已暂停，请在浏览器顶部选择如何处理（接管期间会静默记录你的操作）")

        # ① 初始化样本记录器（幂等，重复调用安全）
        try:
            self.page.evaluate(MANUAL_RECORDER_INIT_JS)
        except Exception:
            pass

        # ② 开启录制
        try:
            self.page.evaluate("""
                () => {
                    window.__hbf_manual_recording = true;
                    window.__hbf_manual_recording_start_t = Date.now();
                    window.__hbf_manual_actions = [];
                }
            """)
        except Exception:
            pass

        # ③ 弹对话框（先确保拖动行为已注入）
        try:
            self.page.evaluate(MANUAL_DIALOG_DRAG_INIT_JS)
        except Exception:
            pass
        try:
            self.page.evaluate(MANUAL_RECOVERY_JS, {
                "index": index,
                "stepType": step_type,
                "errorMsg": error_msg[:600],
                "hasRow": has_row,
            })
        except Exception as ev_err:
            self.log(f"  无法显示人工接管对话框（{ev_err}），按 stop 处理")
            return "stop"

        decision = self._wait_manual_decision(default="stop")

        # ④ 关闭录制 + 取出样本
        try:
            self.page.evaluate("() => { window.__hbf_manual_recording = false; }")
            manual_actions = self.page.evaluate("() => window.__hbf_manual_actions || []") or []
        except Exception:
            manual_actions = []

        # ⑤ 仅在「已手动完成」时保存样本（其他决定的样本不算）
        if decision == "continue" and manual_actions:
            try:
                self._save_manual_sample(index, step_type, error_msg, manual_actions, has_row)
            except Exception as save_err:
                self.log(f"  ⚠ 样本保存失败：{save_err}")

        return decision

    def _save_manual_sample(self, step_index: int, step_type: str,
                            error_msg: str, manual_actions: list, has_row: bool) -> None:
        """
        把人工接管期间录到的操作存到 learning_samples.json
        路径：<flow_dir>/learning_samples.json
        累积到阈值（如 5 个）后，可以让 AI 学习并修补 DSL
        """
        if not self.learning_dir:
            self.log(f"  ⚠ 没有学习样本目录，样本暂不保存（运行模式可能不支持）")
            return

        import json as _json
        from datetime import datetime as _dt

        try:
            self.learning_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        sample_file = self.learning_dir / "learning_samples.json"

        # 读已有
        data = {"step_samples": {}}
        if sample_file.exists():
            try:
                data = _json.loads(sample_file.read_text(encoding="utf-8"))
                if "step_samples" not in data:
                    data["step_samples"] = {}
            except Exception:
                data = {"step_samples": {}}

        key = f"step_{step_index}"
        step_entry = data["step_samples"].setdefault(key, {
            "step_index": step_index,
            "step_type": step_type,
            "samples": [],
        })
        # 更新 step_type（用最新的）
        step_entry["step_type"] = step_type

        sample = {
            "sample_id": len(step_entry["samples"]) + 1,
            "captured_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_msg": error_msg[:500],
            "has_row": has_row,
            "actions_count": len(manual_actions),
            "actions": manual_actions,
        }
        step_entry["samples"].append(sample)

        # 写回
        try:
            sample_file.write_text(
                _json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            total = len(step_entry["samples"])
            self.log(f"  ✓ 第 {step_index} 步样本 #{sample['sample_id']} 已记录（{len(manual_actions)} 个操作；累积 {total} 个样本）")
            if total >= 5 and total < 6:
                self.log(f"  🌱 该步已累积 {total} 个样本，可以让 AI 学习修复了！")
        except Exception as e:
            self.log(f"  ⚠ 写入样本文件失败：{e}")

    def _manual_checkpoint_after_action(self, index: int, loop_index: int) -> None:
        if not self.manual_checkpoint_enabled:
            return
        if index in self.manual_after_indices:
            self._wait_manual_task(index)
            return
        if loop_index != 1:
            return
        if index <= self._manual_prompt_skip_until:
            return
        decision = self._ask_manual_checkpoint(index)
        if decision == "manual":
            self.manual_after_indices.add(index)
            points = ", ".join(str(x) for x in sorted(self.manual_after_indices))
            self.log(f"✓ 已设置人工介入点：每轮第 {index} 步后暂停（当前: {points}）")
            self._wait_manual_task(index)
        elif decision == "skip":
            self._manual_prompt_skip_until = index + self.manual_prompt_skip_steps
            self.log(f"⊝ 接下来 {self.manual_prompt_skip_steps} 步不提示人工介入")
        elif decision == "never":
            self._manual_prompt_skip_until = 10**9
            self.log("⊝ 本轮不再提示人工介入")

    def _ask_manual_checkpoint(self, index: int) -> str:
        self.log(f"？第 {index} 步已完成，等待用户判断是否设置人工介入点")
        try:
            self.page.evaluate(MANUAL_DIALOG_DRAG_INIT_JS)
        except Exception:
            pass
        try:
            self.page.evaluate(MANUAL_CHECKPOINT_PROMPT_JS, {
                "index": index,
                "skip": self.manual_prompt_skip_steps,
            })
        except Exception:
            return "never"
        return self._wait_manual_decision(default="never")

    def _wait_manual_task(self, index: int) -> None:
        self.log(f"⏸ 第 {index} 步后人工介入，等待用户手动处理")
        try:
            self.page.evaluate(MANUAL_DIALOG_DRAG_INIT_JS)
        except Exception:
            pass
        try:
            self.page.evaluate(MANUAL_TASK_JS, {"index": index})
        except Exception:
            raise DSLError("无法显示人工介入浮层")
        decision = self._wait_manual_decision(default="stop")
        if decision == "continue":
            self.log("▶ 用户已手动处理，继续执行剩余步骤")
            return
        raise DSLError("用户停止运行")

    def _wait_manual_decision(self, default: str) -> str:
        while True:
            try:
                decision = self.page.evaluate("() => window.__hbf_manual_decision || null")
            except Exception:
                return default
            if decision:
                return str(decision)
            try:
                self.page.wait_for_timeout(400)
            except Exception:
                return default

    def _run_one(self, a: dict, row: Optional[dict]):
        t = a.get("type", "").lower()
        timeout = a.get("timeout", self.default_timeout)

        if t == "goto":
            url = a.get("url", "")
            self.log(f"→ 打开 {url}")
            self.page.goto(url, wait_until=a.get("wait_until", "domcontentloaded"),
                          timeout=timeout)

        elif t == "wait":
            if a.get("selector"):
                self.log(f"→ 等待元素 {a['selector']}")
                self.page.wait_for_selector(a["selector"], timeout=timeout)
            elif "ms" in a:
                self.page.wait_for_timeout(a["ms"])

        elif t == "fill":
            val = self._resolve(a, row)
            self.log(f"→ 输入 = {val[:30]}")
            is_search_fill = self._looks_like_searchable_dropdown_fill(a)
            item, used = self._find_visible_locator(a, timeout)

            # 【关键修复 - EXP-030】先 click 激活 (有些后台 input 默认 disabled, 必须 click 才能输入)
            try:
                item.click(timeout=2500)
                self.page.wait_for_timeout(150)
            except Exception:
                # click 失败可能是被 mask 拦截,等 mask 消失再试
                self._wait_loading_mask_gone(timeout_ms=3000)
                try:
                    item.click(timeout=2000, force=True)
                    self.page.wait_for_timeout(150)
                except Exception:
                    pass

            # 检查 disabled / readonly
            try:
                eh = item.element_handle()
                state = self.page.evaluate(
                    """(el) => ({
                        disabled: !!(el && (el.disabled || el.hasAttribute('disabled'))),
                        readonly: !!(el && (el.readOnly || el.hasAttribute('readonly')))
                    })""",
                    eh
                )
                if state.get("disabled"):
                    self.log("  input 是 disabled, JS 强制移除")
                    self.page.evaluate(
                        "(el) => { el.removeAttribute('disabled'); el.disabled = false; }",
                        eh
                    )
                    self.page.wait_for_timeout(100)
                # 【关键修复 - EXP-027】readonly input (如 el-select 内部搜索框) 跳过 fill
                # Playwright 的 fill 在 readonly 上会 timeout 30s,不是 no-op!
                # EXP-027 的"机会型 fill"思想:readonly 时跳过,不影响后续 select_option
                if state.get("readonly") and not state.get("disabled"):
                    if is_search_fill:
                        self.log("  可搜索下拉输入框是 readonly，尝试解除 readonly 后输入")
                        try:
                            self.page.evaluate(
                                "(el) => { el.removeAttribute('readonly'); el.readOnly = false; }",
                                eh
                            )
                            self.page.wait_for_timeout(100)
                        except Exception:
                            pass
                    else:
                        self.log("  input 是 readonly (普通 el-select),跳过 fill 让 select_option 直接选")
                        self._wait_after_if_needed(a)
                        return
            except Exception:
                pass

            try:
                if is_search_fill and self._type_into_search_input(a, val):
                    self.log("  ✓ 已按搜索型下拉输入")
                else:
                    # fill 加 timeout=3000ms 避免 readonly 等场景卡默认 30s
                    item.fill(val, timeout=3000)
            except Exception as e:
                if self.fill_fallback:
                    # 兜底 1: click + keyboard.insert_text
                    try:
                        item.click()
                        self.page.wait_for_timeout(100)
                        self.page.keyboard.press("Control+A")
                        self.page.keyboard.insert_text(val)
                    except Exception:
                        # 兜底 2: JS 直接赋值 + 派发 input/change 事件 (终极)
                        try:
                            self.page.evaluate(
                                """(args) => {
                                    const el = args.el;
                                    const native = Object.getOwnPropertyDescriptor(
                                        window.HTMLInputElement.prototype, 'value'
                                    ).set;
                                    native.call(el, args.value);
                                    el.dispatchEvent(new Event('input', {bubbles: true}));
                                    el.dispatchEvent(new Event('change', {bubbles: true}));
                                }""",
                                {"el": item.element_handle(), "value": val}
                            )
                        except Exception:
                            raise DSLError(f"输入失败：{e}")
                else:
                    raise DSLError(f"输入失败：{e}")

            self._last_fill_action = dict(a)
            self._last_fill_value = val
            self._last_fill_at = time.time()
            self._wait_after_if_needed(a)

        elif t in ("click", "select_option"):
            # 菜单项执行前主动等待下拉菜单出现（关键修复）
            if t == "select_option" and self.select_pre_wait > 0:
                try:
                    self.page.wait_for_timeout(self.select_pre_wait)
                except Exception:
                    pass

            self.log(f"→ {'选择' if t == 'select_option' else '点击'}")
            # 菜单项：如果绑定了 Excel 列，用 Excel 里的文本动态生成选择器
            action_eff = dict(a)  # 复制，避免污染原 action
            if t == "select_option" and a.get("match_by_text") and a.get("from_excel"):
                val = ""
                if row:
                    val = str(row.get(a["from_excel"], "")).strip()
                if val:
                    # ⭐ 关键改进：用 smart selector 找父级 <li>，不要找内层 <span>
                    # 这是解决「Locator.click 30s 超时」的核心
                    smart = self._smart_select_match(val)
                    action_eff["selector"] = smart["selector"]
                    action_eff["xpath"] = smart["xpath"]
                    action_eff["_match_value"] = val  # 给 _click_via_js 用
                    self.log(f"→ 按 Excel 数据选择「{val}」")
                else:
                    # ⭐ Excel 数据为空 → 跳过这一步（支持多级菜单的可变层级）
                    self.log(f"⊝ Excel 列「{a.get('from_excel')}」无值，跳过此步")
                    return  # 直接结束这条 action，不报错

            val_for_js = action_eff.get("_match_value")  # JS 兜底用
            item = None
            used = None

            try:
                item, used = self._find_visible_locator(action_eff, timeout)
            except DSLError as e:
                # ───── 自动救火 1：找不到选项 → 自动点开下拉再试 ─────
                if t == "select_option":
                    # 如果上一条是品牌/供应商等搜索框 fill，可能远程搜索没触发或搜索词过短。
                    # 直接把目标选项完整文本再输入到同一个搜索框，然后重试定位。
                    if (
                        val_for_js
                        and self._last_fill_action
                        and time.time() - self._last_fill_at < 20
                    ):
                        self.log(f"⚠ 没找到选项，尝试在上一步搜索框输入完整文本「{val_for_js}」...")
                        if self._type_into_search_input(self._last_fill_action, val_for_js):
                            self.page.wait_for_timeout(max(self.select_pre_wait, 1200))
                            try:
                                item, used = self._find_visible_locator(action_eff, timeout)
                            except DSLError:
                                item = None

                    self.log("⚠ 没找到下拉选项，尝试自动打开下拉菜单...")
                    opened = None if item is not None else self._auto_open_dropdown(action_eff)
                    if item is None and opened:
                        self.log(f"  ✓ 已点开「{opened}」，重试...")
                        self.page.wait_for_timeout(self.select_pre_wait or 600)
                        try:
                            item, used = self._find_visible_locator(action_eff, timeout)
                        except DSLError:
                            item = None

                    # ───── 自动救火 2：Playwright 定位失败 → 直接 JS 派发点击 ─────
                    if item is None and val_for_js:
                        self.log(f"⚠ Playwright 定位失败，切换 JS 模式直接派发点击")
                        if self._click_via_js(val_for_js):
                            # JS 模式点击成功，跳过下面的 .click() 直接走 post-wait
                            if a.get("wait_after"):
                                self.page.wait_for_timeout(a["wait_after"])
                            elif t == "select_option":
                                self.page.wait_for_timeout(self.select_wait)
                            return

                    if item is None:
                        has_excel = bool(a.get("from_excel"))
                        raise DSLError(
                            f"找不到下拉菜单项「{val_for_js or '(无值)'}」。{e}\n"
                            f"可能原因：\n"
                            f"  1) Excel 列「{a.get('from_excel')}」的值跟下拉里的选项文本对不上\n"
                            + (f"  2) 选项是异步加载，需要更长等待\n" if has_excel else "")
                            + f"  3) 没有匹配的 el-select / cascader / 自定义下拉触发器"
                        )
                else:
                    raise

            # ───── 点击 + JS 兜底（解决 <span> 不可点 → click 30s 超时）─────
            click_timeout = min(timeout, 6000)  # 缩短首轮超时，兜底快速接管
            try:
                item.click(timeout=click_timeout)
            except Exception as click_err:
                # 【关键修复 - EXP-030】被 el-loading-mask 拦截 → 等 mask 消失 + force 重试
                err_msg = str(click_err)
                if "intercepts pointer events" in err_msg or "loading-mask" in err_msg:
                    self.log(f"⚠ click 被拦截 (mask),等 mask 消失再 force 重试")
                    self._wait_loading_mask_gone(timeout_ms=5000)
                    try:
                        item.click(timeout=3000, force=True)
                        if a.get("wait_after"):
                            self.page.wait_for_timeout(a["wait_after"])
                        elif t == "select_option":
                            self.page.wait_for_timeout(self.select_wait)
                        return
                    except Exception as e2:
                        click_err = e2

                # 只对 select_option 启用 JS 兜底（普通 click 不能瞎换目标）
                if t == "select_option" and val_for_js:
                    self.log(f"⚠ Playwright .click() 失败 ({type(click_err).__name__})，切换 JS 派发")
                    if self._click_via_js(val_for_js):
                        pass  # 成功，落到下面 wait
                    else:
                        raise DSLError(
                            f"click 失败 + JS 兜底失败：{click_err}\n"
                            f"  Excel 值「{val_for_js}」可能跟当前下拉里的选项不一致"
                        )
                else:
                    raise DSLError(f"click 失败：{click_err}")

            if a.get("wait_after"):
                self.page.wait_for_timeout(a["wait_after"])
            elif t == "select_option":
                self.page.wait_for_timeout(self.select_wait)

        elif t == "select":
            val = self._resolve(a, row)
            self.log(f"→ 选择 = {val}")
            sel = a.get("selector")
            if sel:
                self.page.wait_for_selector(sel, timeout=timeout)
                self.page.select_option(sel, val)

        elif t in ("check", "uncheck"):
            checked = a.get("checked", t == "check")
            self.log(f"→ {'勾选' if checked else '取消勾选'}")
            item, used = self._find_visible_locator(a, timeout)
            if checked:
                item.check()
            else:
                item.uncheck()

        elif t == "upload":
            import os
            from pathlib import Path as _P

            path = self._resolve(a, row)
            # 清洗：去掉用户可能复制带进来的引号、空格、尾部反斜杠
            if path:
                path = path.strip().strip('"').strip("'").strip()
                # 占位提示文字直接当空处理
                if path.startswith(r"D:\示例") or path == "":
                    path = ""
            if not path:
                raise DSLError(
                    "上传文件失败：路径为空。\n"
                    "请在 Excel 对应列填写本地文件或文件夹路径，例如：\n"
                    "  单个文件: D:\\图片\\商品1.jpg\n"
                    "  整个文件夹: D:\\商品图片（runner 会自动上传里面所有文件）"
                )
            p = _P(path)
            if not p.exists():
                raise DSLError(
                    f"上传失败：路径 '{path}' 在本地不存在。\n"
                    f"请检查 Excel 里的路径是否正确（用绝对路径）"
                )

            # ─── 自动识别：路径是文件 or 目录 ───
            if p.is_dir():
                # 默认只接受图片（最常见的上传场景）
                # 用户可以通过 file_extensions 字段自定义
                IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "tiff"}
                DOC_EXT = {"pdf", "doc", "docx", "txt", "csv", "rtf", "odt"}
                SHEET_EXT = {"xls", "xlsx", "ods"}
                VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "webm", "flv"}
                ALL_KNOWN = IMAGE_EXT | DOC_EXT | SHEET_EXT | VIDEO_EXT

                # 常见系统隐藏/缓存文件，静默忽略
                SYSTEM_IGNORE = {
                    ".ds_store", "thumbs.db", "desktop.ini",
                    ".gitkeep", ".gitignore",
                }

                custom_ext = a.get("file_extensions")
                if custom_ext:
                    ext_set = {e.lower().lstrip(".") for e in custom_ext}
                    strict_mode = True
                else:
                    # 默认走"图片优先"模式
                    ext_set = IMAGE_EXT
                    strict_mode = False

                accepted = []        # 命中白名单的
                foreign_known = []   # 已知格式但不在白名单（如想传图，但发现了 pdf）
                unknown = []         # 完全不认识的扩展名（可能是垃圾文件）

                for fname in sorted(os.listdir(path)):
                    fp = p / fname
                    if not fp.is_file():
                        continue
                    lname = fname.lower()
                    if lname in SYSTEM_IGNORE or lname.startswith("."):
                        continue
                    ext = fp.suffix.lower().lstrip(".")
                    if ext in ext_set:
                        accepted.append(str(fp))
                    elif ext in ALL_KNOWN:
                        foreign_known.append(fname)
                    else:
                        unknown.append(fname)

                # ─── 校验"过杂"情况 ───
                # 严格模式（用户指定了 file_extensions）：任何不匹配都报错
                if strict_mode and (foreign_known or unknown):
                    raise DSLError(
                        f"目录「{path}」内的文件不全匹配指定扩展名 {sorted(ext_set)}\n"
                        f"  不符合的文件: {', '.join((foreign_known + unknown)[:8])}\n"
                        f"  请清理目录后重试，或调整 Excel 列指向更干净的文件夹"
                    )

                # 默认模式（图片优先）：
                #   - 一张图都没有 → 报错
                #   - 有图但混了 PDF/Word → 报错（用户大概率搞错了）
                #   - 有图但有少量未知扩展名 → 警告但继续（< 30%）
                if not accepted:
                    if foreign_known:
                        raise DSLError(
                            f"目录「{path}」下没找到图片，但有其他类型文件:\n"
                            f"  {', '.join(foreign_known[:8])}\n"
                            f"  如果你确实要传这些文件，请在 DSL 里指定 file_extensions"
                        )
                    raise DSLError(
                        f"目录「{path}」下没找到可上传的图片\n"
                        f"  默认接受的扩展名: {', '.join(sorted(IMAGE_EXT))}\n"
                        f"  请检查目录里有没有图片文件"
                    )

                if foreign_known:
                    raise DSLError(
                        f"目录「{path}」内文件类型混杂，无法判断要上传什么:\n"
                        f"  图片 {len(accepted)} 张（要传）\n"
                        f"  其他类型: {', '.join(foreign_known[:8])}\n"
                        f"  请把不要上传的文件移出去，或在 DSL 里明确 file_extensions"
                    )

                if unknown:
                    # 未知扩展名容忍：少于 30% 就只 warn
                    ratio = len(unknown) / max(1, len(accepted) + len(unknown))
                    if ratio >= 0.3:
                        raise DSLError(
                            f"目录「{path}」内有较多未知格式文件 ({len(unknown)} 个):\n"
                            f"  {', '.join(unknown[:8])}\n"
                            f"  请清理后重试"
                        )
                    self.log(f"  ⚠ 忽略 {len(unknown)} 个未知扩展名文件: {', '.join(unknown[:5])}")

                paths_to_upload = accepted
                self.log(f"→ 检测到目录，扫到 {len(accepted)} 张图片，准备批量上传:")
                for fp in accepted[:10]:
                    self.log(f"    {_P(fp).name}")
                if len(accepted) > 10:
                    self.log(f"    ... 共 {len(accepted)} 个")
            elif p.is_file():
                paths_to_upload = [str(p)]
                self.log(f"→ 上传单个文件 {path}")
            else:
                raise DSLError(f"路径既不是文件也不是目录: {path}")

            sel = a.get("selector") or "input[type=\"file\"]"
            is_file_input = ('input[type="file"]' in sel or "input[type='file']" in sel
                            or 'input[type=file]' in sel)
            multi_count = len(paths_to_upload)

            def _do_set(locator, files_list):
                """带 multiple 检测的安全投递。
                如果 input 不支持 multiple 但要传多个文件，逐个 set 而不是丢失"""
                if multi_count <= 1:
                    locator.set_input_files(files_list)
                    return "batch"
                try:
                    is_multi = locator.evaluate("el => !!el.multiple")
                except Exception:
                    is_multi = True  # 不知道就假设支持，让 Playwright 决定
                if is_multi:
                    locator.set_input_files(files_list)
                    return "batch"
                # 不支持 multiple → 逐个传
                for i, fpath in enumerate(files_list, 1):
                    locator.set_input_files(fpath)
                    self.log(f"    [{i}/{multi_count}] 已投递 {fpath}")
                    self.page.wait_for_timeout(300)
                return "iterative"

            # 策略 1: input[type=file] 直接 set_input_files
            if is_file_input:
                try:
                    action_eff = dict(a)
                    action_eff["selector"] = sel
                    item, used = self._find_visible_locator(action_eff, timeout, require_visible=False)
                    mode = _do_set(item, paths_to_upload)
                    self.log(f"  ✓ set_input_files 完成（{mode}，{multi_count} 个文件）")
                    return
                except Exception as e:
                    self.log(f"  直接 set_input_files 失败: {e}，尝试 file_chooser 模式")

            # 策略 2: click button + expect_file_chooser 拦截系统文件对话框
            try:
                self._wait_loading_mask_gone(timeout_ms=3000)
                action_eff = dict(a)
                action_eff["selector"] = sel
                item, used = self._find_visible_locator(action_eff, timeout)
                with self.page.expect_file_chooser(timeout=5000) as chooser_info:
                    item.click(timeout=3000, force=True)
                chooser_info.value.set_files(paths_to_upload)
                self.log(f"  ✓ 通过 file_chooser 投递 {multi_count} 个文件")
                return
            except Exception as e:
                self.log(f"  file_chooser 模式失败: {e}")

            # 策略 3: 终极兜底 - 找页面上任何可见的 input[type=file] 直接投递
            try:
                inputs = self.page.locator("input[type='file']")
                if inputs.count() > 0:
                    mode = _do_set(inputs.last, paths_to_upload)
                    self.log(f"  ✓ 通过页面任意 input[type=file] 投递 {multi_count} 个文件 ({mode})")
                    return
            except Exception:
                pass

            raise DSLError(
                f"上传失败: 所有 3 种策略都失败 (selector={sel!r}, files={multi_count} 个)\n"
                f"  策略 1: set_input_files 直接投递\n"
                f"  策略 2: click button + expect_file_chooser 拦截\n"
                f"  策略 3: 找页面任意 input[type=file]"
            )

        elif t == "upload_folder_to_library":
            # ────────────────────────────────────────────────
            #  素材库目录批量上传 + 自动等待 + 自动勾选
            # ────────────────────────────────────────────────
            #  用户 Excel 一格填文件夹路径，runner 自动：
            #    1) 扫描该目录下所有图片
            #    2) 用 set_input_files 一次性上传所有图片
            #    3) 等待上传完成（监测 DOM 里素材项数量增加到 +N）
            #    4) 自动勾选最近上传的 N 张
            #    5) 后续步骤会点击「确定」关闭弹窗
            #
            #  DSL 字段：
            #    selector         素材库弹窗里 input[type=file]
            #    from_excel       Excel 列名（用户填文件夹路径）
            #    file_extensions  允许的扩展名（默认 jpg/jpeg/png/gif/webp/bmp）
            #    item_selector    素材项 selector（默认 label.material-name）
            #    select_strategy  last_n / first_n（默认 last_n）
            #    wait_timeout     上传完成最长等待（默认 300000ms = 5 分钟）
            #    wait_after       勾选前额外等（默认 1000ms）
            # ────────────────────────────────────────────────
            import os
            from pathlib import Path as _P

            col = a.get("from_excel")
            if not col:
                raise DSLError(
                    "upload_folder_to_library 必须配置 from_excel（Excel 列名）"
                )
            folder = ""
            used_col = col
            if row is not None:
                col_candidates = [col]
                if col.endswith("目录"):
                    col_candidates.append(col[:-2] + "路径")
                elif col.endswith("路径"):
                    col_candidates.append(col[:-2] + "目录")

                seen_cols = set()
                for candidate in col_candidates:
                    if not candidate or candidate in seen_cols:
                        continue
                    seen_cols.add(candidate)
                    raw_value = row.get(candidate, "")
                    if raw_value is None:
                        value = ""
                    else:
                        value = str(raw_value).strip().strip('"').strip("'")
                    if value and value.lower() not in ("nan", "none"):
                        folder = value
                        used_col = candidate
                        break
                if folder and used_col != col:
                    self.log(f"  Excel 列「{col}」无值，兼容使用「{used_col}」")
            if not folder:
                self.log(f"⊝ Excel 列「{col}」无值，跳过批量上传")
                return
            if not _P(folder).is_dir():
                raise DSLError(
                    f"文件夹不存在：{folder}\n"
                    f"请检查 Excel 里「{used_col}」列的路径是否正确（要绝对路径）"
                )

            extensions = a.get("file_extensions",
                ["jpg", "jpeg", "png", "gif", "webp", "bmp"])
            extensions = {e.lower().lstrip(".") for e in extensions}

            # 扫描目录，按文件名排序
            files = []
            for fname in sorted(os.listdir(folder)):
                p = _P(folder) / fname
                if not p.is_file():
                    continue
                ext = p.suffix.lower().lstrip(".")
                if ext in extensions:
                    files.append(str(p))
            if not files:
                raise DSLError(
                    f"目录「{folder}」下没找到匹配的图片\n"
                    f"允许的扩展名：{', '.join(sorted(extensions))}"
                )

            n = len(files)
            self.log(f"→ 扫到 {n} 张图片，开始批量上传...")

            # input[type=file] 的 selector（DSL 提供 or 默认）
            sel = a.get("selector") or '.el-dialog__wrapper input[type="file"]'

            # 勾选用的 checkbox selector 候选列表（按优先级）
            # 关键：用 span.el-checkbox__inner（Element UI checkbox 真正可点的小方块）
            checkbox_selectors = a.get("checkbox_selectors") or [
                "xpath=//div[contains(@class,'el-dialog')]//span[contains(@class,'el-checkbox__inner')]",
                "css=.el-dialog__wrapper span.el-checkbox__inner",
                "css=.el-dialog__wrapper label.el-checkbox",
                "css=.el-drawer__wrapper span.el-checkbox__inner",
            ]

            # ⭐ 默认 auto_diff —— 不写死方向，靠 before/after 差集找新图
            # 兼容显式 first_n / last_n，给老 DSL / 特殊场景留兜底
            select_strategy = a.get("select_strategy", "auto_diff")
            wait_after = int(a.get("wait_after", 800))

            # ─── 上传前快照：input[type=file] 数量 + 已有 checkbox item 的身份指纹 ───
            try:
                before_input_count = self.page.locator("input[type='file']").count()
            except Exception:
                before_input_count = 0
            self.log(f"  上传前页面有 {before_input_count} 个 input[type=file]")

            # 上传前对每个 checkbox 取「身份指纹」，方便后面差集找新图
            # 指纹优先级：img.src → 文本（含文件名）→ 位置坐标
            def _snapshot_checkboxes() -> list[dict]:
                try:
                    return self.page.evaluate("""
                        (selectors) => {
                            // 用第一个能找到 > 0 个的 selector
                            let items = [];
                            let usedSel = '';
                            for (const sel of selectors) {
                                let els = [];
                                if (sel.startsWith('xpath=')) {
                                    const xp = sel.slice('xpath='.length);
                                    const it = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                                    for (let i = 0; i < it.snapshotLength; i++) els.push(it.snapshotItem(i));
                                } else if (sel.startsWith('css=')) {
                                    els = Array.from(document.querySelectorAll(sel.slice('css='.length)));
                                } else {
                                    els = Array.from(document.querySelectorAll(sel));
                                }
                                if (els.length > 0) { items = els; usedSel = sel; break; }
                            }
                            return items.map((el, idx) => {
                                const r = el.getBoundingClientRect();
                                // 往上找最近的"图片卡片容器"，从里面取识别信息
                                let card = el.closest('.el-card, .el-card__body, .el-col, .material-item, [class*="material"], [class*="item"]');
                                if (!card) card = el.parentElement;
                                const img = card ? card.querySelector('img') : null;
                                const src = img ? (img.src || '') : '';
                                const text = ((card && card.textContent) || '').trim().slice(0, 80);
                                return {
                                    idx: idx,
                                    src: src,
                                    text: text,
                                    top: Math.round(r.top),
                                    left: Math.round(r.left),
                                    used_sel: usedSel,
                                };
                            });
                        }
                    """, checkbox_selectors)
                except Exception as e:
                    self.log(f"    snapshot checkbox 失败: {e}")
                    return []

            def _fingerprint(item: dict) -> str:
                """生成稳定的身份指纹：优先 img.src，没有则用 text + position"""
                if item.get("src"):
                    return f"src:{item['src']}"
                if item.get("text"):
                    return f"text:{item['text']}"
                return f"pos:{item.get('top', 0)}x{item.get('left', 0)}"

            before_snapshot = _snapshot_checkboxes()
            before_fingerprints = {_fingerprint(it) for it in before_snapshot}
            self.log(f"  上传前 checkbox 快照：{len(before_snapshot)} 个")

            # ─── 投递模式：默认一次性批量上传 ───
            # 如果发现某站点批量上传丢失，可在 DSL 里设置 "batch_upload": false 改逐个上传
            # 配合「人工接管 + 样本累积」机制，长期看 AI 会学到更稳的处理方式
            batch_upload = bool(a.get("batch_upload", True))
            # 逐个模式下每张图上传后的等待时间（毫秒）
            per_file_wait_ms = int(a.get("per_file_wait_ms", 1500))

            def _locate_file_input():
                """重新定位 input[type=file]，每次上传前都重找（input 可能被 reset）"""
                # 优先用 DSL 提供的 selector
                try:
                    action_eff = dict(a)
                    action_eff["selector"] = sel
                    loc, _used = self._find_visible_locator(action_eff, timeout, require_visible=False)
                    return loc
                except Exception:
                    pass
                # 兜底：用页面里最新出现的 input[type=file]
                inputs = self.page.locator("input[type='file']")
                for _ in range(20):
                    try:
                        if inputs.count() > 0:
                            break
                    except Exception:
                        pass
                    self.page.wait_for_timeout(200)
                try:
                    count = inputs.count()
                except Exception:
                    count = 0
                if count == 0:
                    raise DSLError("找不到任何 input[type=file]")
                # 优先用 before_input_count 之后新出现的（弹窗里的新 input）
                start_idx = max(before_input_count, 0)
                if count > start_idx:
                    return inputs.nth(count - 1)  # 最新出现的那个
                return inputs.last

            if batch_upload:
                # 一次性投递所有文件（适用于网站没有多文件 bug 时）
                self.log(f"  📦 模式：一次性批量上传 {n} 张")
                try:
                    input_loc = _locate_file_input()
                    input_loc.set_input_files(files, timeout=10000)
                    self.log(f"  ✓ 已投递 {n} 个文件")
                except Exception as inject_err:
                    raise DSLError(f"批量投递失败：{inject_err}")
                # 给浏览器时间处理
                wait_upload = max(800, n * 250)
                self.log(f"  等浏览器处理 {wait_upload}ms ...")
                self.page.wait_for_timeout(wait_upload)
            else:
                # ⭐ 逐个上传（默认模式，规避批量上传丢失的 bug）
                self.log(f"  📋 模式：逐个上传 {n} 张（每张间隔 {per_file_wait_ms}ms）")
                for idx, file_path in enumerate(files, 1):
                    fname = _P(file_path).name
                    self.log(f"    [{idx}/{n}] 上传 {fname}")
                    try:
                        input_loc = _locate_file_input()
                        input_loc.set_input_files(file_path, timeout=8000)
                    except Exception as inject_err:
                        # 单张失败时给一次重试机会
                        self.log(f"      ✗ 第 {idx} 张投递失败：{inject_err}，500ms 后重试一次")
                        self.page.wait_for_timeout(500)
                        try:
                            input_loc = _locate_file_input()
                            input_loc.set_input_files(file_path, timeout=8000)
                        except Exception as retry_err:
                            raise DSLError(
                                f"第 {idx}/{n} 张「{fname}」投递失败：{retry_err}\n"
                                f"已上传 {idx-1} 张，请人工接管或停止"
                            )
                    # 等浏览器处理这一张，再传下一张
                    self.page.wait_for_timeout(per_file_wait_ms)
                self.log(f"  ✓ {n} 张全部投递完成")
                # 全部投完再额外等一下（让服务器返回最后一张的 CDN URL）
                self.page.wait_for_timeout(800)

            # ─── 动态轮询找 checkbox（最多 4 秒）───
            self.log(f"  等待至少 {n} 个 checkbox 可见 ...")
            checkbox_loc = None
            used_cs = None
            for cs in checkbox_selectors:
                try:
                    loc = self.page.locator(cs)
                    polls = 0
                    while polls < 20:
                        try:
                            if loc.count() >= n:
                                checkbox_loc = loc
                                used_cs = cs
                                self.log(f"  ✓ 用 selector「{cs}」找到 {loc.count()} 个 checkbox")
                                break
                        except Exception:
                            pass
                        self.page.wait_for_timeout(200)
                        polls += 1
                    if checkbox_loc is not None:
                        break
                except Exception:
                    continue

            if checkbox_loc is None:
                # 没等到足够数量就用第一个 count>0 的兜底
                for cs in checkbox_selectors:
                    try:
                        loc = self.page.locator(cs)
                        if loc.count() > 0:
                            checkbox_loc = loc
                            used_cs = cs
                            self.log(f"  ⚠ 未等到 {n} 个，先用 selector「{cs}」（找到 {loc.count()} 个）")
                            break
                    except Exception:
                        continue

            if checkbox_loc is None:
                raise DSLError(
                    "找不到任何 checkbox。Element UI 标准结构是 span.el-checkbox__inner，"
                    "请去网页 F12 看素材库实际 DOM 结构。"
                )

            # ─── 决定要勾哪些（核心：auto_diff 不写死方向）───
            total = checkbox_loc.count()
            indices = []
            strategy_used = select_strategy

            if select_strategy == "auto_diff":
                # 重新 snapshot，对比 before 找出"新出现的"checkbox
                after_snapshot = _snapshot_checkboxes()
                new_items = [it for it in after_snapshot
                             if _fingerprint(it) not in before_fingerprints]

                if len(new_items) >= n:
                    # 找到了至少 N 个新图，按它们在 DOM 中的实际 idx 来勾选
                    # 不限制位置（top-left / bottom-right 都行）
                    indices = [it["idx"] for it in new_items[:n]]
                    self.log(f"  ✓ 差集识别到 {len(new_items)} 个新 checkbox，勾选前 {n} 个")
                    self.log(f"    新图位置（top, left, src/text 前 40 字）:")
                    for it in new_items[:min(5, n)]:
                        ident = (it.get("src") or it.get("text") or "")[:40]
                        self.log(f"      idx={it['idx']}  top={it['top']}  left={it['left']}  {ident}")
                    strategy_used = "auto_diff(new_items)"
                elif new_items:
                    # 没到 N 个但有几个新的，先勾选这几个
                    indices = [it["idx"] for it in new_items]
                    self.log(f"  ⚠ 差集只识别到 {len(new_items)} 个新 checkbox（期望 {n}），全部勾选")
                    strategy_used = f"auto_diff(partial:{len(new_items)})"
                else:
                    # 差集识别失败（可能 snapshot 没拿到指纹）→ 回退 first_n
                    indices = list(range(min(n, total)))
                    self.log(f"  ⚠ 差集没识别到新图，回退 first_n（前 {len(indices)} 个）")
                    strategy_used = "auto_diff→fallback(first_n)"
            elif select_strategy == "first_n":
                indices = list(range(min(n, total)))
            else:  # last_n
                indices = list(range(max(0, total - n), total))

            sample_indices = indices[:5] + (['...'] if len(indices) > 5 else [])
            self.log(f"  开始勾选 {len(indices)} 个 checkbox（策略：{strategy_used}，索引：{sample_indices}）")

            success = 0
            for i in indices:
                try:
                    box = checkbox_loc.nth(i)
                    box.scroll_into_view_if_needed(timeout=2500)
                    box.click(timeout=2500)
                    success += 1
                except Exception as click_err:
                    self.log(f"    ✗ 勾选第 {i} 个失败：{click_err}")

            self.log(f"  ✓ 已勾选 {success}/{len(indices)} 个")
            self.page.wait_for_timeout(wait_after)

        elif t == "delay":
            ms = a.get("ms", 1000)
            self.log(f"→ 等待 {ms}ms")
            self.page.wait_for_timeout(ms)

        elif t == "press":
            key = a.get("key", "Enter")
            self.log(f"→ 按键 {key}")
            sel = a.get("selector")
            if sel:
                self.page.press(sel, key)
            else:
                self.page.keyboard.press(key)

        elif t == "scroll":
            to = a.get("to", "bottom")
            sel = a.get("selector")
            # ⭐ frameset 场景：滚动可能发生在子 iframe 的容器里（聚水潭详情弹窗 #flow_ctrl）。
            #    先在所有 frame 里找滚动容器；找到就在它所在的 frame 上下文执行滚动，
            #    没有 selector 或找不到就退回到主框架的 window 滚动。
            scroll_ctx = self.page          # 默认主框架
            container_found = False
            if sel:
                try:
                    for frame in list(self.page.frames):
                        try:
                            if frame.is_detached():
                                continue
                            if frame.locator(sel).count() > 0:
                                scroll_ctx = frame
                                container_found = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            try:
                if container_found:
                    # 在容器内部滚动（top/bottom/精确像素都支持）
                    if to == "top":
                        scroll_ctx.evaluate(
                            f"() => {{ const e=document.querySelector({sel!r}); if(e) e.scrollTop=0; }}")
                    else:  # bottom 或其它，统统滚到底（这类步骤多为浏览详情，无副作用）
                        scroll_ctx.evaluate(
                            f"() => {{ const e=document.querySelector({sel!r}); if(e) e.scrollTop=e.scrollHeight; }}")
                    self.log(f"→ 在容器 {sel[:40]} 内滚动（{to}）")
                elif sel:
                    # 有 selector 但没在任何 frame 找到容器 → 尽力 scrollIntoView
                    try:
                        self.page.wait_for_selector(sel, timeout=min(timeout, 3000))
                    except Exception:
                        pass
                    self.page.evaluate(
                        f"() => document.querySelector({sel!r})?.scrollIntoView({{block:'center'}})")
                    self.log(f"→ 滚动到元素 {sel[:40]}")
                elif to == "top":
                    self.page.evaluate("window.scrollTo(0, 0)")
                else:
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception as scroll_err:
                # 滚动失败不该中断整条流程（多为浏览性动作）
                self.log(f"  ⚠ 滚动跳过：{scroll_err}")

        else:
            raise DSLError(f"未知指令类型: {t}")


# ════════════════════════════════════════
#  steps → DSL（保留 xpath 和 scoped 兜底）
# ════════════════════════════════════════
def steps_to_dsl(steps: list, init_url: str, name: str = "") -> dict:
    actions = []
    if init_url:
        actions.append({"type": "goto", "url": init_url})

    for s in steps:
        if not s.get("selected", True):
            continue
        at = s.get("action_type", "click")
        sel = s.get("selector", "")
        xp = s.get("xpath", "")
        scoped = s.get("scoped_selector", "")
        col = (s.get("excel_column") or "").strip()

        # 通用字段
        common = {"selector": sel}
        if xp:
            common["xpath"] = xp
        if scoped:
            common["scoped_selector"] = scoped

        if at == "input":
            a = {"type": "fill", **common}
            if col:
                a["from_excel"] = col
            else:
                a["value"] = s.get("value", "")
            actions.append(a)
        elif at == "select":
            a = {"type": "select", **common}
            if col:
                a["from_excel"] = col
            else:
                a["value"] = s.get("value", "")
            actions.append(a)
        elif at == "check":
            actions.append({"type": "check", **common,
                          "checked": bool(s.get("value", True))})
        elif at == "upload":
            a = {"type": "upload", **common}
            if col:
                a["from_excel"] = col
            else:
                a["value"] = s.get("value", "")
            actions.append(a)
        elif at == "select_option":
            a = {"type": "select_option", **common, "wait_after": 500}
            if col:
                a["from_excel"] = col
                a["match_by_text"] = True
            actions.append(a)
        else:  # click
            # 普通点击：等待时间加长，给可能触发的弹窗/下拉留时间
            actions.append({"type": "click", **common, "wait_after": 700})

    return {
        "version": "1.0",
        "name": name,
        "actions": actions,
    }
