import json
import logging
import os
import threading
import traceback
from pathlib import Path
from typing import Optional

from app.browser import launch_browser_context
from app.dsl import Interpreter, DSLError, wait_for_user_start
from app.excel import read_rows

# 运行时浏览器 profile（跟录制共用，登录态保留）
PROFILE_DIR = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "好办法自动化" / "edge_profile"

log = logging.getLogger(__name__)


class Runner:
    def __init__(self, rules: dict = None):
        self._running = False
        self.rules = rules or {}

    def run(self, dsl_obj: dict, excel_path: Optional[Path] = None,
            init_url: str = "", loop_count: int = 1,
            loop_interval_ms: int = 2000,
            on_log=None, on_done=None, on_error=None,
            flow_dir: Optional[Path] = None,
            browser_mode: str = "normal",
            cdp_profile_dir: Optional[Path] = None):
        """
        loop_count: 不带 Excel 时的循环次数（>=1）
                    -1 表示无限循环（直到用户关闭浏览器）
        loop_interval_ms: 两次循环之间的等待毫秒
        excel_path 优先生效；没有则按 loop_count 跑
        flow_dir: 流程目录（用于保存「人工接管学习样本」）
        browser_mode:
          - "normal": 普通模式，Playwright 自带 Edge
          - "stealth_cdp": 防检测模式，CDP 附加到用户真实 Edge（聚水潭等）
        """
        if self._running:
            if on_error:
                on_error("已经有流程在运行中")
            return
        self._running = True
        threading.Thread(
            target=self._exec,
            args=(dsl_obj, excel_path, init_url, loop_count, loop_interval_ms,
                  on_log, on_done, on_error, flow_dir, browser_mode, cdp_profile_dir),
            daemon=True,
        ).start()

    def _exec(self, dsl_obj, excel_path, init_url, loop_count, loop_interval_ms,
              on_log, on_done, on_error, flow_dir=None, browser_mode="normal",
              cdp_profile_dir=None):
        pw = None
        browser = None
        context = None
        edge_process = None
        log_fn = on_log or (lambda s: None)
        try:
            from playwright.sync_api import sync_playwright
            actions = dsl_obj.get("actions", [])
            if not actions:
                raise ValueError("流程为空")

            # ⭐ DSL 通常不带 label，但 runner 的 _candidates 智能 fallback 需要它
            #    → 从 flow_dir/steps.json 把 label 等元数据合并到 actions
            self._merge_step_metadata(actions, flow_dir)

            pw = sync_playwright().start()

            if browser_mode == "stealth_cdp":
                # ⭐ 防检测模式（聚水潭等）
                log_fn("🛒 启动真实 Edge（防检测模式）...")
                from app.browser import launch_cdp_attached_context
                start_url_pre = init_url or self._first_goto_url(actions) or "about:blank"
                context, browser, edge_process = launch_cdp_attached_context(
                    pw,
                    edge_profile_dir=cdp_profile_dir or PROFILE_DIR,
                    initial_url=start_url_pre,
                    log_fn=log_fn,
                )
            else:
                log_fn("启动浏览器（优先用系统 Edge）...")
                context, browser = launch_browser_context(
                    pw,
                    headless=False,
                    persist_dir=PROFILE_DIR,  # 跟录制共用 profile，登录态保留
                    viewport=None,            # 不锁定视口，页面跟随窗口大小
                    locale="zh-CN",
                    maximized=True,           # 启动时窗口最大化
                )
            pages = context.pages
            page = pages[0] if pages else context.new_page()

            # ⭐ 防检测模式：注入 stealth.js 到 context（所有当前/未来的 page 都用）
            if browser_mode == "stealth_cdp":
                try:
                    from app.paths import resource
                    stealth_path = resource("app", "stealth.js")
                    if stealth_path.exists():
                        stealth_js = stealth_path.read_text(encoding="utf-8")
                        context.add_init_script(script=stealth_js)
                        log_fn("✓ 已注入 stealth.js（防自动化检测）")
                except Exception as e:
                    log_fn(f"⚠ stealth.js 注入失败（{e}），仍尝试继续")

            # 1) 先打开初始 URL（让用户登录、导航）
            start_url = init_url or self._first_goto_url(actions) or "about:blank"

            # ⭐ JST / SPA 子应用场景：录制时步骤所在 URL 可能跟 meta.url 不同
            #    （比如聚水潭：登录后落 epaas 工作台，但商品操作在 src.erp321.com 的子应用）
            #    去 steps.json 读第 1 步的 url，比 meta.url 更准
            if browser_mode == "stealth_cdp" and flow_dir:
                try:
                    import json as _json
                    steps_file = flow_dir / "steps.json"
                    if steps_file.exists():
                        raw_steps = _json.loads(steps_file.read_text(encoding="utf-8"))
                        # ⭐ frameset 场景（聚水潭订单页 = list.aspx 主框架
                        #    + filter.aspx 左侧栏 iframe + OrderEditorNew.aspx 详情弹窗 iframe）：
                        #    各步骤 url 分属不同 frame，绝不能用「第 1 步 url」当起点——
                        #    第 1 步常发生在左侧栏 filter.aspx（视口仅 220px），单独打开它整个页就废了。
                        #    主框架几乎总是视口最宽的那个，所以选 viewport.width 最大的步骤 url。
                        #    （商品等单页场景所有步骤同源，取最宽的同样正确。）
                        best_url, best_w, first_url = "", -1, ""
                        for s in raw_steps:
                            su = (s.get("url") or "").strip()
                            if not su:
                                continue
                            if not first_url:
                                first_url = su
                            try:
                                w = int((s.get("viewport") or {}).get("width") or 0)
                            except Exception:
                                w = 0
                            if w > best_w:
                                best_w, best_url = w, su
                        chosen = best_url or first_url
                        if chosen:
                            cur_base = (start_url or "").split("#")[0].rstrip("/")
                            new_base = chosen.split("#")[0].rstrip("/")
                            if new_base and new_base != cur_base:
                                log_fn(f"📍 起点改用主框架页（视口最宽 {best_w}px）："
                                       f"{chosen[:90]}{'...' if len(chosen) > 90 else ''}")
                                start_url = chosen
                except Exception as e:
                    log_fn(f"⚠ 读 steps.json 找起点 URL 失败：{e}，按 init_url 走")
            if browser_mode == "stealth_cdp":
                # CDP 模式：Edge 启动时已经带 initial_url 跳转了
                # 不管在不在目标，reload 一下让 stealth init_script 应用到当前 page
                try:
                    current = (page.url or "").split("#")[0].rstrip("/")
                    target = (start_url or "").split("#")[0].rstrip("/")
                    if current and current == target:
                        log_fn(f"CDP 模式：reload 让 stealth 生效")
                        page.reload(wait_until="domcontentloaded", timeout=30000)
                    else:
                        log_fn(f"打开 {start_url}")
                        page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    log_fn(f"页面加载警告：{e}（不影响后续操作）")
            else:
                log_fn(f"打开 {start_url}")
                try:
                    page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    log_fn(f"页面加载警告：{e}（不影响后续操作）")

            # 2) 等用户点「开始工作」按钮
            wait_for_user_start(page, on_log=log_fn)

            # 3) 执行 DSL（如果第一个 action 是和 start_url 一样的 goto，跳过避免重复跳转）
            actions_to_run = self._strip_redundant_goto(actions, start_url)

            interp = Interpreter(page, on_log=log_fn,
                                  runner_config=self.rules.get("runner_config"),
                                  learning_dir=flow_dir)

            if excel_path and excel_path.exists():
                # Excel 数据驱动
                total = 0
                for i, row in enumerate(read_rows(excel_path), 1):
                    log_fn(f"━━ 第 {i} 行数据 ━━")
                    interp.execute(actions_to_run, row=row, loop_index=i)
                    total = i
                log_fn(f"✓ 完成，共处理 {total} 行")
            elif loop_count == -1:
                # 无限循环
                i = 0
                while True:
                    i += 1
                    log_fn(f"━━ 第 {i} 次循环（无限模式，关闭浏览器停止）━━")
                    try:
                        interp.execute(actions_to_run, row=None, loop_index=i)
                    except Exception as e:
                        log_fn(f"❌ 第 {i} 次循环失败：{e}（继续下一次）")
                    if loop_interval_ms > 0:
                        try:
                            page.wait_for_timeout(loop_interval_ms)
                        except Exception:
                            break  # 浏览器被关了
            else:
                # 固定次数循环
                n = max(1, loop_count)
                for i in range(1, n + 1):
                    log_fn(f"━━ 第 {i} / {n} 次 ━━")
                    interp.execute(actions_to_run, row=None, loop_index=i)
                    if i < n and loop_interval_ms > 0:
                        page.wait_for_timeout(loop_interval_ms)
                log_fn(f"✓ 完成，共 {n} 次")

            if on_done:
                on_done()
        except DSLError as e:
            log.error(f"DSL 执行错误: {e}")
            if on_error:
                on_error(str(e))
        except Exception as e:
            detail = traceback.format_exc()
            log.error(f"流程出错:\n{detail}")
            if on_error:
                on_error(str(e))
        finally:
            self._running = False
            try:
                if browser_mode == "stealth_cdp":
                    # CDP 模式：只 disconnect，让用户的真实 Edge 继续开着
                    if browser:
                        try: browser.close()  # 在 CDP 模式下等同 disconnect
                        except Exception: pass
                else:
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
            # CDP 模式下 edge_process 是用户的 Edge，不能 terminate
            _ = edge_process

    def _merge_step_metadata(self, actions: list, flow_dir):
        """
        把 flows/{xxx}/steps.json 里的 label / action_type / dom_context 信息
        合并到 dsl.json 的 actions 中（AI 生成 DSL 时通常丢了这些字段）。

        匹配策略（按优先级）：
          1. xpath 精确匹配
          2. selector 精确匹配
          3. excel_column == from_excel 匹配
          4. 按位置（顺序）匹配（兜底）
        """
        if not flow_dir:
            return
        try:
            steps_file = flow_dir / "steps.json"
            if not steps_file.exists():
                return
            import json as _json
            raw_steps = _json.loads(steps_file.read_text(encoding="utf-8"))
        except Exception as e:
            log.debug(f"merge step metadata: load steps.json failed: {e}")
            return

        valid_steps = [s for s in raw_steps if s.get("selected", True)]
        # 索引
        by_xpath = {}
        by_selector = {}
        by_excel_col = {}
        for s in valid_steps:
            xp = s.get("xpath") or ""
            if xp:
                by_xpath.setdefault(xp, s)
            sel = s.get("selector") or ""
            if sel:
                by_selector.setdefault(sel, s)
            col = (s.get("excel_column") or "").strip()
            if col:
                by_excel_col[col] = s

        # 走一遍 actions 找匹配
        used_step_ids = set()
        unmatched_actions = []  # 用于 position fallback
        for idx, action in enumerate(actions):
            # 跳过非操作类（runner 内部 action）
            if action.get("type") in ("goto", "delay", "press", "scroll"):
                continue

            matched = None
            # 1. xpath
            xp = (action.get("xpath") or "").strip()
            if xp and xp in by_xpath:
                matched = by_xpath[xp]
            # 2. selector
            if not matched:
                sel = (action.get("selector") or "").strip()
                if sel and sel in by_selector:
                    matched = by_selector[sel]
            # 3. from_excel
            if not matched:
                col = (action.get("from_excel") or "").strip()
                if col and col in by_excel_col:
                    matched = by_excel_col[col]

            if matched:
                step_id = id(matched)
                if step_id not in used_step_ids:
                    used_step_ids.add(step_id)
                    for k in ("label", "action_type", "dom_context", "input_type", "tag"):
                        if matched.get(k) and not action.get(k):
                            action[k] = matched[k]
            else:
                unmatched_actions.append((idx, action))

        # 4. 位置 fallback：把还没匹配的 actions 按顺序对到还没用的 steps
        if unmatched_actions:
            unused_steps = [s for s in valid_steps if id(s) not in used_step_ids]
            for (a_idx, action), step in zip(unmatched_actions, unused_steps):
                for k in ("label", "action_type", "dom_context", "input_type", "tag"):
                    if step.get(k) and not action.get(k):
                        action[k] = step[k]

    def _first_goto_url(self, actions: list) -> str:
        for a in actions:
            if a.get("type") == "goto":
                return a.get("url", "")
        return ""

    def _strip_redundant_goto(self, actions: list, current_url: str) -> list:
        """如果第一个 action 是 goto 且 URL 和当前一致（含 hash），就跳过"""
        if not actions:
            return actions
        first = actions[0]
        if first.get("type") == "goto":
            target = first.get("url", "").rstrip("/")
            cur = (current_url or "").rstrip("/")
            if target == cur:
                return actions[1:]
        return actions

    def stop(self):
        self._running = False


def load_dsl(filepath: Path) -> dict:
    return json.loads(filepath.read_text(encoding="utf-8"))
