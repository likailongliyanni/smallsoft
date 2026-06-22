# -*- coding: utf-8 -*-
"""Electron 界面的 Python 后端桥。

Electron 把每条命令以「一行 JSON」从 stdin 发来，本脚本调用原版
snap_saver.py 里成熟的函数干活，再把结果以「一行 JSON」从 stdout 返回。
这样界面层（Electron/JS）和功能层（Python）解耦，原版逻辑全部复用。

协议（每行一个 JSON 对象）：
  收：{"id": 1, "cmd": "get_serial", "args": {...}}
  回：{"id": 1, "ok": true, "data": {...}}  或  {"id": 1, "ok": false, "error": "..."}
"""
import json
import sys
import io
from pathlib import Path

# Electron 的管道统一使用 UTF-8。stdin 也必须重设；否则 Windows 中文路径会
# 被 Python 按系统 GBK 解码，导致「存图结果」变成「瀛樺浘缁撴灉」，并让 Path.exists 失败。
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", newline="")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", newline="")

# 复用原版 snap_saver.py 的全部逻辑
sys.path.insert(0, str(Path(__file__).resolve().parent))
import snap_saver as S

# 关键：让本进程 DPI 感知，使全局鼠标钩子坐标与 ImageGrab 用同一套物理坐标。
# 不设的话高分屏（125%/150% 缩放）下截图坐标错位 → 截到空白/越界 → 看似"没保存"。
try:
    S.enable_dpi_awareness()
except Exception:
    pass

# 持有一个登记后的 token（同步额度等需要）
_STATE = {"token": "", "server_url": S.DEFAULT_SERVER_URL}


def _server_url() -> str:
    return _STATE.get("server_url") or S.DEFAULT_SERVER_URL


def _configured_output_dir(value=None, create=True) -> Path:
    """返回 Electron 与原版共用的输出根目录。"""
    raw = str(value or "").strip()
    if not raw:
        raw = str((S.load_config() or {}).get("output_dir") or "").strip()
    # Electron 版默认放到用户文档，避免打包后结果藏在 exe/项目目录深处。
    path = Path(raw).expanduser() if raw else Path.home() / "Documents" / "存图结果"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def cmd_get_settings(args):
    output_dir = _configured_output_dir()
    config = S.load_config() or {}
    return {
        "output_dir": str(output_dir),
        "free_dir": str(output_dir / "自由截图"),
        "repair_dir": str(output_dir / "AI修复"),
        "doc_dir": str(output_dir / "文档"),
        "keep_original": bool(config.get("keep_original", False)),
    }


def cmd_set_output_dir(args):
    raw = str(args.get("path") or "").strip()
    if not raw:
        raise RuntimeError("请选择输出目录。")
    output_dir = _configured_output_dir(raw)
    S.save_config({"output_dir": str(output_dir)})
    _WORKER.out_dir = output_dir
    return {"output_dir": str(output_dir)}


def cmd_set_keep_original(args):
    keep = bool(args.get("keep_original", False))
    S.save_config({"keep_original": keep})
    return {"keep_original": keep}


def _pretty_serial(raw: str) -> str:
    """把编号格式化成界面显示用：12 位 MAC → XX-XX-XX-XX-XX-XX，去掉 -pic 等后缀。"""
    hexs = "".join(c for c in str(raw or "") if c.isalnum()).upper()
    # 去掉末尾可能的软件代码后缀（pic/auto）——只保留前 12 位 MAC
    if len(hexs) >= 12:
        hexs = hexs[:12]
    if len(hexs) == 12:
        return "-".join(hexs[i:i + 2] for i in range(0, 12, 2))
    return str(raw or "")


def cmd_get_serial(args):
    """返回本机软件编号（MAC，带横线，界面显示用）。"""
    return {"serial": _pretty_serial(S.local_software_id())}


def cmd_register(args):
    """登记设备，拿 token + 额度。界面启动时调一次。"""
    serial = S.local_software_id()
    data = S.server_register_device(_server_url(), serial)
    _STATE["token"] = str(data.get("token") or "")
    quota = data.get("quota") or {}
    return {
        "serial": _pretty_serial(data.get("software_id") or serial),
        "quota": {
            "free": int(quota.get("free") or 0),
            "paid": int(quota.get("paid") or 0),
            "available": int(quota.get("available") or 0),
        },
    }


