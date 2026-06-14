import json
import logging
import os
import threading
import time
import traceback
from pathlib import Path

from app.browser import launch_browser_context
from app.paths import resource
from app.rules import rules_to_js
from app.vision_capture import save_privacy_focus_screenshot

INJECT_JS = resource("app", "inject.js")

# 浏览器持久化 profile 目录（保留登录态）
PROFILE_DIR = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "好办法自动化" / "edge_profile"

log = logging.getLogger(__name__)

VISION_FOCUS_RADIUS = int(os.environ.get("HBF_VISION_FOCUS_RADIUS", "200"))
VISION_BLUR_RADIUS = int(os.environ.get("HBF_VISION_BLUR_RADIUS", "18"))
VISION_JPEG_QUALITY = int(os.environ.get("HBF_VISION_JPEG_QUALITY", "82"))
VISION_MAX_PER_FLOW = int(os.environ.get("HBF_VISION_MAX_PER_FLOW", "50"))


class Recorder:
    def __init__(self, on_step=None, on_done=None, on_error=None, rules: dict = None):
        self.on_step = on_step
        self.on_done = on_done
        self.on_error = on_error
        self.rules = rules or {}
        self.steps: list[dict] = []
        self._thread: threading.Thread | None = None
        self._running = False
        self._done_requested = False
        self._lock = threading.Lock()
        self._pending_visual_steps: list[dict] = []
        self._pending_prepare_visuals: list[dict] = []
        self._prepared_visuals: dict[str, dict] = {}
        self._vision_count = 0
        self.capture_dir: Path | None = None
        self.init_url: str = ""
        self._active_page = None             # 多标签页：当前活跃的 page
        self._needs_broadcast_count = False  # 多标签页：是否要广播 step 总数
        self._paused = False                 # 多 frame：当前暂停状态（top frame 上报）
        self._needs_broadcast_paused = False # 多 frame：是否要广播 paused 状态

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def start(self, url: str, capture_dir: Path | str | None = None,
              browser_mode: str = "normal",
              cdp_profile_dir: "Path | None" = None):
        """
        browser_mode:
          - "normal": Playwright 自带 Edge（普通自动化，会被反爬网站识别）
          - "stealth_cdp": CDP 附加到用户真实 Edge（无自动化痕迹，全局默认）
        cdp_profile_dir: stealth_cdp 用的 Edge user-data-dir；
                         None=普通真实 Edge(PROFILE_DIR)，聚水潭传 JST_PROFILE_DIR
        """
        if self._running:
            return
        self.steps = []
        self._pending_visual_steps = []
        self._pending_prepare_visuals = []
        self._prepared_visuals = {}
        self._vision_count = 0
        self.capture_dir = Path(capture_dir) if capture_dir else None
        if self.capture_dir:
            self.capture_dir.mkdir(parents=True, exist_ok=True)
        self._done_requested = False
        self.init_url = url
        self._browser_mode = browser_mode
        self._cdp_profile_dir = cdp_profile_dir
        self._running = True
        self._thread = threading.Thread(target=self._run, args=(url,), daemon=True)
        self._thread.start()

    # 聚水潭等防爬网站专用的 Edge profile（跟普通模式分开）
    JST_PROFILE_DIR = Path(os.environ.get("USERPROFILE", str(Path.home()))) \
                      / "Documents" / "好办法自动化" / "edge_jst_profile"

    def _run(self, url: str):
        pw = None
        browser = None
        context = None
        edge_process = None  # CDP 模式下的真实 Edge 子进程
        self._active_page = None
        try:
            from playwright.sync_api import sync_playwright
            log.info("启动 Playwright...")
            pw = sync_playwright().start()

            mode = getattr(self, "_browser_mode", "normal")
            if mode == "stealth_cdp":
                # ⭐ 防检测模式：用 CDP 附加到用户真实 Edge
                log.info("启动防检测模式（CDP 附加用户真实 Edge）...")
                from app.browser import launch_cdp_attached_context
                context, browser, edge_process = launch_cdp_attached_context(
                    pw,
                    edge_profile_dir=getattr(self, "_cdp_profile_dir", None) or PROFILE_DIR,
                    initial_url=url,
                    log_fn=lambda m: log.info(m),
                )
            else:
                # 普通模式：Playwright 自带 Edge
                log.info("启动浏览器（普通模式）...")
                context, browser = launch_browser_context(
                    pw,
                    headless=False,
                    persist_dir=PROFILE_DIR,  # 保留登录 cookies
                    viewport=None,            # 不锁定视口，页面跟随窗口大小
                    locale="zh-CN",
                    maximized=True,           # 启动时窗口最大化
                )
            # persistent context 有时已有空白 page，复用它；没有就 new 一个
            pages = context.pages
            page = pages[0] if pages else context.new_page()
            self._active_page = page

            # ⭐ 关键改动：context 级别暴露函数，所有标签页（含弹窗新开的）都能调用
            context.expose_function("__hbf_prepare_visual", self._handle_prepare_visual)
            context.expose_function("__hbf_record", self._handle_record)
            context.expose_function("__hbf_done", self._handle_done)
            context.expose_function("__hbf_undo", self._handle_undo)
            context.expose_function("__hbf_pause", self._handle_pause)

            # 优先用知识库里的 inject_js（远程更新的最新版）
            override = (self.rules or {}).get("inject_js_override", "")
            if override and len(override) > 100 and "target_box" in override and "click_x" in override:
                js_code = override
                log.info("使用远程知识库的 inject.js")
            else:
                js_code = INJECT_JS.read_text(encoding="utf-8")
                log.info("使用本地内置的 inject.js")

            # ⭐ 防检测模式：先注入 stealth 脚本，再注入 inject.js
            stealth_js = ""
            if mode == "stealth_cdp":
                try:
                    stealth_path = INJECT_JS.parent / "stealth.js"
                    if stealth_path.exists():
                        stealth_js = stealth_path.read_text(encoding="utf-8")
                        log.info("✓ 已加载防检测 stealth.js")
                except Exception as e:
                    log.warning(f"读取 stealth.js 失败: {e}")

            # 把规则当全局变量注入到页面
            full_js = (stealth_js + "\n" if stealth_js else "") + rules_to_js(self.rules) + "\n" + js_code
            # ⭐ context 级别注入脚本，所有新标签页自动获得 inject.js
            context.add_init_script(script=full_js)

            # ⭐ 监听新标签页打开（target=_blank / window.open 等）
            def _on_new_page(new_page):
                try:
                    log.info(f"📑 新标签页打开（{len(context.pages)} 个）: {new_page.url or '(loading)'}")
                except Exception:
                    log.info("📑 新标签页打开")
                self._active_page = new_page
                # 把新页面 focus / load / close 也跟踪起来
                try:
                    new_page.on("close", lambda: self._on_page_closed(new_page, context))
                except Exception:
                    pass
                try:
                    new_page.on("framenavigated", lambda f: self._on_frame_navigated(new_page, f))
                except Exception:
                    pass
                # 标记需要广播，让新页面的工具栏立刻同步到全局 step 数
                self._needs_broadcast_count = True

            context.on("page", _on_new_page)
            # 初始 page 也挂上 close 监听
            try:
                page.on("close", lambda: self._on_page_closed(page, context))
            except Exception:
                pass

            # CDP 模式下 Edge 启动时已经带 initial_url 打开了页面，
            # 但当时 inject.js 还没注入，需要 reload 让 init_script 生效
            log.info(f"打开网页: {url}")
            if mode == "stealth_cdp":
                # 检查当前页是否已是目标 URL；若是就 reload，让 stealth + inject 生效
                try:
                    current = page.url or ""
                except Exception:
                    current = ""
                if current and current.split("#")[0].rstrip("/") == url.split("#")[0].rstrip("/"):
                    log.info("CDP 模式：页面已是目标，reload 让 stealth 生效")
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=30000)
                    except Exception as e:
                        log.warning(f"reload 失败: {e}，回退 goto")
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                else:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
            else:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # ⭐ 关键修复：强制把 inject.js 注入到所有「已经存在」的 frame
            #    场景：聚水潭老订单页是 frameset 多 iframe 架构
            #          context.add_init_script 只对"之后"navigation 的 frame 生效
            #          已经加载好的旧 iframe（比如左侧筛选）拿不到 inject.js
            #          → 这里手动遍历所有 frame，没注入的就 evaluate 一遍
            self._inject_into_all_frames(context, full_js)
            self._setup_frame_attach_handlers(context, full_js)

            while self._running:
                # 用"活跃 page"做轮询和截图。如果当前活跃 page 关了，切到任何还开着的 page。
                active = self._get_alive_page(context)
                if active is None:
                    log.warning("所有标签页都关了，录制结束")
                    break

                # 诊断：周期性打印 page/frame 结构（仅结构变化时输出，不刷屏）
                _now = time.time()
                if _now >= getattr(self, "_diag_next_ts", 0):
                    self._diag_next_ts = _now + 1.2
                    self._diag_dump_structure(context)

                # 跨标签页广播 step 总数（让每个工具栏数字一致）
                if self._needs_broadcast_count:
                    self._needs_broadcast_count = False
                    self._broadcast_step_count(context)

                # 跨 frame 广播 paused 状态（让 iframe 也跟着停 / 继续）
                if self._needs_broadcast_paused:
                    self._needs_broadcast_paused = False
                    self._broadcast_paused(context)

                self._capture_prepare_visuals(context, active)
                self._capture_pending_visuals(context, active)
                if self._done_requested:
                    with self._lock:
                        pending = bool(self._pending_visual_steps)
                    if not pending:
                        self._cleanup_prepared_visuals(max_age=0)
                        self._running = False
                        if self.on_done:
                            self.on_done(list(self.steps))
                        break
                try:
                    active.wait_for_timeout(50)
                except Exception:
                    # 活跃页面可能在 wait 过程中被关掉，下次循环重新选
                    pass

        except Exception as e:
            detail = traceback.format_exc()
            log.error(f"录制出错:\n{detail}")
            if self.on_error:
                self.on_error(str(e))
        finally:
            self._running = False
            self._active_page = None
            # CDP 模式：用户的真实 Edge 不应该被我们强制关闭，
            #          让 Playwright disconnect 即可，Edge 进程留给用户继续用
            mode = getattr(self, "_browser_mode", "normal")
            try:
                if mode == "stealth_cdp":
                    # CDP 模式只 disconnect，不 close（不杀 Edge 进程）
                    if browser:
                        try: browser.close()  # close 在 CDP 模式下等同 disconnect
                        except Exception: pass
                else:
                    # persistent context 模式下 browser 是 None，关 context 即可
                    if browser:
                        browser.close()
                    elif context:
                        context.close()
            except Exception:
                pass
            try:
                if pw:
                    pw.stop()
            except Exception:
                pass
            # CDP 模式：edge_process 是用户的 Edge，不要 terminate
            # （用户可能想继续用浏览器查看结果）
            _ = edge_process

    def _on_page_closed(self, closed_page, context):
        """某个标签页关闭"""
        try:
            log.info(f"📑 标签页关闭: {closed_page.url}")
        except Exception:
            log.info("📑 标签页关闭")
        if self._active_page is closed_page:
            self._active_page = self._get_alive_page(context)

    def _on_frame_navigated(self, page, frame):
        """页面跳转 — 更新 active page 跟踪"""
        try:
            if frame == page.main_frame:
                # 这个 page 刚跳转完成，把它设为活跃
                self._active_page = page
        except Exception:
            pass

    def _inject_into_all_frames(self, context, js_code: str) -> None:
        """
        强制把 inject.js 注入到 context 里所有「已经加载」的 frame。

        必要性：context.add_init_script 只对未来 navigation 生效。
                CDP 附加时 Edge 可能已经加载好 iframe（如聚水潭老订单 frameset），
                这些 iframe 不会自动拿到 inject.js，需要手动 evaluate。
        """
        try:
            for p in context.pages:
                try:
                    if p.is_closed():
                        continue
                except Exception:
                    continue
                self._inject_into_page_frames(p, js_code)
        except Exception as e:
            log.debug(f"inject all frames failed: {e}")

    def _inject_into_page_frames(self, page, js_code: str) -> None:
        """把 inject.js 注入到一个 page 的所有 frame（含主文档 + 所有 iframe）"""
        try:
            frames = list(page.frames)
        except Exception:
            return
        for frame in frames:
            try:
                if frame.is_detached():
                    continue
            except Exception:
                continue
            try:
                # 已经注入过的 frame 跳过（inject.js 自己有 __hbf_injected 守卫）
                already = False
                try:
                    already = frame.evaluate("() => !!window.__hbf_injected")
                except Exception:
                    already = False
                if already:
                    continue
                try:
                    frame.evaluate(js_code)
                    try:
                        fu = (frame.url or "")[:80]
                    except Exception:
                        fu = ""
                    log.info(f"📌 强制 inject 到 frame: {fu}")
                except Exception as e:
                    log.debug(f"frame evaluate inject failed: {e}")
            except Exception as e:
                log.debug(f"frame inject loop failed: {e}")

    def _setup_frame_attach_handlers(self, context, js_code: str) -> None:
        """
        给所有 page 挂上 frameattached / framenavigated 监听器：
        每当新 frame 出现，自动注入 inject.js。

        Playwright 的 context.add_init_script 理论上对新 frame 自动生效，
        但某些老 frameset / document.write 写入的 iframe 不走 navigation 流程，
        这里加双保险。
        """
        try:
            for p in context.pages:
                self._attach_frame_listeners(p, js_code)
        except Exception as e:
            log.debug(f"setup frame attach handlers failed: {e}")
        # 新打开的 page 也要挂
        try:
            def _on_new_page_inject(np):
                self._attach_frame_listeners(np, js_code)
                # 新 page 也立即扫一遍现有 frame
                try:
                    np.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                self._inject_into_page_frames(np, js_code)
            context.on("page", _on_new_page_inject)
        except Exception:
            pass

    def _attach_frame_listeners(self, page, js_code: str) -> None:
        """给一个 page 挂 frameattached / framenavigated 监听"""
        def _on_frame_attached(frame):
            try:
                # 等 frame 至少完成 domcontentloaded
                try:
                    frame.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                if frame.is_detached():
                    return
                already = False
                try:
                    already = frame.evaluate("() => !!window.__hbf_injected")
                except Exception:
                    already = False
                if not already:
                    try:
                        frame.evaluate(js_code)
                        try: fu = (frame.url or "")[:80]
                        except Exception: fu = ""
                        log.info(f"📌 frameattached → inject: {fu}")
                    except Exception:
                        pass
            except Exception:
                pass

        def _on_frame_navigated(frame):
            # 跳转后的 frame 由 add_init_script 自动注入；这里做兜底验证
            try:
                if frame.is_detached():
                    return
                # 给浏览器一点时间执行 init script
                try:
                    frame.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                already = False
                try:
                    already = frame.evaluate("() => !!window.__hbf_injected")
                except Exception:
                    already = False
                if not already:
                    try:
                        frame.evaluate(js_code)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            page.on("frameattached", _on_frame_attached)
        except Exception:
            pass
        try:
            page.on("framenavigated", _on_frame_navigated)
        except Exception:
            pass

    def _get_alive_page(self, context):
        """返回任意一个还活着（没关）的 page，优先用 self._active_page"""
        try:
            if self._active_page and not self._active_page.is_closed():
                return self._active_page
        except Exception:
            pass
        try:
            # 倒序遍历：优先用最近的标签页
            for p in reversed(context.pages):
                try:
                    if not p.is_closed():
                        self._active_page = p
                        return p
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _find_page_by_url(self, context, target_url: str):
        """根据 url 找对应的 page（用于截图：取步骤记录时所在的页面）"""
        if not target_url:
            return None
        try:
            for p in context.pages:
                try:
                    if p.is_closed():
                        continue
                    if p.url == target_url:
                        return p
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _handle_record(self, data_json: str):
        try:
            step = json.loads(data_json)
            with self._lock:
                self.steps.append(step)
                if self._should_capture_visual(step):
                    self._pending_visual_steps.append(step)
                self._needs_broadcast_count = True
            if self.on_step:
                self.on_step(step)
        except Exception:
            log.error(f"接收步骤失败: {traceback.format_exc()}")

    def _broadcast_step_count(self, context) -> None:
        """把全局 step 总数广播到所有 page 的所有 frame（含 iframe）。
        - 主 frame：工具栏数字会更新
        - iframe：UI 不存在但 stepCount 会同步，避免 MAX_STEPS 限制错误截断录制
        多 frame 录制（聚水潭 frameset 等）必须遍历每个 page.frames，否则
        iframe 内点击会让 iframe 的本地 stepCount 和 Python 真实值越走越远。
        """
        try:
            total = len(self.steps)
        except Exception:
            return
        js = (
            "(n) => { if (typeof window.__hbf_set_global_count === 'function') "
            "window.__hbf_set_global_count(n); }"
        )
        try:
            for p in context.pages:
                try:
                    if p.is_closed():
                        continue
                except Exception:
                    continue
                try:
                    frames = list(p.frames)
                except Exception:
                    frames = []
                for frame in frames:
                    try:
                        if frame.is_detached():
                            continue
                    except Exception:
                        continue
                    try:
                        frame.evaluate(js, total)
                    except Exception:
                        # 单个 frame 失败不影响其他
                        pass
        except Exception:
            pass

    def _diag_dump_structure(self, context, force=False):
        """打印所有 page / frame 的结构 + 注入状态 + binding 可用性。

        用于诊断聚水潭订单页（左侧筛选 sidebar / 中间订单列表 / 详情弹窗）三页录制：
          ✓注入   = inject.js 在该 frame 跑起来了（window.__hbf_injected）
          ✓可上报 = window.__hbf_record 在该 frame 是函数（点击能传回 Python）
        只在结构变化时打印，避免刷屏。
        关键看点：如果某个 frame 是「✓注入 但 ✗无binding」，说明点击监听到了
        但传不回 Python —— 这就是「只监听一个页面」的真正原因。
        """
        try:
            lines = []
            sig_parts = []
            try:
                page_list = list(context.pages)
            except Exception:
                page_list = []
            for pi, p in enumerate(page_list):
                try:
                    if p.is_closed():
                        continue
                except Exception:
                    continue
                try:
                    purl = p.url or "(blank)"
                except Exception:
                    purl = "(?)"
                sig_parts.append(purl)
                lines.append(f"  [标签页 {pi}] {purl[:90]}")
                try:
                    frames = list(p.frames)
                except Exception:
                    frames = []
                for fi, fr in enumerate(frames):
                    try:
                        if fr.is_detached():
                            continue
                    except Exception:
                        continue
                    try:
                        furl = fr.url or "(blank)"
                    except Exception:
                        furl = "(?)"
                    injected = False
                    has_record = False
                    try:
                        injected = bool(fr.evaluate("() => !!window.__hbf_injected"))
                    except Exception:
                        pass
                    try:
                        has_record = bool(fr.evaluate(
                            "() => typeof window.__hbf_record === 'function'"))
                    except Exception:
                        pass
                    try:
                        is_main = (fr == p.main_frame)
                    except Exception:
                        is_main = False
                    role = "主框架  " if is_main else "子iframe"
                    mark = "✓注入" if injected else "✗未注入"
                    bind = "✓可上报" if has_record else "✗无binding(点击会丢)"
                    sig_parts.append(f"{furl}|{injected}|{has_record}")
                    lines.append(f"        └[{role} {fi}] {mark} {bind}  {furl[:72]}")
            sig = "||".join(sig_parts)
            if not force and sig == getattr(self, "_diag_last_sig", None):
                return
            self._diag_last_sig = sig
            log.info("\n===== 聚水潭 页面/iframe 结构诊断 =====\n"
                     + "\n".join(lines)
                     + "\n======================================")
        except Exception:
            pass

    def _handle_done(self):
        self._done_requested = True

    def _handle_pause(self, paused_bool):
        """top frame 工具栏点暂停 → Python 收到 → 广播到所有 frame 同步状态"""
        try:
            self._paused = bool(paused_bool)
        except Exception:
            self._paused = False
        self._needs_broadcast_paused = True

    def _broadcast_paused(self, context) -> None:
        """把 paused 状态广播到每个 page 的每个 frame，保证 iframe 也停录"""
        try:
            paused = bool(getattr(self, "_paused", False))
        except Exception:
            return
        js = (
            "(b) => { if (typeof window.__hbf_set_paused === 'function') "
            "window.__hbf_set_paused(b); }"
        )
        try:
            for p in context.pages:
                try:
                    if p.is_closed():
                        continue
                except Exception:
                    continue
                try:
                    frames = list(p.frames)
                except Exception:
                    frames = []
                for frame in frames:
                    try:
                        if frame.is_detached():
                            continue
                    except Exception:
                        continue
                    try:
                        frame.evaluate(js, paused)
                    except Exception:
                        pass
        except Exception:
            pass

    def _handle_prepare_visual(self, data_json: str):
        try:
            item = json.loads(data_json)
            key = str(item.get("visual_key") or "").strip()
            if not key:
                return
            with self._lock:
                if key in self._prepared_visuals:
                    return
                if any(str(x.get("visual_key")) == key for x in self._pending_prepare_visuals):
                    return
                self._pending_prepare_visuals.append(item)
        except Exception:
            log.debug("prepare visual request failed", exc_info=True)

    def _handle_undo(self):
        """删除最后一条记录"""
        removed = None
        remove_screenshot = False
        with self._lock:
            if self.steps:
                removed = self.steps.pop()
                self._pending_visual_steps = [
                    s for s in self._pending_visual_steps if s is not removed
                ]
                remove_screenshot = bool(removed.get("screenshot_file"))
                if remove_screenshot and self._vision_count > 0:
                    self._vision_count -= 1
                self._needs_broadcast_count = True  # 多标签页：广播新的总数
            current_steps = list(self.steps)
        if removed is not None:
            if remove_screenshot:
                self._delete_step_screenshot(removed)
            # 重新编号
            for i, s in enumerate(current_steps, 1):
                s["step_index"] = i
            if self.on_step:
                # 通知 UI 刷新（传 None 表示是 undo 操作）
                try:
                    self.on_step({"_undo": True})
                except Exception:
                    pass

    def _delete_step_screenshot(self, step: dict) -> None:
        if not self.capture_dir:
            return
        screenshot_file = str(step.get("screenshot_file") or "").strip()
        if not screenshot_file:
            return
        target = self.capture_dir / Path(screenshot_file).name
        try:
            capture_root = self.capture_dir.resolve()
            target_path = target.resolve()
            if target_path.parent == capture_root and target_path.exists():
                target_path.unlink()
        except Exception:
            log.debug("delete step screenshot failed", exc_info=True)

    def stop(self):
        self._running = False

    def _should_capture_visual(self, step: dict) -> bool:
        if self._vision_count >= VISION_MAX_PER_FLOW:
            return False
        if not step.get("visual_key"):
            return False
        has_box = bool(step.get("target_box"))
        has_click = step.get("click_x") is not None and step.get("click_y") is not None
        if not has_box and not has_click:
            return False
        return step.get("action_type") in {
            "click", "check", "input", "select", "select_option", "upload"
        }

    def _capture_prepare_visuals(self, context, default_page):
        """处理待截图队列。对每个 item，根据它所在的页面 URL 找正确的 page，找不到就用 default_page。"""
        self._cleanup_prepared_visuals()
        while True:
            with self._lock:
                if not self._pending_prepare_visuals:
                    return
                item = self._pending_prepare_visuals.pop(0)
                key = str(item.get("visual_key") or "").strip()
                if not key or key in self._prepared_visuals:
                    continue
            # 找到这个 prepare 是在哪个标签页里发起的
            target_page = self._find_page_by_url(context, str(item.get("url") or "")) or default_page
            if target_page is None or self._is_page_closed(target_page):
                continue
            try:
                shot = self._make_prepared_screenshot(target_page, item)
            except Exception:
                log.debug("capture prepared screenshot failed", exc_info=True)
                shot = None
            if not shot:
                continue
            with self._lock:
                self._prepared_visuals[key] = shot

    def _capture_pending_visuals(self, context, default_page):
        while True:
            with self._lock:
                if not self._pending_visual_steps:
                    return
                step = self._pending_visual_steps.pop(0)
                if self._vision_count >= VISION_MAX_PER_FLOW:
                    continue
                if not any(s is step for s in self.steps):
                    continue
                if step.get("screenshot_file"):
                    continue

            # 找到这一步是在哪个标签页里录的
            target_page = self._find_page_by_url(context, str(step.get("url") or "")) or default_page
            if target_page is None or self._is_page_closed(target_page):
                continue

            try:
                shot = self._make_privacy_screenshot(target_page, step)
            except Exception:
                log.debug("capture privacy screenshot failed", exc_info=True)
                shot = None

            if not shot:
                continue

            with self._lock:
                if any(s is step for s in self.steps):
                    step["screenshot_file"] = shot["file"]
                    step["screenshot_focus"] = shot["focus"]
                    step["screenshot_kind"] = "privacy_focus_viewport"
                    step["screenshot_width"] = shot["width"]
                    step["screenshot_height"] = shot["height"]
                    self._vision_count += 1

    @staticmethod
    def _is_page_closed(page) -> bool:
        try:
            return page.is_closed()
        except Exception:
            return True

    def _make_privacy_screenshot(self, page, step: dict) -> dict | None:
        if not self.capture_dir:
            return None
        prepared = None
        visual_key = str(step.get("visual_key") or "").strip()
        if visual_key:
            deadline = time.time() + 1.5
            while time.time() < deadline:
                with self._lock:
                    prepared = self._prepared_visuals.pop(visual_key, None)
                if prepared:
                    break
                time.sleep(0.05)
            if not prepared:
                return None

        filename = f"{int(step.get('step_index') or (self._vision_count + 1)):03d}.jpg"
        out_path = self.capture_dir / filename
        if prepared:
            return self._move_prepared_to_final(prepared, out_path, filename)

        box = step.get("target_box") or {}
        try:
            raw_x = step.get("click_x") if step.get("click_x") is not None else box.get("cx")
            raw_y = step.get("click_y") if step.get("click_y") is not None else box.get("cy")
            cx = float(raw_x)
            cy = float(raw_y)
        except Exception:
            x0 = float(box.get("x", 0))
            y0 = float(box.get("y", 0))
            w0 = float(box.get("width", 0))
            h0 = float(box.get("height", 0))
            cx = x0 + w0 / 2
            cy = y0 + h0 / 2

        raw = page.screenshot(
            full_page=False,
            type="jpeg",
            quality=VISION_JPEG_QUALITY,
        )
        meta = save_privacy_focus_screenshot(
            raw,
            out_path,
            cx,
            cy,
            radius=VISION_FOCUS_RADIUS,
            blur_radius=VISION_BLUR_RADIUS,
            quality=VISION_JPEG_QUALITY,
        )
        return {"file": f"screenshots/{filename}", **meta}

    def _move_prepared_to_final(self, prepared: dict, out_path: Path, filename: str) -> dict | None:
        pending_path = Path(prepared.get("path", ""))
        try:
            if pending_path.exists():
                if out_path.exists():
                    out_path.unlink()
                pending_path.replace(out_path)
                return {
                    "file": f"screenshots/{filename}",
                    "width": prepared.get("width"),
                    "height": prepared.get("height"),
                    "focus": prepared.get("focus"),
                }
        except Exception:
            log.debug("use prepared screenshot failed", exc_info=True)
        return None

    def _make_prepared_screenshot(self, page, item: dict) -> dict | None:
        if not self.capture_dir:
            return None
        key = "".join(ch for ch in str(item.get("visual_key") or "") if ch.isalnum() or ch in ("_", "-"))
        if not key:
            return None
        try:
            cx = float(item.get("click_x"))
            cy = float(item.get("click_y"))
        except Exception:
            return None

        out_path = self.capture_dir / f"pending_{key}.jpg"
        raw = page.screenshot(
            full_page=False,
            type="jpeg",
            quality=VISION_JPEG_QUALITY,
        )
        meta = save_privacy_focus_screenshot(
            raw,
            out_path,
            cx,
            cy,
            radius=VISION_FOCUS_RADIUS,
            blur_radius=VISION_BLUR_RADIUS,
            quality=VISION_JPEG_QUALITY,
        )
        return {"path": str(out_path), "created_at": time.time(), **meta}

    def _cleanup_prepared_visuals(self, max_age: float = 20) -> None:
        now = time.time()
        stale = []
        with self._lock:
            for key, shot in list(self._prepared_visuals.items()):
                if max_age <= 0 or now - float(shot.get("created_at") or now) > max_age:
                    stale.append((key, shot))
                    self._prepared_visuals.pop(key, None)
        for _key, shot in stale:
            try:
                path = Path(shot.get("path", ""))
                if path.exists():
                    path.unlink()
            except Exception:
                log.debug("cleanup prepared screenshot failed", exc_info=True)

    def build_review_data(self) -> list[dict]:
        """转成整理页用的数据结构，自动填充 Excel 列名建议。"""
        result = []
        used = set()
        with self._lock:
            recorded_steps = list(self.steps)
        for s in recorded_steps:
            at = s.get("action_type", "click")
            label = s.get("label", "").strip()
            # 输入/上传/选择/菜单项 → 推荐列名
            excel_col = ""
            if at in ("input", "select", "upload", "select_option"):
                if at == "select_option":
                    # 菜单项的默认列名是"菜单项_N"，用户可以改成实际含义（如"省份"）
                    base = f"菜单项_{len([r for r in result if r.get('action_type') == 'select_option']) + 1}"
                elif at == "upload":
                    # 上传步骤明确提示用户填「文件夹路径」
                    # 用户在 Excel 里填一个文件夹路径，runner 会自动上传里面的所有文件
                    if label:
                        base = f"{label}_文件夹"
                    else:
                        upload_idx = len([r for r in result if r.get("action_type") == "upload"]) + 1
                        base = f"文件夹_{upload_idx}"
                else:
                    base = label or f"输入字段_{len(result)+1}"
                col = base
                i = 1
                while col in used:
                    i += 1
                    col = f"{base}_{i}"
                excel_col = col
                used.add(col)
            # 描述：优先用用户录制时的备注（user_note），没填才用自动生成
            user_note = (s.get("user_note") or "").strip()
            desc = user_note if user_note else self._auto_desc(s)
            result.append({
                "_raw": s,
                "selected": True,
                "step_index": s.get("step_index", 0),
                "action_type": at,
                "action_label": s.get("action_label", at),
                "selector": s.get("selector", ""),
                "xpath": s.get("xpath", ""),
                "scoped_selector": s.get("scoped_selector", ""),
                "label": label,
                "value": s.get("value", ""),
                "text": s.get("text", ""),
                "tag": s.get("tag", ""),
                "input_type": s.get("input_type", ""),
                "url": s.get("url", ""),
                "target_box": s.get("target_box"),
                "viewport": s.get("viewport"),
                "click_x": s.get("click_x"),
                "click_y": s.get("click_y"),
                "screenshot_file": s.get("screenshot_file", ""),
                "screenshot_focus": s.get("screenshot_focus"),
                "screenshot_kind": s.get("screenshot_kind", ""),
                "screenshot_match": s.get("screenshot_match"),
                "screenshot_width": s.get("screenshot_width"),
                "screenshot_height": s.get("screenshot_height"),
                "dom_context": s.get("dom_context"),
                "scroll_from": s.get("scroll_from"),
                "scroll_to": s.get("scroll_to"),
                "scroll_delta": s.get("scroll_delta"),
                "scroll_container": s.get("scroll_container"),
                "excel_column": excel_col,
                "description": desc,
            })
        return result

    def _auto_desc(self, s: dict) -> str:
        at = s.get("action_type", "click")
        label = s.get("label", "").strip()
        text = s.get("text", "").strip()
        val = str(s.get("value", "")).strip()

        if at == "scroll":
            delta = s.get("scroll_delta", {})
            dx = delta.get("x", 0)
            dy = delta.get("y", 0)
            container = s.get("scroll_container")
            prefix = f"在「{container.get('class', '容器')[:20]}」内" if container else ""
            if abs(dy) >= abs(dx):
                direction = "向下" if dy > 0 else "向上"
            else:
                direction = "向右" if dx > 0 else "向左"
            return f"{prefix}滚动页面（{direction} {abs(dy) if abs(dy) >= abs(dx) else abs(dx)}px）"
        if at == "input":
            target = label or "输入框"
            return f"在「{target}」输入内容"
        if at == "select":
            target = label or "下拉框"
            return f"在「{target}」选择选项"
        if at == "select_option":
            target = text or label or "选项"
            if len(target) > 16:
                target = target[:16]
            return f"选择菜单项「{target}」"
        if at == "check":
            target = label or text or "复选框"
            return f"勾选「{target}」"
        if at == "upload":
            target = label or "上传框"
            return f"在「{target}」上传文件（Excel 填文件夹路径，自动上传里面所有文件）"
        # click
        target = text or label or "按钮"
        if len(target) > 16:
            target = target[:16]
        return f"点击「{target}」"
