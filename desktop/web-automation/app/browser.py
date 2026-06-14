"""
浏览器启动统一入口
==================

策略（按优先级）：
  1. 系统 Edge（msedge）—— Win10/11 自带，100% 可用，免下载
  2. 系统 Chrome —— 多数用户有装
  3. 内置 Chromium —— 最后兜底（需要先下载，正常不会走到这）

设计哲学：
  - 让"别的电脑"开箱即用，不联网也能跑
  - 用 launch_persistent_context 保留用户登录态（cookies），下次启动还在登录
  - 用户profile 目录隔离：每个 Windows 账号一个独立 profile
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)


def edge_installed_path() -> Optional[Path]:
    """返回系统 Edge 的可执行文件路径，没装返回 None。
    免去等 Playwright launch 才能知道"有没有 Edge"。
    """
    candidates = [
        # 64-bit Windows，最常见位置
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        # 用户级安装
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    return None


def chrome_installed_path() -> Optional[Path]:
    """Google Chrome 检测"""
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    return None


def detect_browser() -> tuple[str, Optional[Path]]:
    """
    返回 (channel, exe_path)
    channel: "msedge" / "chrome" / "chromium"（最后兜底，需要 Playwright 装过）
    exe_path: 系统浏览器路径（chromium 时是 None）
    """
    edge = edge_installed_path()
    if edge:
        return ("msedge", edge)
    chrome = chrome_installed_path()
    if chrome:
        return ("chrome", chrome)
    return ("chromium", None)


def launch_browser_context(
    pw,
    headless: bool = False,
    persist_dir: Optional[Path] = None,
    viewport: Optional[dict] = None,
    locale: str = "zh-CN",
    maximized: bool = True,
):
    """
    统一的浏览器启动入口。

    Args:
        pw: sync_playwright().start() 返回的实例
        headless: 是否无头模式
        persist_dir: 持久化 profile 目录（保留 cookies 登录态）；None 则用临时
        viewport: 视口大小。传 None（默认）= 不锁定视口，页面跟随窗口大小（推荐）
                  传 dict {width,height} = 强制锁定到该尺寸（适合截图比对一致性场景）
        locale: 区域
        maximized: 是否启动时最大化窗口（默认 True）

    Returns:
        (context, browser_or_none)
        - context: 浏览器上下文，可以 .new_page()
        - browser_or_none: 非持久模式返回 browser，持久模式返回 None
    """
    # 视口策略：None = 让页面跟随窗口（解决"最大化后留白"问题）
    use_no_viewport = viewport is None

    channel, exe_path = detect_browser()
    log.info(f"浏览器检测: channel={channel}, path={exe_path}, no_viewport={use_no_viewport}, maximized={maximized}")

    # 浏览器启动参数
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=Translate",
    ]
    if maximized:
        launch_args.append("--start-maximized")

    # ── 持久化 context（保留 cookies / 登录态）──
    if persist_dir is not None:
        try:
            persist_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        kwargs = dict(
            user_data_dir=str(persist_dir),
            headless=headless,
            locale=locale,
            args=launch_args,
        )
        # 视口策略：either no_viewport（跟随窗口）or 固定 viewport
        if use_no_viewport:
            kwargs["no_viewport"] = True
        else:
            kwargs["viewport"] = viewport

        # 优先 msedge，失败 chrome，再不行用内置 chromium
        for ch in (channel, "msedge", "chrome"):
            if ch == "chromium":
                continue
            try:
                kwargs_try = dict(kwargs)
                kwargs_try["channel"] = ch
                return pw.chromium.launch_persistent_context(**kwargs_try), None
            except Exception as e:
                log.info(f"persistent {ch} 失败: {type(e).__name__}: {str(e)[:120]}")
        # 内置 chromium 兜底（不带 channel）
        return pw.chromium.launch_persistent_context(**kwargs), None

    # ── 非持久化 context（每次干净启动）──
    ctx_kwargs = dict(locale=locale)
    if use_no_viewport:
        ctx_kwargs["no_viewport"] = True
    else:
        ctx_kwargs["viewport"] = viewport

    for ch in (channel, "msedge", "chrome"):
        if ch == "chromium":
            continue
        try:
            br = pw.chromium.launch(channel=ch, headless=headless, args=launch_args)
            ctx = br.new_context(**ctx_kwargs)
            return ctx, br
        except Exception as e:
            log.info(f"launch {ch} 失败: {type(e).__name__}: {str(e)[:120]}")

    # 内置 chromium 兜底
    br = pw.chromium.launch(headless=headless, args=launch_args)
    ctx = br.new_context(**ctx_kwargs)
    return ctx, br


# ════════════════════════════════════════════════════════════════════
#  CDP 附加模式 — 用于聚水潭等防自动化检测网站
# ════════════════════════════════════════════════════════════════════
#
#  与普通模式区别：
#    - 普通模式：Playwright 直接 launch 浏览器，会带 --enable-automation 等参数，
#                 navigator.webdriver === true，能被聚水潭等网站识别
#    - CDP 模式：我们用 subprocess 启动用户真实的 Edge（带调试端口），
#                 然后用 Playwright connect_over_cdp 附加。
#                 这种方式不留 Playwright 控制痕迹，配合 stealth.js 几乎和真人无异。
#
#  使用 dedicated profile：
#    避免占用用户主 Edge profile（用户的 Edge 还能正常用）
#    路径：~/Documents/好办法自动化/edge_jst_profile
# ════════════════════════════════════════════════════════════════════

def _pick_free_port(default_port: int = 9222) -> int:
    """优先用 default_port，被占了就找一个空闲端口"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", default_port)) != 0:
                return default_port
    except Exception:
        return default_port
    # default_port 被占了 → 让系统挑一个空闲的
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_cdp_ready(port: int, timeout: int = 25) -> bool:
    """等 Edge 启动好调试端口（先 socket 通了，再确认 /json/version 接口能拿到）"""
    import requests
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    # 端口通了，再请求 /json/version 看 CDP 是不是真的起来了
                    try:
                        r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
                        if r.status_code == 200:
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(0.4)
    return False