def cmd_sync_quota(args):
    """同步额度（没 token 先登记一次）。"""
    if not _STATE["token"]:
        return cmd_register(args)
    data = S.server_device_status(_server_url(), _STATE["token"])
    quota = data.get("quota") or {}
    return {
        "quota": {
            "free": int(quota.get("free") or 0),
            "paid": int(quota.get("paid") or 0),
            "available": int(quota.get("available") or 0),
        },
    }


def cmd_ping(args):
    """连通性测试。"""
    return {"pong": True, "version": S.APP_VERSION}


def cmd_list_shots(args):
    """列出「自由截图」目录里的图片，给整理文档用。
    args.dir 可指定截图目录；默认用户文档下的「存图结果/自由截图」。"""
    folder = args.get("dir")
    if folder:
        folder = Path(folder)
    else:
        # 与原版一致：输出目录/自由截图
        out = _configured_output_dir(args.get("out_dir")) / "自由截图"
        folder = out
    shots = []
    if folder.exists():
        for p in sorted(folder.glob("*.jpg")):
            try:
                with S.Image.open(p) as im:
                    w, h = im.size
            except Exception:
                w, h = 0, 0
            shots.append({"path": str(p.resolve()), "name": p.name, "w": w, "h": h})
    return {"shots": shots, "dir": str(folder.resolve())}


def cmd_describe_image(args):
    """对一张图调 AI 生成说明。args: {path, hint, style}"""
    if not _STATE["token"]:
        S.server_register_device(_server_url(), S.local_software_id())  # 兜底先登记
        # 重新登记拿 token
        data = S.server_register_device(_server_url(), S.local_software_id())
        _STATE["token"] = str(data.get("token") or "")
    path = Path(args.get("path") or "")
    hint = str(args.get("hint") or "")
    style = str(args.get("style") or "detail")
    res = S.server_describe_image(_server_url(), _STATE["token"], path, hint=hint, style=style)
    return {"description": res.get("description", ""), "charged": bool(res.get("charged"))}


def cmd_generate_product_params(args):
    """把一句商品介绍交给服务器 AI，拆成可编辑的参数表。"""
    text = str(args.get("text") or "").strip()
    if not text:
        raise RuntimeError("请先输入一句商品介绍。")
    if not _STATE["token"]:
        data = S.server_register_device(_server_url(), S.local_software_id())
        _STATE["token"] = str(data.get("token") or "")
    return S.server_generate_product_params(_server_url(), _STATE["token"], text)


def cmd_export_doc(args):
    """导出整理文档。args: {title, intro, items:[{path,caption,size}], format:'pdf'|'long', watermark}"""
    title = str(args.get("title") or "使用说明")
    intro = str(args.get("intro") or "")
    fmt = str(args.get("format") or "pdf")
    watermark = bool(args.get("watermark", True))
    style = args.get("style") or {}
    raw_items = args.get("items") or []

    loaded = []
    for it in raw_items:
        p = Path(it.get("path") or "")
        if not p.exists():
            continue
        try:
            with S.Image.open(p) as im:
                img = im.convert("RGB")
                img.load()
            loaded.append((
                img,
                str(it.get("caption") or ""),
                str(it.get("size") or "full"),
                str(it.get("layout") or "auto"),
                str(it.get("align") or "inherit"),
            ))
        except Exception:
            continue
    if not loaded:
        raise RuntimeError("没有可导出的图片。")

    out_dir = _configured_output_dir(args.get("out_dir")) / "文档"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = S.safe_folder_name(title, "使用说明")
    stamp = S.time.strftime("%Y%m%d-%H%M%S")

    if fmt == "long":
        out = out_dir / f"{name}_{stamp}.jpg"
        image = S.build_long_image(title, intro, loaded, watermark=watermark, style=style)
        image.save(out, "JPEG", quality=92)
    else:
        out = out_dir / f"{name}_{stamp}.pdf"
        S.build_doc_pdf(out, title, intro, loaded, watermark=watermark, style=style)
    return {"path": str(out), "dir": str(out_dir)}


def cmd_stitch_long_image(args):
    """把 Electron 按视口截出的编辑器切片拼成长图。"""
    paths = [Path(p) for p in (args.get("paths") or [])]
    images = []
    for path in paths:
        if not path.exists():
            continue
        try:
            with S.Image.open(path) as source:
                image = source.convert("RGB")
                image.load()
            images.append(image)
        except Exception:
            continue
    if not images:
        raise RuntimeError("没有可拼接的文档画面。")
    width = max(image.width for image in images)
    height = sum(image.height for image in images)
    canvas = S.Image.new("RGB", (width, height), "white")
    y = 0
    for image in images:
        canvas.paste(image, ((width - image.width) // 2, y))
        y += image.height
    out_dir = _configured_output_dir(args.get("out_dir")) / "文档"
    out_dir.mkdir(parents=True, exist_ok=True)
    title = S.safe_folder_name(str(args.get("title") or "使用说明"), "使用说明")
    stamp = S.time.strftime("%Y%m%d-%H%M%S")
    # 长图使用 PNG 无损保存，避免文字边缘和商品图二次 JPEG 压缩后出现颗粒。
    out = out_dir / f"{title}_{stamp}.png"
    canvas.save(out, "PNG", optimize=True)
    return {"path": str(out), "dir": str(out_dir), "width": width, "height": height}


def cmd_open_path(args):
    """在资源管理器里打开一个文件/目录。"""
    target = Path(args.get("path") or "")
    if args.get("create"):
        target.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        raise RuntimeError("目录或文件不存在。")
    try:
        S.os.startfile(str(target))
    except Exception as exc:
        raise RuntimeError(f"无法打开：{exc}") from exc
    return {"ok": True}


# ───────────────────────── 电商批量采集（Ctrl 拖框截图）─────────────────────────
class CaptureWorker:
    """复用原版 CtrlDragHook：在网页上按 Ctrl 拖框截图，按主图/详情自动归类、自动翻页。
    钩子事件来了直接截图存盘，并通过 _push_event 主动告诉 Electron 界面更新进度。"""

    def __init__(self):
        self.hook = None
        self.active = False
        self.free_mode = False   # 自由截图模式：不归类、不翻页，直接存自由截图目录
        self.rows = []           # [{name, link}]
        self.index = 0
        self.main_count = 1
        self.detail_count = 3
        self.category = "主图"
        self.counts = {}         # index -> [main_done, detail_done]
        self.gesture_start = None
        self._poll_thread = None
        self.out_dir = _configured_output_dir()
        self.frozen_image = None
        self.frozen_origin = (0, 0)
        self.link_switch_delay = 2.5
        self.link_transition = 0
        self.link_timer = None
        self.hover_bbox = None
        self.hover_title = ""
        self.last_move_emit = 0.0
        self.last_hover_emit = 0.0
        self.visual_regions = []
        self.visual_region_key = None
        self.visual_region_time = 0.0

    def start_free(self, out_dir=None):
        """自由截图：装钩子，Ctrl 拖框随手截，存到「自由截图」目录。"""
        if self.active:
            raise RuntimeError("请先结束当前截图任务。")
        self.out_dir = _configured_output_dir(out_dir)
        self.free_mode = True
        self.hover_bbox = None
        self.hover_title = ""
        self.last_move_emit = 0.0
        self.last_hover_emit = 0.0
        self.visual_regions = []
        self.visual_region_key = None
        self.visual_region_time = 0.0
        self.hook = S.CtrlDragHook()
        ok = self.hook.install()
        if not ok:
            self.free_mode = False
            raise RuntimeError(self.hook.last_error or "截图钩子启用失败，可能被安全软件拦截。")
        self.active = True
        self._poll_thread = _threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        return {"ok": True}

    def _save_free(self, sx, sy, ex, ey):
        left, top = min(sx, ex), min(sy, ey)
        right, bottom = max(sx, ex), max(sy, ey)
        if right - left < 5 or bottom - top < 5:
            self.frozen_image = None
            return
        self.hook.enabled = False
        try:
            img = self._grab_selection(left, top, right, bottom)
        finally:
            self.hook.enabled = True
        if img.mode != "RGB":
            img = img.convert("RGB")
        out_dir = self.out_dir / "自由截图"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = S.time.strftime("%Y%m%d-%H%M%S")
        target = out_dir / f"截图_{stamp}.jpg"
        idx = 2
        while target.exists():
            target = out_dir / f"截图_{stamp}-{idx}.jpg"; idx += 1
        img.save(target, "JPEG", quality=95)
        _push_event("capture_saved", path=str(target), name=target.name,
                    w=img.width, h=img.height, row_name="自由截图", category="")

    def counts_for(self, i):
        return self.counts.setdefault(i, [0, 0])

    def start(self, rows, main_count, detail_count, out_dir=None):
        if self.active:
            raise RuntimeError("请先结束当前截图任务。")
        if not rows:
            raise RuntimeError("请先导入名称+链接列表。")
        self.rows = rows
        self.index = 0
        self.main_count = int(main_count)
        self.detail_count = int(detail_count)
        self.category = "主图"
        self.counts = {}
        self.out_dir = _configured_output_dir(out_dir)

        self.hook = S.CtrlDragHook()
        ok = self.hook.install()
        if not ok:
            raise RuntimeError(self.hook.last_error or "截图钩子启用失败，可能被安全软件拦截。")
        self.active = True
        self._poll_thread = _threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        # 打开第一个商品链接
        self._push_progress()
        self._open_link_with_pause()
        return {"ok": True}

    def stop(self):
        self.active = False
        self.free_mode = False
        self.gesture_start = None
        self.hover_bbox = None
        self.hover_title = ""
        self.link_transition += 1
        if self.link_timer:
            try:
                self.link_timer.cancel()
            except Exception:
                pass
            self.link_timer = None
        _push_event("capture_drag_end")
        _push_event("capture_window_hover_end")
        if self.hook:
            try:
                self.hook.uninstall()
            except Exception:
                pass
        self.hook = None
        self.frozen_image = None
        return {"ok": True}

    def _freeze_screen(self):
        """在选框出现前冻结虚拟桌面，避免绿色选框被截进结果图。"""
        from PIL import ImageGrab
        self.frozen_image = ImageGrab.grab(all_screens=True)
        try:
            import ctypes
            self.frozen_origin = (
                int(ctypes.windll.user32.GetSystemMetrics(76)),  # SM_XVIRTUALSCREEN
                int(ctypes.windll.user32.GetSystemMetrics(77)),  # SM_YVIRTUALSCREEN
            )
        except Exception:
            self.frozen_origin = (0, 0)

    def _grab_selection(self, left, top, right, bottom):
        frozen = self.frozen_image
        self.frozen_image = None
        if frozen is not None:
            ox, oy = self.frozen_origin
            crop = (int(left - ox), int(top - oy), int(right - ox), int(bottom - oy))
            if crop[0] >= 0 and crop[1] >= 0 and crop[2] <= frozen.width and crop[3] <= frozen.height:
                return frozen.crop(crop)
        from PIL import ImageGrab
        # 先让 Electron 透明选框完成隐藏，再抓当前屏幕；避免绿框进入结果图。
        import time
        time.sleep(0.07)
        return ImageGrab.grab(
            bbox=(int(left), int(top), int(right), int(bottom)), all_screens=True)

    def _window_at(self, x, y):
        """返回鼠标下有意义的子窗口/对话框边界，用于自由截图智能吸附。"""
        try:
            import ctypes
            from ctypes import wintypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            class RECT(ctypes.Structure):
                _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                            ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

            user32 = ctypes.windll.user32
            user32.WindowFromPoint.argtypes = [POINT]
            user32.WindowFromPoint.restype = wintypes.HWND
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetDesktopWindow.restype = wintypes.HWND
            hwnd = user32.WindowFromPoint(POINT(int(x), int(y)))
            if not hwnd:
                return None
            root = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
            if not user32.IsWindowVisible(root) or root == user32.GetDesktopWindow():
                return None

            def window_rect(target, use_dwm=False):
                rect = RECT()
                got = False
                if use_dwm:
                    try:
                        dwmapi = ctypes.windll.dwmapi
                        dwmapi.DwmGetWindowAttribute.argtypes = [
                            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
                        got = dwmapi.DwmGetWindowAttribute(
                            target, 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0
                    except Exception:
                        got = False
                if not got:
                    got = bool(user32.GetWindowRect(target, ctypes.byref(rect)))
                return rect if got else None

            root_rect = window_rect(root, use_dwm=True)
            if not root_rect:
                return None
            root_area = max(1, (root_rect.right - root_rect.left) * (root_rect.bottom - root_rect.top))
            # WindowFromPoint 通常落在按钮/输入框等过细控件上。逐层向父级寻找
            # 第一个足够大的区域，得到对话框、内容面板或渲染区，而不是整套程序。
            control_classes = {
                "button", "edit", "static", "combobox", "comboboxex32", "scrollbar",
                "msctls_statusbar32", "msctls_progress32", "toolbarwindow32",
            }
            selected = root
            selected_rect = root_rect
            selected_class = ""
            current = hwnd
            for _ in range(16):
                if not current:
                    break
                rect = window_rect(current, use_dwm=current == root)
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(current, class_buf, 256)
                cls = class_buf.value.lower()
                if rect and user32.IsWindowVisible(current):
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    area = width * height
                    inside = rect.left <= x < rect.right and rect.top <= y < rect.bottom
                    meaningful = (width >= 160 and height >= 90 and inside and
                                  cls not in control_classes and area >= min(32000, root_area * 0.025))
                    if meaningful:
                        selected, selected_rect, selected_class = current, rect, cls
                        break
                if current == root:
                    break
                current = user32.GetParent(current)

            rect = selected_rect
            selected_area = max(1, (rect.right - rect.left) * (rect.bottom - rect.top))
            visual = None
            # Electron/浏览器的 HTML 对话框没有独立 HWND。对子窗口仍接近整窗的情况，
            # 再用矩形边缘识别寻找鼠标下的弹窗或内容面板。
            if selected_area >= root_area * 0.62 or "chrome_render" in selected_class:
                visual = self._visual_region_at(
                    (root_rect.left, root_rect.top, root_rect.right, root_rect.bottom), x, y)
                if visual:
                    rect = RECT(*visual)
                    selected = root
            if rect.right - rect.left < 20 or rect.bottom - rect.top < 20:
                return None
            length = user32.GetWindowTextLengthW(selected)
            title = ""
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(selected, buf, length + 1)
                title = buf.value.strip()
            if not title and selected != root:
                length = user32.GetWindowTextLengthW(root)
                if length:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(root, buf, length + 1)
                    title = (buf.value.strip() + " · 内容区域").strip(" ·")
            elif visual:
                title = (title or "当前窗口") + " · 智能区域"
            return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom), title)
        except Exception:
            return None

    def _visual_region_at(self, root_bbox, x, y):
        """用窗口画面边缘寻找 HTML 弹窗/面板；依赖不可用时静默退回 HWND。"""
        try:
            import time
            now = time.monotonic()
            key = tuple(int(v) for v in root_bbox)
            if key != self.visual_region_key or now - self.visual_region_time > 0.45:
                import cv2
                import numpy as np
                from PIL import ImageGrab
                left, top, right, bottom = key
                shot = ImageGrab.grab(bbox=key, all_screens=True).convert("RGB")
                arr = np.asarray(shot)
                height, width = arr.shape[:2]
                factor = min(1.0, 1500.0 / max(width, height))
                if factor < 1:
                    arr = cv2.resize(arr, (round(width * factor), round(height * factor)),
                                     interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray, 55, 150)
                edges = cv2.morphologyEx(
                    edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
                contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
                ih, iw = gray.shape[:2]
                total = iw * ih
                regions = []
                for contour in contours:
                    rx, ry, rw, rh = cv2.boundingRect(contour)
                    area = rw * rh
                    if rw < 160 * factor or rh < 90 * factor:
                        continue
                    if area < total * 0.025 or area > total * 0.90:
                        continue
                    contour_area = abs(cv2.contourArea(contour))
                    if contour_area / max(1, area) < 0.38:
                        continue
                    regions.append((
                        left + round(rx / factor), top + round(ry / factor),
                        left + round((rx + rw) / factor), top + round((ry + rh) / factor)))
                # 去重并优先更小、更具体的区域。
                unique = []
                for region in sorted(regions, key=lambda r: (r[2] - r[0]) * (r[3] - r[1])):
                    if not any(sum(abs(a - b) for a, b in zip(region, old)) < 24 for old in unique):
                        unique.append(region)
                self.visual_regions = unique[:80]
                self.visual_region_key = key
                self.visual_region_time = now
            for region in self.visual_regions:
                if region[0] <= x < region[2] and region[1] <= y < region[3]:
                    return region
        except Exception:
            return None
        return None

    def _open_link(self):
        if 0 <= self.index < len(self.rows):
            link = (self.rows[self.index].get("link") or "").strip()
            if link:
                try:
                    S.webbrowser.open(link)
                    return True
                except Exception:
                    pass
        return False

    def _open_link_with_pause(self):
        """切换商品时短暂关闭截图，避免用户在旧页面继续截满下一商品的数量。"""
        self.link_transition += 1
        transition = self.link_transition
        row = self.rows[self.index] if 0 <= self.index < len(self.rows) else {}
        if self.hook:
            self.hook.enabled = False
        _push_event(
            "capture_link_wait",
            index=self.index,
            total=len(self.rows),
            row_name=row.get("name", ""),
            delay=self.link_switch_delay,
        )
        opened = self._open_link()
        delay = self.link_switch_delay if opened else 0.3
        self.link_timer = _threading.Timer(delay, self._finish_link_switch, args=(transition,))
        self.link_timer.daemon = True
        self.link_timer.start()

    def _finish_link_switch(self, transition):
        if not self.active or transition != self.link_transition:
            return
        if self.hook:
            self.hook.enabled = True
        row = self.rows[self.index] if 0 <= self.index < len(self.rows) else {}
        _push_event(
            "capture_link_ready",
            index=self.index,
            total=len(self.rows),
            row_name=row.get("name", ""),
        )

    def _poll_loop(self):
        import queue as _q
        import time as _t
        while self.active and self.hook:
            try:
                kind, x, y = self.hook.events.get(timeout=0.2)
            except _q.Empty:
                continue
            except Exception:
                break
            try:
                if kind == "start":
                    self.gesture_start = (x, y)
                    # 悬停时已经锁定底层窗口；不要在覆盖层出现后重新识别成覆盖层自身。
                    if self.free_mode and not self.hover_bbox:
                        found = self._window_at(x, y)
                        if found:
                            self.hover_bbox = found[:4]
                            self.hover_title = found[4]
                    _push_event("capture_drag_start", x=x, y=y)
                elif kind == "move":
                    if self.gesture_start:
                        # 全局鼠标事件可能超过 200Hz；限制到约 60fps，避免 JSON 管道积压造成拖框滞后。
                        now = _t.monotonic()
                        if now - self.last_move_emit >= 1 / 60:
                            self.last_move_emit = now
                            _push_event("capture_drag_move", x=x, y=y)
                elif kind == "hover" and self.free_mode:
                    now = _t.monotonic()
                    if now - self.last_hover_emit >= 1 / 30:
                        self.last_hover_emit = now
                        found = self._window_at(x, y)
                        if found and (found[:4] != self.hover_bbox or found[4] != self.hover_title):
                            self.hover_bbox = found[:4]
                            self.hover_title = found[4]
                            _push_event("capture_window_hover", bbox=list(found[:4]), title=found[4])
                elif kind == "hover_end" and self.free_mode:
                    self.hover_bbox = None
                    self.hover_title = ""
                    _push_event("capture_window_hover_end")
                elif kind == "finish":
                    if self.gesture_start:
                        sx, sy = self.gesture_start
                        self.gesture_start = None
                        _push_event("capture_drag_end")
                        if self.free_mode:
                            if abs(x - sx) < 5 and abs(y - sy) < 5:
                                found = self.hover_bbox or ((self._window_at(x, y) or ())[:4])
                                if found:
                                    self._save_free(*found)
                            else:
                                self._save_free(sx, sy, x, y)
                            self.hover_bbox = None
                            self.hover_title = ""
                            self.visual_regions = []
                            self.visual_region_key = None
                        else:
                            self._do_capture(sx, sy, x, y)
            except Exception as e:
                _push_event("capture_error", error=str(e))

    def _do_capture(self, sx, sy, ex, ey):
        left, top = min(sx, ex), min(sy, ey)
        right, bottom = max(sx, ex), max(sy, ey)
        if right - left < 5 or bottom - top < 5:
            self.frozen_image = None
            return
        self.hook.enabled = False
        try:
            img = self._grab_selection(left, top, right, bottom)
        finally:
            self.hook.enabled = True
        if img.mode != "RGB":
            img = img.convert("RGB")

        row = self.rows[self.index]
        name = S.safe_folder_name(row.get("name") or f"第{self.index+1}行", f"第{self.index+1}行")
        cat = self.category
        done = self.counts_for(self.index)[0 if cat == "主图" else 1]
        target = self.out_dir / name / cat / f"pic{done + 1}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target, "JPEG", quality=95)
        self.counts_for(self.index)[0 if cat == "主图" else 1] += 1

        _push_event("capture_saved", path=str(target), name=target.name,
                    w=img.width, h=img.height, row_name=row.get("name"), category=cat)
        self._after_capture()

    def _after_capture(self):
        md, dd = self.counts_for(self.index)
        if self.category == "主图":
            if self.main_count and md >= self.main_count:
                if self.detail_count > 0:
                    self.category = "详情"
                else:
                    self._advance()
                    return
        else:
            if self.detail_count and dd >= self.detail_count:
                self._advance()
                return
        self._push_progress()

    def _advance(self):
        if self.index + 1 >= len(self.rows):
            # 全部商品截完：自动停掉钩子，避免任务完成后还能继续截
            _push_event("capture_all_done")
            self._push_progress()
            self.stop()
            return
        self.index += 1
        self.category = "主图"
        self._push_progress()
        self._open_link_with_pause()

    def set_category(self, cat):
        self.category = "详情" if cat == "详情" else "主图"
        self._push_progress()

    def next_row(self):
        self._advance()

    def _push_progress(self):
        md, dd = self.counts_for(self.index)
        cur = self.rows[self.index] if 0 <= self.index < len(self.rows) else {}
        _push_event("capture_progress",
                    index=self.index, total=len(self.rows),
                    row_name=cur.get("name", ""), category=self.category,
                    main_done=md, main_count=self.main_count,
                    detail_done=dd, detail_count=self.detail_count)


_WORKER = CaptureWorker()


def cmd_capture_start(args):
    rows = args.get("rows") or []
    return _WORKER.start(rows, args.get("main_count", 1), args.get("detail_count", 3), args.get("out_dir"))


def cmd_capture_stop(args):
    return _WORKER.stop()


def cmd_capture_set_category(args):
    _WORKER.set_category(str(args.get("category") or "主图"))
    return {"ok": True}


def cmd_capture_next_row(args):
    _WORKER.next_row()
    return {"ok": True}


def cmd_list_folder_images(args):
    """扫描一个文件夹里的所有图片（递归），给整理文档/AI修复用。args: {dir}"""
    d = Path(args.get("dir") or "")
    if not d.exists() or not d.is_dir():
        raise RuntimeError("文件夹不存在。")
    paths = S.scan_image_folder(d)
    images = []
    for p in paths:
        try:
            with S.Image.open(p) as im:
                w, h = im.size
        except Exception:
            w, h = 0, 0
        try:
            stat = p.stat()
            mtime_ns, size = stat.st_mtime_ns, stat.st_size
        except OSError:
            mtime_ns, size = 0, 0
        images.append({
            "path": str(p.resolve()), "name": p.name, "w": w, "h": h,
            "mtime_ns": mtime_ns, "size": size,
        })
    return {"images": images, "dir": str(d.resolve())}


def cmd_import_rows_file(args):
    """从 Excel/CSV/txt 文件读「名称+链接」列表。args: {path}"""
    p = Path(args.get("path") or "")
    if not p.exists():
        raise RuntimeError("文件不存在。")
    raw = S.read_import_rows(p)  # 返回 [(name, link), ...] 元组列表
    rows = [{"name": t[0], "link": t[1] if len(t) > 1 else ""} for t in raw]
    return {"rows": rows}


def cmd_parse_rows(args):
    """解析「名称+链接」文本（每行：名称<制表符或空格>链接），返回 rows。"""
    text = str(args.get("text") or "")
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 制表符或多空格分隔，取第一个链接样式的字段
        parts = line.split("\t") if "\t" in line else line.rsplit(None, 1)
        if len(parts) == 2:
            name, link = parts[0].strip(), parts[1].strip()
        else:
            name, link = line, ""
        rows.append({"name": name, "link": link})
    return {"rows": rows}


def cmd_save_capture(args):
    """保存一张截图到「自由截图」目录。args: {data_url} 或 {png_base64}
    返回 {path}。与原版命名一致：截图_时间戳.jpg。"""
    import base64
    import io as _io
    raw = args.get("png_base64") or ""
    if not raw and args.get("data_url"):
        du = str(args["data_url"])
        raw = du.split(",", 1)[1] if "," in du else du
    if not raw:
        raise RuntimeError("没有图像数据。")
    img_bytes = base64.b64decode(raw)
    img = S.Image.open(_io.BytesIO(img_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    out_dir = _configured_output_dir(args.get("out_dir")) / "自由截图"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = S.time.strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"截图_{stamp}.jpg"
    idx = 2
    while target.exists():
        target = out_dir / f"截图_{stamp}-{idx}.jpg"
        idx += 1
    img.save(target, "JPEG", quality=95)
    return {"path": str(target), "name": target.name, "w": img.width, "h": img.height, "dir": str(out_dir)}


def cmd_repair_modes(args):
    """返回 AI 修复的 5 种模式（去水印/去贴纸/去广告/清爽化/白底上图）。"""
    return {"modes": [{"key": k, "label": v} for k, v in S.REPAIR_MODES]}


def _ensure_token():
    if not _STATE["token"]:
        data = S.server_register_device(_server_url(), S.local_software_id())
        _STATE["token"] = str(data.get("token") or "")


def cmd_repair_image(args):
    """对一张图做 AI 修复（去水印/白底等）。
    args: {path, mode, keep_original}
    返回 {out} 处理后图片路径。修复后默认覆盖原图，keep_original=true 则原图备份。"""
    import threading
    import tempfile as _tf
    src = Path(args.get("path") or "")
    mode = str(args.get("mode") or "watermark")
    keep = bool(args.get("keep_original", False))
    if not src.exists():
        raise RuntimeError(f"图片不存在：{src}")
    _ensure_token()

    # 先写同目录临时文件，成功后再原子替换，避免接口失败损坏原图。
    target = src.parent / f".{src.name}.{S.uuid.uuid4().hex}.repair"
    backup_target = None
    stop = threading.Event()
    try:
        with _tf.TemporaryDirectory(prefix="snap_repair_") as tmp:
            S.server_remove_watermark_to(
                _server_url(), _STATE["token"], src, target, Path(tmp), mode, stop)
        if keep:
            backup_dir = src.parent / S.BACKUP_DIR_NAME
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_target = backup_dir / src.name
            S.shutil.copy2(src, backup_target)
        S.os.replace(target, src)
    finally:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
    stat = src.stat()
    return {
        "out": str(src), "dir": str(src.parent),
        "backup": str(backup_target) if backup_target else "",
        "replaced": True,
        "mtime_ns": stat.st_mtime_ns, "size": stat.st_size,
    }


HANDLERS = {
    "get_settings": cmd_get_settings,
    "set_output_dir": cmd_set_output_dir,
    "set_keep_original": cmd_set_keep_original,
    "ping": cmd_ping,
    "get_serial": cmd_get_serial,
    "register": cmd_register,
    "sync_quota": cmd_sync_quota,
    "list_shots": cmd_list_shots,
    "describe_image": cmd_describe_image,
    "generate_product_params": cmd_generate_product_params,
    "export_doc": cmd_export_doc,
    "stitch_long_image": cmd_stitch_long_image,
    "open_path": cmd_open_path,
    "repair_modes": cmd_repair_modes,
    "repair_image": cmd_repair_image,
    "save_capture": cmd_save_capture,
    "parse_rows": cmd_parse_rows,
    "import_rows_file": cmd_import_rows_file,
    "list_folder_images": cmd_list_folder_images,
    "capture_start": cmd_capture_start,
    "capture_stop": cmd_capture_stop,
    "capture_set_category": cmd_capture_set_category,
    "capture_next_row": cmd_capture_next_row,
    "free_capture_start": lambda args: _WORKER.start_free(args.get("out_dir")),
}


import threading as _threading
_SEND_LOCK = _threading.Lock()


def _send(obj):
    # 线程安全：命令回应和后台钩子事件可能并发写 stdout
    with _SEND_LOCK:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _push_event(event, **data):
    """后台主动推送（非命令回应）。Electron 用 event 字段区分。"""
    _send({"event": event, **data})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        rid = msg.get("id")
        cmd = msg.get("cmd")
        args = msg.get("args") or {}
        handler = HANDLERS.get(cmd)
        if not handler:
            _send({"id": rid, "ok": False, "error": f"未知命令: {cmd}"})
            continue
        try:
            data = handler(args)
            _send({"id": rid, "ok": True, "data": data})
        except Exception as e:
            try:
                S.write_error_log(f"Electron 后端命令 {cmd} 失败：{e}")
            except Exception:
                pass
            _send({"id": rid, "ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