def launch_cdp_attached_context(
    pw,
    edge_profile_dir: Path,
    initial_url: str = "about:blank",
    debug_port: int = 9222,
    log_fn=None,
) -> Tuple[object, object, Optional[subprocess.Popen]]:
    """
    用调试模式启动用户的真实 Edge，然后 Playwright 通过 CDP 附加。

    Args:
        pw: sync_playwright().start()
        edge_profile_dir: 这个浏览器实例独立使用的 user-data-dir
                          （建议跟用户日常 Edge 不一样，避免冲突）
        initial_url: 启动后第一个标签页打开的网址
        debug_port: CDP 调试端口（默认 9222，被占用时自动找空闲端口）
        log_fn: 日志回调

    Returns:
        (context, browser, edge_process)
        - context: BrowserContext，可以 .new_page()
        - browser: Browser（CDP attach 模式下的 browser 对象）
        - edge_process: subprocess.Popen 对象（保留引用以便后续 terminate）
    """
    def _log(msg):
        log.info(msg)
        if log_fn:
            try: log_fn(msg)
            except Exception: pass

    edge = edge_installed_path()
    if not edge:
        raise RuntimeError(
            "找不到系统 Edge。聚水潭专区需要使用 Edge 真实浏览器才能绕过反爬。\n"
            "请确认 Windows 10/11 自带的 Microsoft Edge 没被卸载。"
        )

    # 准备 profile 目录
    try:
        edge_profile_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"无法创建 Edge profile 目录 {edge_profile_dir}: {e}")

    # 找一个可用的调试端口
    port = _pick_free_port(debug_port)
    _log(f"📡 调试端口：{port}")

    # ⭐ 关键：用真实 Edge 启动，不带 Playwright 的自动化参数
    # 注意：不要加 --disable-blink-features=AutomationControlled 这种东西
    #       那是 Playwright 启动 chromium 时为了"消除" automation 痕迹用的，
    #       而真实 Edge 启动**根本就没有**这些痕迹，加了反而暴露
    edge_args = [
        str(edge),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={str(edge_profile_dir)}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--start-maximized",
        initial_url,
    ]

    _log(f"🚀 启动真实 Edge：{edge}")
    _log(f"📁 profile：{edge_profile_dir}")

    try:
        edge_process = subprocess.Popen(
            edge_args,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise RuntimeError(f"启动 Edge 失败：{e}")

    # 等 Edge 把调试端口起起来
    _log("⏳ 等待 Edge 调试端口就绪...")
    if not _wait_for_cdp_ready(port, timeout=25):
        try: edge_process.terminate()
        except Exception: pass
        raise RuntimeError(
            f"Edge 启动超时（25 秒内未响应调试端口 {port}）\n"
            f"可能原因：\n"
            f"  1. 这个 profile 目录被另一个 Edge 进程占用\n"
            f"  2. 杀毒软件拦截了 Edge 启动\n"
            f"  3. 系统 Edge 版本太老（建议更新到最新版）"
        )
    _log(f"✓ Edge 调试端口已就绪 http://127.0.0.1:{port}")

    # Playwright CDP 附加
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    except Exception as e:
        try: edge_process.terminate()
        except Exception: pass
        raise RuntimeError(f"Playwright 附加到 Edge 失败：{e}")

    # 用第 1 个 context 即可（持久 profile 模式下 default context 已经存在）
    contexts = browser.contexts
    context = contexts[0] if contexts else browser.new_context()
    _log(f"✓ 已通过 CDP 附加到 Edge，context 数 = {len(browser.contexts)}")

    return context, browser, edge_process

