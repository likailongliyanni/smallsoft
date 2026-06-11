import csv
import ctypes
import json
import mimetypes
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import openpyxl
except Exception:  # pragma: no cover - optional at runtime
    openpyxl = None


APP_NAME = "图片整理器"
HOTKEY_ID = 90521
VK_F9 = 0x78
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
GWLP_WNDPROC = -4

MAIN_CATEGORY = "主图"
DETAIL_CATEGORY = "详情"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}
TEMP_SUFFIXES = (".crdownload", ".tmp", ".part", ".partial", ".download")


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def error_log_path() -> Path:
    return app_dir() / "图片整理器错误日志.txt"


def write_error_log(message: str):
    try:
        with error_log_path().open("a", encoding="utf-8") as file:
            file.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def default_download_dir() -> Path:
    """系统「下载」文件夹（Known Folder），取不到时退回 用户目录\\Downloads。"""
    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        folder_uuid = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B")
        guid = GUID()
        guid.Data1 = folder_uuid.time_low
        guid.Data2 = folder_uuid.time_mid
        guid.Data3 = folder_uuid.time_hi_version
        for index, byte in enumerate(folder_uuid.bytes[8:]):
            guid.Data4[index] = byte

        path_ptr = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)
        )
        if result == 0 and path_ptr.value:
            path = Path(path_ptr.value)
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            return path
    except Exception:
        pass
    return Path.home() / "Downloads"


def safe_folder_name(value: str, fallback: str) -> str:
    name = str(value).strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")
    return name or fallback


def try_read_text_file(path: Path) -> str:
    encodings = ("utf-8-sig", "utf-8", "gbk", "gb18030")
    last_error = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error or UnicodeDecodeError("utf-8", b"", 0, 1, "无法读取文件")


def clean_link(value) -> str:
    link = "" if value is None else str(value).strip()
    if not link:
        return ""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", link):
        return link
    if "." in link and " " not in link:
        return f"https://{link}"
    return link


def looks_like_header(name: str, link: str) -> bool:
    name_text = str(name).strip().lower()
    link_text = str(link).strip().lower()
    name_headers = {"名称", "名字", "文件夹名", "文件名", "name", "title"}
    link_headers = {"链接", "网址", "url", "link", "商品链接"}
    return name_text in name_headers and (not link_text or link_text in link_headers)


def add_import_row(rows: list[tuple[str, str]], raw_name, raw_link, row_index: int):
    name = "" if raw_name is None else str(raw_name).strip()
    link = clean_link(raw_link)
    if not name and not link:
        return
    if row_index == 1 and looks_like_header(name, link):
        return
    if not name:
        name = f"未命名_{row_index}"
    rows.append((name, link))


def read_import_rows(path: Path) -> list[tuple[str, str]]:
    path = Path(path)
    suffix = path.suffix.lower()
    rows: list[tuple[str, str]] = []

    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        if openpyxl is None:
            raise RuntimeError("当前环境缺少 openpyxl，无法读取 Excel 文件。")
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if not row:
                    continue
                name = row[0] if len(row) > 0 else ""
                link = row[1] if len(row) > 1 else ""
                add_import_row(rows, name, link, row_index)
        finally:
            workbook.close()
        return rows

    if suffix == ".csv":
        text = try_read_text_file(path)
        reader = csv.reader(text.splitlines())
        for row_index, row in enumerate(reader, start=1):
            if not row:
                continue
            name = row[0] if len(row) > 0 else ""
            link = row[1] if len(row) > 1 else ""
            add_import_row(rows, name, link, row_index)
        return rows

    text = try_read_text_file(path)
    for row_index, line in enumerate(text.splitlines(), start=1):
        if "\t" in line:
            parts = line.split("\t")
        elif "," in line:
            parts = next(csv.reader([line]))
        else:
            parts = [line]
        name = parts[0] if len(parts) > 0 else ""
        link = parts[1] if len(parts) > 1 else ""
        add_import_row(rows, name, link, row_index)
    return rows


def is_image_candidate(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(TEMP_SUFFIXES):
        return False
    return os.path.splitext(lower)[1] in IMAGE_EXTS


def convert_to_jpg(source: Path, target: Path, quality: int):
    """统一转 JPG：透明背景补白、EXIF 方向纠正。"""
    with Image.open(source) as image:
        image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        target.parent.mkdir(parents=True, exist_ok=True)
        quality = max(30, min(100, int(quality or 95)))
        image.save(target, "JPEG", quality=quality, optimize=True)


# ---------------- AI 去水印（阿里云百炼 DashScope） ----------------
# 和网站后台同一套阿里云全家桶：模型 wanx2.1-imageedit 的 remove_watermark 功能。
# 只用标准库 urllib，不增加打包体积。

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"
WATERMARK_MODEL = "wanx2.1-imageedit"
WATERMARK_MIN_SIDE = 512
WATERMARK_MAX_SIDE = 4096
WATERMARK_MAX_BYTES = 10 * 1024 * 1024


def config_path() -> Path:
    return app_dir() / "图片整理器配置.json"


def load_config() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(updates: dict):
    data = load_config()
    data.update(updates)
    try:
        config_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        write_error_log(f"保存配置失败：{exc}")


class DashScopeError(RuntimeError):
    pass


def friendly_dashscope_error(code: str, message: str) -> str:
    text = f"{code} {message}".lower()
    if "invalidapikey" in text or "invalid_api_key" in text or "incorrect api key" in text:
        return "API Key 无效，请检查填写的 DashScope Key。"
    if "arrearage" in text:
        return "阿里云账户欠费，请到百炼控制台充值。"
    if "throttling" in text or "ratelimit" in text or "rate limit" in text:
        return "接口被限流，稍后会自动重试。"
    if "datainspection" in text or "inappropriate" in text or "green" in text:
        return "图片未通过内容审核，已跳过。"
    return f"{code}：{message}"[:200]


def _ds_request(url: str, api_key: str, payload: dict | None = None,
                headers: dict | None = None, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    request.add_header("Authorization", f"Bearer {api_key}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            info = json.loads(body)
            code = info.get("code") or exc.code
            message = info.get("message") or body[:200]
        except Exception:
            code, message = exc.code, body[:200]
        if exc.code == 401:
            raise DashScopeError("API Key 无效，请检查填写的 DashScope Key。")
        raise DashScopeError(friendly_dashscope_error(str(code), str(message)))
    except urllib.error.URLError as exc:
        raise DashScopeError(f"网络请求失败：{exc.reason}")


def _encode_multipart(fields: list, filename: str, file_bytes: bytes):
    boundary = f"----PicOrganizer{uuid.uuid4().hex}"
    chunks = []
    for name, value in fields:
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_bytes)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def ds_upload_image(api_key: str, path: Path) -> str:
    """把本地图片传到 DashScope 临时存储（48 小时自动删除），返回 oss:// 地址。"""
    policy = _ds_request(
        f"{DASHSCOPE_BASE}/api/v1/uploads?action=getPolicy&model={WATERMARK_MODEL}",
        api_key,
    )
    data = policy.get("data") or {}
    needed = ("upload_host", "upload_dir", "policy", "signature", "oss_access_key_id")
    if not all(data.get(key) for key in needed):
        raise DashScopeError("获取上传授权失败，请稍后重试。")

    key = f"{data['upload_dir']}/{uuid.uuid4().hex}{path.suffix.lower() or '.jpg'}"
    fields = [
        ("OSSAccessKeyId", str(data["oss_access_key_id"])),
        ("Signature", str(data["signature"])),
        ("policy", str(data["policy"])),
        ("key", key),
        ("x-oss-object-acl", str(data.get("x_oss_object_acl", "private"))),
        ("x-oss-forbid-overwrite", str(data.get("x_oss_forbid_overwrite", "true"))),
        ("success_action_status", "200"),
    ]
    body, content_type = _encode_multipart(fields, path.name, path.read_bytes())
    request = urllib.request.Request(str(data["upload_host"]), data=body, method="POST")
    request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=180):
            pass
    except urllib.error.HTTPError as exc:
        raise DashScopeError(f"图片上传失败：HTTP {exc.code}")
    except urllib.error.URLError as exc:
        raise DashScopeError(f"图片上传失败：{exc.reason}")
    return f"oss://{key}"


def ds_create_watermark_task(api_key: str, oss_url: str) -> str:
    payload = {
        "model": WATERMARK_MODEL,
        "input": {
            "function": "remove_watermark",
            "prompt": "去除图片中的水印、文字水印和角标，保持商品和画面其他内容不变",
            "base_image_url": oss_url,
        },
        "parameters": {"n": 1},
    }
    response = _ds_request(
        f"{DASHSCOPE_BASE}/api/v1/services/aigc/image2image/image-synthesis",
        api_key,
        payload,
        headers={
            "X-DashScope-Async": "enable",
            "X-DashScope-OssResourceResolve": "enable",
        },
    )
    task_id = (response.get("output") or {}).get("task_id")
    if not task_id:
        raise DashScopeError("创建去水印任务失败，请稍后重试。")
    return str(task_id)


def ds_wait_task(api_key: str, task_id: str, stop_event: threading.Event,
                 timeout: float = 300.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if stop_event.is_set():
            raise DashScopeError("已停止。")
        info = _ds_request(f"{DASHSCOPE_BASE}/api/v1/tasks/{task_id}", api_key)
        output = info.get("output") or {}
        status = str(output.get("task_status") or "")
        if status == "SUCCEEDED":
            results = output.get("results") or []
            url = results[0].get("url") if results and isinstance(results[0], dict) else None
            if not url:
                raise DashScopeError("任务完成但没有返回结果图。")
            return str(url)
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            raise DashScopeError(friendly_dashscope_error(
                str(output.get("code") or status),
                str(output.get("message") or "任务失败"),
            ))
        stop_event.wait(2)
    raise DashScopeError("任务超时（5 分钟）。")


def ds_download_bytes(url: str) -> bytes:
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as response:
            return response.read()
    except Exception as exc:
        raise DashScopeError(f"下载结果图失败：{exc}")


def prepare_watermark_input(path: Path, temp_dir: Path) -> Path:
    """送 AI 前的预处理：统一转成尺寸合规（512~4096px、≤10MB）的 JPG 临时文件。"""
    with Image.open(path) as image:
        image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        width, height = image.size
        if min(width, height) <= 0:
            raise DashScopeError("图片尺寸异常，已跳过。")
        if max(width, height) / min(width, height) > WATERMARK_MAX_SIDE / WATERMARK_MIN_SIDE:
            raise DashScopeError("长宽比过大（例如详情长图），AI 接口不支持，已跳过。")

        scale = 1.0
        if min(width, height) < WATERMARK_MIN_SIDE:
            scale = WATERMARK_MIN_SIDE / min(width, height)
        elif max(width, height) > WATERMARK_MAX_SIDE:
            scale = WATERMARK_MAX_SIDE / max(width, height)
        if scale != 1.0:
            image = image.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.LANCZOS,
            )

        target = temp_dir / f"{uuid.uuid4().hex}.jpg"
        for quality in (92, 85, 75):
            image.save(target, "JPEG", quality=quality, optimize=True)
            if target.stat().st_size <= WATERMARK_MAX_BYTES:
                break
        return target


class DownloadMonitor:
    """监控下载目录：只认开启之后新出现的、写入完成的图片文件。

    线程内只做检测，结果（Path）放入 results 队列，由主线程取走归档。
    判定「写入完成」：连续两次扫描文件大小不变且大于 0。
    """

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.results: queue.Queue = queue.Queue()
        self.watch_dir: Path | None = None

    def start(self, watch_dir: Path):
        self.stop()
        self.watch_dir = Path(watch_dir)
        self.stop_event = threading.Event()
        self.results = queue.Queue()
        self.thread = threading.Thread(target=self._run, name="DownloadMonitor", daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            self.thread.join(timeout=2)
        self.thread = None

    def _scan_names(self) -> set[str]:
        try:
            with os.scandir(self.watch_dir) as entries:
                return {entry.name for entry in entries}
        except OSError:
            return set()

    def _run(self):
        done = self._scan_names()
        pending: dict[str, int] = {}

        while not self.stop_event.wait(self.interval):
            try:
                with os.scandir(self.watch_dir) as scan:
                    entries = [entry for entry in scan if entry.is_file()]
            except OSError:
                continue

            ready: list[tuple[float, Path]] = []
            for entry in entries:
                name = entry.name
                if name in done or not is_image_candidate(name):
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                if stat.st_size > 0 and pending.get(name) == stat.st_size:
                    done.add(name)
                    pending.pop(name, None)
                    ready.append((stat.st_mtime, Path(entry.path)))
                else:
                    pending[name] = stat.st_size

            for _mtime, path in sorted(ready):
                self.results.put(path)


class HotkeyManager:
    def __init__(self, root: tk.Tk, callback):
        self.root = root
        self.callback = callback
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.hwnd = int(root.winfo_id())
        self.old_proc = None
        self.new_proc = None
        self.registered = False

        self.WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )

        self.user32.SetWindowLongPtrW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        self.user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        self.user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        self.user32.CallWindowProcW.restype = ctypes.c_longlong
        self.user32.RegisterHotKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        self.user32.RegisterHotKey.restype = ctypes.c_bool
        self.user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.user32.UnregisterHotKey.restype = ctypes.c_bool

    def install(self) -> bool:
        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_HOTKEY and int(wparam) == HOTKEY_ID:
                self.root.after(0, self.callback)
                return 0
            return self.user32.CallWindowProcW(self.old_proc, hwnd, msg, wparam, lparam)

        self.new_proc = self.WNDPROC(wndproc)
        proc_ptr = ctypes.cast(self.new_proc, ctypes.c_void_p)
        self.old_proc = self.user32.SetWindowLongPtrW(
            self.hwnd, GWLP_WNDPROC, proc_ptr
        )
        if not self.old_proc:
            raise ctypes.WinError(ctypes.get_last_error())

        self.registered = self.user32.RegisterHotKey(
            self.hwnd, HOTKEY_ID, MOD_NOREPEAT, VK_F9
        )
        if not self.registered:
            self.registered = self.user32.RegisterHotKey(self.hwnd, HOTKEY_ID, 0, VK_F9)
        return self.registered

    def uninstall(self):
        if self.registered:
            self.user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)
            self.registered = False
        if self.old_proc:
            self.user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self.old_proc)
            self.old_proc = None
        self.new_proc = None


class WorkPanel(tk.Toplevel):
    """工作模式下的置顶浮窗：类别切换、下一行、撤销等都在这里。"""

    def __init__(self, owner):
        super().__init__(owner.root)
        self.owner = owner
        self.title("整理中")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", owner.stop_work_mode)

        frame = ttk.Frame(self, padding=(12, 10))
        frame.grid(row=0, column=0, sticky="nsew")
        for column in range(3):
            frame.columnconfigure(column, weight=1)

        ttk.Label(frame, text="当前商品").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            frame,
            textvariable=owner.panel_current_var,
            font=("Microsoft YaHei UI", 12, "bold"),
            wraplength=380,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 6))
        ttk.Label(frame, textvariable=owner.panel_progress_var, wraplength=380).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(0, 4)
        )
        ttk.Label(frame, textvariable=owner.panel_link_var, wraplength=380).grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(0, 4)
        )
        ttk.Label(frame, textvariable=owner.panel_status_var, wraplength=380, foreground="#0b6b3a").grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=(0, 8)
        )
        ttk.Separator(frame).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        category_row = ttk.Frame(frame)
        category_row.grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(category_row, text="保存到：").grid(row=0, column=0, padx=(0, 6))
        ttk.Radiobutton(
            category_row,
            text=MAIN_CATEGORY,
            value=MAIN_CATEGORY,
            variable=owner.category_var,
        ).grid(row=0, column=1)
        ttk.Radiobutton(
            category_row,
            text=DETAIL_CATEGORY,
            value=DETAIL_CATEGORY,
            variable=owner.category_var,
        ).grid(row=0, column=2, padx=(10, 0))

        ttk.Button(frame, text="下一行 ▶", style="Accent.TButton", command=owner.next_row).grid(
            row=7, column=0, sticky="ew"
        )
        ttk.Button(frame, text="跳过当前", command=owner.skip_current).grid(
            row=7, column=1, sticky="ew", padx=(8, 0)
        )
        ttk.Button(frame, text="复制上一个", command=owner.copy_previous_to_current).grid(
            row=7, column=2, sticky="ew", padx=(8, 0)
        )
        ttk.Button(frame, text="撤销上一张", command=owner.undo_last_archive).grid(
            row=8, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(frame, text="显示程序 F9", command=owner.show_main_window).grid(
            row=8, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )
        ttk.Button(frame, text="结束整理", command=owner.stop_work_mode).grid(
            row=8, column=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )
        self.geometry("+18+18")


class WatermarkWindow(tk.Toplevel):
    """AI 批量去水印：选文件夹/图片 → 并发调用阿里云 → 存到 xxx_去水印 目录，原图不动。"""

    def __init__(self, owner):
        super().__init__(owner.root)
        self.owner = owner
        self.title("AI 批量去水印")
        self.geometry("700x600")
        self.minsize(640, 540)
        self.transient(owner.root)

        config = load_config()
        default_key = str(config.get("dashscope_api_key") or os.environ.get("DASHSCOPE_API_KEY", ""))
        self.api_key_var = tk.StringVar(value=default_key)
        self.show_key_var = tk.BooleanVar(value=False)
        self.recursive_var = tk.BooleanVar(value=True)
        self.workers_var = tk.IntVar(value=2)
        self.source_var = tk.StringVar(value="还没有选择图片")
        self.output_var = tk.StringVar(value="-")
        self.progress_var = tk.StringVar(value="待开始")

        self.tasks = []  # [(源文件 Path, 输出文件 Path)]
        self.running = False
        self.stop_event = threading.Event()
        self.events: queue.Queue = queue.Queue()
        self.threads = []
        self.temp_dir = None
        self.done = 0
        self.failed = 0

        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)
        pad = {"padx": 14}

        ttk.Label(
            self,
            text="批量去除图片水印（阿里云百炼 AI，按张计费）。请只处理你自己拥有或已获授权的图片。",
            style="Hint.TLabel",
            wraplength=640,
        ).grid(row=0, column=0, sticky="w", pady=(12, 8), **pad)

        key_row = ttk.Frame(self)
        key_row.grid(row=1, column=0, sticky="ew", **pad)
        key_row.columnconfigure(1, weight=1)
        ttk.Label(key_row, text="API Key").grid(row=0, column=0, padx=(0, 8))
        self.key_entry = ttk.Entry(key_row, textvariable=self.api_key_var, show="*")
        self.key_entry.grid(row=0, column=1, sticky="ew")
        ttk.Checkbutton(
            key_row, text="显示", variable=self.show_key_var, command=self.toggle_key_visible
        ).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(
            key_row,
            text="和网站后台同一个 DASHSCOPE_API_KEY（阿里云百炼控制台获取），保存在本机配置文件。",
            style="Hint.TLabel",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        source_row = ttk.Frame(self)
        source_row.grid(row=2, column=0, sticky="ew", pady=(12, 0), **pad)
        self.folder_button = ttk.Button(source_row, text="选择文件夹", command=self.choose_folder)
        self.folder_button.grid(row=0, column=0)
        self.files_button = ttk.Button(source_row, text="选择图片", command=self.choose_files)
        self.files_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Checkbutton(source_row, text="包含子文件夹", variable=self.recursive_var).grid(
            row=0, column=2, padx=(12, 0)
        )
        ttk.Label(source_row, text="并发").grid(row=0, column=3, padx=(16, 6))
        ttk.Spinbox(source_row, from_=1, to=3, width=4, textvariable=self.workers_var).grid(
            row=0, column=4
        )

        ttk.Label(self, textvariable=self.source_var, style="Hint.TLabel", wraplength=640).grid(
            row=3, column=0, sticky="w", pady=(8, 0), **pad
        )
        ttk.Label(self, textvariable=self.output_var, style="Hint.TLabel", wraplength=640).grid(
            row=4, column=0, sticky="w", pady=(2, 0), **pad
        )

        action_row = ttk.Frame(self)
        action_row.grid(row=5, column=0, sticky="ew", pady=(12, 8), **pad)
        action_row.columnconfigure(2, weight=1)
        self.start_button = ttk.Button(
            action_row, text="开始去水印", style="Accent.TButton", command=self.start
        )
        self.start_button.grid(row=0, column=0)
        self.stop_button = ttk.Button(action_row, text="停止", command=self.stop, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Label(action_row, textvariable=self.progress_var).grid(row=0, column=2, sticky="e")

        bottom = ttk.Frame(self)
        bottom.grid(row=6, column=0, sticky="nsew", pady=(0, 12), **pad)
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(1, weight=1)
        self.progressbar = ttk.Progressbar(bottom, mode="determinate")
        self.progressbar.grid(row=0, column=0, sticky="ew")
        self.log_box = scrolledtext.ScrolledText(bottom, height=10, wrap="word")
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.log_box.configure(state="disabled")

        self.log("提示：每张图大约几秒到几十秒；尺寸小于 512px 的会自动放大，超长的详情图会跳过。")

    def toggle_key_visible(self):
        self.key_entry.configure(show="" if self.show_key_var.get() else "*")

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ---------- 任务收集 ----------

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self, title="选择要去水印的图片文件夹")
        if not folder:
            return
        folder_path = Path(folder)
        pattern = folder_path.rglob("*") if self.recursive_var.get() else folder_path.glob("*")
        sources = []
        for path in pattern:
            if not path.is_file() or not is_image_candidate(path.name):
                continue
            parent_parts = path.relative_to(folder_path).parts[:-1]
            if any(part == "去水印" or part.endswith("_去水印") for part in parent_parts):
                continue
            sources.append(path)
        sources.sort()
        if not sources:
            messagebox.showinfo(APP_NAME, "这个文件夹里没有找到图片。", parent=self)
            return
        output_root = folder_path.parent / f"{folder_path.name}_去水印"
        self.set_tasks(
            [(path, output_root / path.relative_to(folder_path).with_suffix(".jpg")) for path in sources],
            f"已选择文件夹：{folder_path}（{len(sources)} 张图片）",
            f"输出到：{output_root}（保持原目录结构，原图不动）",
        )

    def choose_files(self):
        names = filedialog.askopenfilenames(
            parent=self,
            title="选择要去水印的图片",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.gif *.bmp *.avif"), ("所有文件", "*.*")],
        )
        if not names:
            return
        sources = [Path(name) for name in names if is_image_candidate(Path(name).name)]
        if not sources:
            messagebox.showinfo(APP_NAME, "没有选择到支持的图片格式。", parent=self)
            return
        self.set_tasks(
            [(path, path.parent / "去水印" / f"{path.stem}.jpg") for path in sources],
            f"已选择 {len(sources)} 张图片",
            "输出到：各图片所在目录的「去水印」子文件夹（原图不动）",
        )

    def set_tasks(self, tasks, source_text: str, output_text: str):
        used = set()
        unique_tasks = []
        for source, target in tasks:
            candidate = target
            counter = 2
            while str(candidate).lower() in used:
                candidate = target.with_name(f"{target.stem}-{counter}{target.suffix}")
                counter += 1
            used.add(str(candidate).lower())
            unique_tasks.append((source, candidate))
        self.tasks = unique_tasks
        self.source_var.set(source_text)
        self.output_var.set(output_text)
        self.progress_var.set(f"0/{len(self.tasks)}")
        self.progressbar.configure(maximum=max(1, len(self.tasks)), value=0)

    # ---------- 执行 ----------

    def start(self):
        if self.running:
            return
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning(APP_NAME, "请先填写 DashScope API Key。", parent=self)
            return
        if not self.tasks:
            messagebox.showwarning(APP_NAME, "请先选择要处理的文件夹或图片。", parent=self)
            return

        save_config({"dashscope_api_key": api_key})
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pic_wm_"))
        self.stop_event = threading.Event()
        self.events = queue.Queue()
        self.done = 0
        self.failed = 0
        self.progressbar.configure(maximum=len(self.tasks), value=0)

        task_queue = queue.Queue()
        for task in self.tasks:
            task_queue.put(task)
        workers = max(1, min(3, int(self.workers_var.get() or 2)))
        self.threads = []
        for index in range(workers):
            thread = threading.Thread(
                target=self.worker, args=(api_key, task_queue),
                name=f"Watermark-{index + 1}", daemon=True,
            )
            thread.start()
            self.threads.append(thread)

        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.folder_button.configure(state="disabled")
        self.files_button.configure(state="disabled")
        self.log(f"开始处理 {len(self.tasks)} 张图片，{workers} 个并发。")
        self.after(300, self.poll_events)

    def stop(self):
        if self.running:
            self.stop_event.set()
            self.log("正在停止，等待进行中的任务结束...")

    def worker(self, api_key: str, task_queue: queue.Queue):
        while not self.stop_event.is_set():
            try:
                source, target = task_queue.get_nowait()
            except queue.Empty:
                return
            last_error = None
            for attempt in (1, 2):
                if self.stop_event.is_set():
                    last_error = "已停止。"
                    break
                try:
                    self.process_one(api_key, source, target)
                    last_error = None
                    break
                except DashScopeError as exc:
                    last_error = str(exc)
                    fatal = ("API Key" in last_error or "欠费" in last_error
                             or "已跳过" in last_error or "已停止" in last_error)
                    if fatal or attempt == 2:
                        break
                    self.stop_event.wait(2)
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt == 2:
                        break
                    self.stop_event.wait(2)
            if last_error is None:
                self.events.put(("ok", source, str(target)))
            else:
                self.events.put(("fail", source, last_error))

    def process_one(self, api_key: str, source: Path, target: Path):
        prepared = prepare_watermark_input(source, self.temp_dir)
        try:
            oss_url = ds_upload_image(api_key, prepared)
            task_id = ds_create_watermark_task(api_key, oss_url)
            result_url = ds_wait_task(api_key, task_id, self.stop_event)
            data = ds_download_bytes(result_url)
        finally:
            try:
                prepared.unlink()
            except OSError:
                pass

        target.parent.mkdir(parents=True, exist_ok=True)
        temp_out = self.temp_dir / f"{uuid.uuid4().hex}.result"
        temp_out.write_bytes(data)
        try:
            convert_to_jpg(temp_out, target, 95)
        finally:
            try:
                temp_out.unlink()
            except OSError:
                pass

    def poll_events(self):
        try:
            while True:
                kind, source, info = self.events.get_nowait()
                if kind == "ok":
                    self.done += 1
                    self.log(f"完成：{source.name}")
                else:
                    self.failed += 1
                    self.log(f"失败：{source.name} —— {info}")
                    if "API Key" in info or "欠费" in info:
                        self.stop_event.set()
                self.progressbar.configure(value=self.done + self.failed)
                self.progress_var.set(
                    f"{self.done + self.failed}/{len(self.tasks)} · 成功 {self.done} · 失败 {self.failed}"
                )
        except queue.Empty:
            pass
        if not self.running:
            return
        if any(thread.is_alive() for thread in self.threads):
            self.after(300, self.poll_events)
        else:
            self.finish()

    def finish(self):
        self.running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.folder_button.configure(state="normal")
        self.files_button.configure(state="normal")
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None
        stopped = self.stop_event.is_set() and (self.done + self.failed) < len(self.tasks)
        summary = f"处理结束：成功 {self.done} 张，失败 {self.failed} 张"
        if stopped:
            summary += "（已手动停止，未处理完）"
        self.log(summary)

    def on_close(self):
        if self.running:
            if not messagebox.askyesno(APP_NAME, "正在去水印，确定停止并关闭吗？", parent=self):
                return
            self.stop_event.set()
            self.running = False
            if self.temp_dir:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.destroy()


class PictureOrganizerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("980x680")
        self.root.minsize(900, 600)

        self.items: list[dict] = []
        self.current_index = 0
        self.work_mode = False
        self.work_panel: WorkPanel | None = None
        self.watermark_window: WatermarkWindow | None = None
        self.monitor = DownloadMonitor()
        self.undo_stack: list[dict] = []
        self.polling_results = False

        self.output_dir_var = tk.StringVar(value=str(app_dir() / "整理结果"))
        self.watch_dir_var = tk.StringVar(value=str(default_download_dir()))
        self.main_count_var = tk.IntVar(value=1)
        self.detail_count_var = tk.IntVar(value=1)
        self.prefix_var = tk.StringVar(value="pic")
        self.quality_var = tk.IntVar(value=95)
        self.overwrite_var = tk.BooleanVar(value=True)
        self.enabled_var = tk.BooleanVar(value=True)
        self.auto_open_links_var = tk.BooleanVar(value=True)
        self.category_var = tk.StringVar(value=MAIN_CATEGORY)
        self.status_var = tk.StringVar(value="请先导入文件夹名，然后按 F9 开启工作模式。")
        self.current_var = tk.StringVar(value="-")
        self.next_path_var = tk.StringVar(value="-")
        self.panel_current_var = tk.StringVar(value="-")
        self.panel_progress_var = tk.StringVar(value="进度：-")
        self.panel_link_var = tk.StringVar(value="链接：-")
        self.panel_status_var = tk.StringVar(value="把图片「另存为」到监控目录即可自动归档")
        self.mode_var = tk.StringVar(value="待开始")
        self.hotkey_var = tk.StringVar(value="F9 热键：注册中")

        self.hotkey = HotkeyManager(self.root, self.hotkey_pressed)
        self.category_var.trace_add("write", lambda *_: self.refresh_state())
        self.root.report_callback_exception = self.report_callback_exception

        self.configure_style()
        self.build_ui()
        self.root.update_idletasks()

        try:
            ok = self.hotkey.install()
            self.hotkey_var.set("F9 热键：已启用" if ok else "F9 热键：注册失败")
            if not ok:
                self.log("F9 热键注册失败，可能被其他软件占用。可以使用窗口里的「开启整理」按钮。")
        except Exception as exc:
            self.hotkey_var.set("F9 热键：注册失败")
            self.log(f"F9 热键注册失败：{exc}")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_state()

    def configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=(10, 5))
        style.configure("Accent.TButton", padding=(12, 6))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Hint.TLabel", foreground="#666666")
        style.configure("Status.TLabel", foreground="#0b6b3a")

    def report_callback_exception(self, exc_type, exc_value, exc_tb):
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        write_error_log(details)
        self.status_var.set("程序遇到错误，已写入错误日志。")
        try:
            messagebox.showerror(APP_NAME, f"程序遇到错误，已写入：\n{error_log_path()}")
        except tk.TclError:
            pass

    def build_ui(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        header = ttk.Frame(root, padding=(16, 14, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.hotkey_var, style="Status.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        ttk.Label(
            header,
            text="导入 A列名称 + B列链接，按 F9 开启工作模式；在浏览器里把原图「另存为」到监控目录，软件自动归档改名。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        controls = ttk.Frame(root, padding=(16, 4, 16, 8))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="输出目录").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(controls, textvariable=self.output_dir_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(controls, text="选择", command=self.choose_output_dir).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(controls, text="打开", command=self.open_output_dir).grid(
            row=0, column=3, padx=(8, 0)
        )

        ttk.Label(controls, text="监控目录").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(controls, textvariable=self.watch_dir_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(controls, text="选择", command=self.choose_watch_dir).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0)
        )
        ttk.Button(controls, text="默认下载", command=self.reset_watch_dir).grid(
            row=1, column=3, padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(controls, text="数量提示").grid(row=2, column=0, sticky="w", pady=(10, 0))
        settings = ttk.Frame(controls)
        settings.grid(row=2, column=1, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Label(settings, text="主图").grid(row=0, column=0, padx=(0, 6))
        ttk.Spinbox(settings, from_=0, to=999, width=6, textvariable=self.main_count_var, command=self.refresh_state).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(settings, text="详情").grid(row=0, column=2, padx=(14, 6))
        ttk.Spinbox(settings, from_=0, to=999, width=6, textvariable=self.detail_count_var, command=self.refresh_state).grid(
            row=0, column=3, sticky="w"
        )
        ttk.Label(settings, text="（只做进度提示，不会自动跳行）", style="Hint.TLabel").grid(
            row=0, column=4, padx=(8, 0)
        )
        ttk.Label(settings, text="文件名前缀").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Entry(settings, width=10, textvariable=self.prefix_var).grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="JPG质量").grid(row=1, column=3, padx=(14, 6), pady=(8, 0))
        ttk.Spinbox(settings, from_=30, to=100, width=6, textvariable=self.quality_var).grid(
            row=1, column=4, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(settings, text="覆盖同名文件", variable=self.overwrite_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(settings, text="启用 F9", variable=self.enabled_var).grid(
            row=2, column=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(settings, text="切行后自动打开链接", variable=self.auto_open_links_var).grid(
            row=2, column=3, columnspan=2, sticky="w", padx=(14, 0), pady=(8, 0)
        )

        body = ttk.Panedwindow(root, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(left)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="导入文件", command=self.import_file).grid(row=0, column=0)
        ttk.Button(toolbar, text="从剪贴板导入", command=self.import_clipboard).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(toolbar, text="打开当前链接", command=self.open_current_link_manual).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(toolbar, text="清空列表", command=self.clear_items).grid(
            row=0, column=3, padx=(8, 0)
        )
        ttk.Button(toolbar, text="重置进度", command=self.reset_progress).grid(
            row=0, column=4, padx=(8, 0)
        )
        ttk.Button(toolbar, text="跳过当前", command=self.skip_current).grid(
            row=0, column=5, padx=(8, 0)
        )
        ttk.Button(toolbar, text="复制上一个", command=self.copy_previous_to_current).grid(
            row=0, column=6, padx=(8, 0)
        )
        ttk.Button(toolbar, text="AI 去水印", command=self.open_watermark_window).grid(
            row=0, column=7, padx=(8, 0)
        )

        columns = ("index", "name", "link", "main", "detail", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("index", text="#")
        self.tree.heading("name", text="文件夹名")
        self.tree.heading("link", text="链接")
        self.tree.heading("main", text="主图")
        self.tree.heading("detail", text="详情")
        self.tree.heading("status", text="状态")
        self.tree.column("index", width=50, anchor="center", stretch=False)
        self.tree.column("name", width=260, anchor="w")
        self.tree.column("link", width=90, anchor="center", stretch=False)
        self.tree.column("main", width=80, anchor="center", stretch=False)
        self.tree.column("detail", width=80, anchor="center", stretch=False)
        self.tree.column("status", width=90, anchor="center", stretch=False)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        right.columnconfigure(0, weight=1)
        right.rowconfigure(8, weight=1)

        ttk.Label(right, text="当前文件夹").grid(row=0, column=0, sticky="w")
        ttk.Label(right, textvariable=self.current_var, font=("Microsoft YaHei UI", 12, "bold")).grid(
            row=1, column=0, sticky="ew", pady=(4, 12)
        )

        ttk.Label(right, text="下一张保存到").grid(row=2, column=0, sticky="w")
        ttk.Label(right, textvariable=self.next_path_var, wraplength=360, style="Hint.TLabel").grid(
            row=3, column=0, sticky="ew", pady=(4, 12)
        )

        ttk.Label(right, text="工作状态").grid(row=4, column=0, sticky="w")
        ttk.Label(right, textvariable=self.mode_var, style="Hint.TLabel").grid(
            row=5, column=0, sticky="ew", pady=(4, 8)
        )

        actions = ttk.Frame(right)
        actions.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        for column in range(4):
            actions.columnconfigure(column, weight=1)
        self.start_button = ttk.Button(
            actions, text="开启整理 F9", style="Accent.TButton", command=self.hotkey_pressed
        )
        self.start_button.grid(row=0, column=0, sticky="ew")
        self.stop_button = ttk.Button(actions, text="结束整理", command=self.stop_work_mode)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(actions, text="打开当前链接", command=self.open_current_link_manual).grid(
            row=0, column=2, sticky="ew", padx=(8, 0)
        )
        ttk.Button(actions, text="下一行", command=self.next_row).grid(
            row=0, column=3, sticky="ew", padx=(8, 0)
        )

        ttk.Label(right, text="运行日志").grid(row=8, column=0, sticky="sw")
        self.log_box = scrolledtext.ScrolledText(right, height=12, wrap="word")
        self.log_box.grid(row=9, column=0, sticky="nsew", pady=(4, 0))
        self.log_box.configure(state="disabled")

        footer = ttk.Frame(root, padding=(16, 0, 16, 12))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="w"
        )

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def choose_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir_var.set(path)
            self.refresh_state()

    def open_output_dir(self):
        path = Path(self.output_dir_var.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def choose_watch_dir(self):
        path = filedialog.askdirectory(title="选择要监控的下载目录")
        if path:
            self.watch_dir_var.set(path)
            if self.work_mode:
                self.monitor.start(Path(path))
                self.log(f"监控目录已切换：{path}")

    def reset_watch_dir(self):
        self.watch_dir_var.set(str(default_download_dir()))

    def open_link(self, item, force: bool = False) -> bool:
        link = item.get("link", "")
        if not link:
            self.status_var.set(f"{item.get('folder', '当前项')} 没有链接。")
            return False
        if item.get("opened") and not force:
            return False
        try:
            os.startfile(link)
        except Exception as exc:
            self.status_var.set(f"打开链接失败：{exc}")
            self.log(f"打开链接失败：{item.get('folder')} -> {link}，{exc}")
            return False
        item["opened"] = True
        index = self.items.index(item) if item in self.items else -1
        self.refresh_tree_row(index)
        if index == self.current_index:
            self.refresh_state()
        self.status_var.set(f"已打开链接：{item.get('folder')}")
        self.log(f"已打开链接：{item.get('folder')} -> {link}")
        return True

    def open_current_link_once(self) -> bool:
        if not (0 <= self.current_index < len(self.items)):
            return False
        return self.open_link(self.items[self.current_index], force=False)

    def open_current_link_manual(self):
        if not (0 <= self.current_index < len(self.items)):
            self.status_var.set("没有当前链接可打开。")
            return
        self.open_link(self.items[self.current_index], force=True)

    def import_file(self):
        filename = filedialog.askopenfilename(
            title="导入 A列名称 + B列链接",
            filetypes=[
                ("支持的文件", "*.xlsx *.xlsm *.csv *.txt"),
                ("Excel", "*.xlsx *.xlsm"),
                ("CSV", "*.csv"),
                ("文本", "*.txt"),
                ("所有文件", "*.*"),
            ],
        )
        if not filename:
            return
        try:
            values = read_import_rows(Path(filename))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"导入失败：\n{exc}")
            return
        self.set_items(values)
        self.log(f"已从文件导入 {len(values)} 条数据：{filename}")

    def import_clipboard(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning(APP_NAME, "剪贴板里没有可读取的文本。")
            return
        values = []
        for row_index, line in enumerate(text.splitlines(), start=1):
            if "\t" in line:
                parts = line.split("\t")
            elif "," in line:
                parts = next(csv.reader([line]))
            else:
                parts = [line]
            name = parts[0] if len(parts) > 0 else ""
            link = parts[1] if len(parts) > 1 else ""
            add_import_row(values, name, link, row_index)
        self.set_items(values)
        self.log(f"已从剪贴板导入 {len(values)} 条数据。")

    def set_items(self, values: list):
        self.items = []
        for idx, value in enumerate(values, start=1):
            if isinstance(value, (tuple, list)):
                original = str(value[0]).strip() if len(value) > 0 else f"未命名_{idx}"
                link = clean_link(value[1] if len(value) > 1 else "")
            else:
                original = str(value).strip()
                link = ""
            folder = safe_folder_name(original, f"未命名_{idx}")
            self.items.append(
                {
                    "original": original,
                    "folder": folder,
                    "link": link,
                    "opened": False,
                    "main": 0,
                    "detail": 0,
                    "status": "等待",
                }
            )
        self.current_index = 0
        self.undo_stack = []
        self.rebuild_tree()
        self.refresh_state()

    def rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        for idx, item in enumerate(self.items):
            link_status = self.link_status_text(item)
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    idx + 1,
                    item["folder"],
                    link_status,
                    item["main"],
                    item["detail"],
                    item["status"],
                ),
            )
        self.highlight_current()

    def refresh_tree_row(self, index: int):
        if index < 0 or index >= len(self.items):
            return
        item = self.items[index]
        if not self.tree.exists(str(index)):
            return
        link_status = self.link_status_text(item)
        self.tree.item(
            str(index),
            values=(
                index + 1,
                item["folder"],
                link_status,
                item["main"],
                item["detail"],
                item["status"],
            ),
        )

    def link_status_text(self, item) -> str:
        if not item.get("link"):
            return "无"
        return "已打开" if item.get("opened") else "有"

    def highlight_current(self):
        for idx, item in enumerate(self.items):
            if idx < self.current_index:
                item["status"] = "完成"
            elif idx == self.current_index:
                item["status"] = "当前"
            else:
                item["status"] = "等待"
            self.refresh_tree_row(idx)
        if 0 <= self.current_index < len(self.items):
            iid = str(self.current_index)
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def clear_items(self):
        if self.items and not messagebox.askyesno(APP_NAME, "确定清空当前列表和进度吗？"):
            return
        self.items = []
        self.current_index = 0
        self.undo_stack = []
        self.rebuild_tree()
        self.refresh_state()
        self.log("已清空列表。")

    def reset_progress(self):
        for item in self.items:
            item["main"] = 0
            item["detail"] = 0
            item["opened"] = False
        self.current_index = 0
        self.undo_stack = []
        self.category_var.set(MAIN_CATEGORY)
        self.highlight_current()
        self.refresh_state()
        self.log("已重置进度。")

    # ---- 行推进 ----

    def current_item(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    def next_row(self):
        item = self.current_item()
        if not item:
            self.status_var.set("已经是最后一行了。")
            return
        if item["main"] + item["detail"] == 0:
            if not messagebox.askyesno(
                APP_NAME,
                f"「{item['folder']}」还没有归档任何图片。\n确定进入下一行吗？",
                parent=self.work_panel if self.work_panel else self.root,
            ):
                return
        self.advance_to_next_item()

    def skip_current(self):
        item = self.current_item()
        if not item:
            return
        self.log(f"已跳过：{item['folder']}")
        self.advance_to_next_item()

    def advance_to_next_item(self):
        self.current_index += 1
        self.category_var.set(MAIN_CATEGORY)
        self.highlight_current()
        self.refresh_state()
        if self.current_index >= len(self.items):
            if self.work_mode:
                messagebox.showinfo(
                    APP_NAME,
                    "列表已全部做完。",
                    parent=self.work_panel if self.work_panel else self.root,
                )
                self.stop_work_mode(auto=True)
            return
        if self.auto_open_links_var.get():
            if self.work_mode:
                self.root.after(250, self.open_current_link_once)
            else:
                self.open_current_link_once()

    def copy_previous_to_current(self):
        if not self.items or self.current_index >= len(self.items):
            return
        if self.current_index <= 0:
            messagebox.showwarning(APP_NAME, "当前是第一条，没有上一个商品可以复制。")
            return

        previous = self.items[self.current_index - 1]
        current = self.items[self.current_index]
        output_dir = Path(self.output_dir_var.get()).expanduser()
        source_dir = output_dir / previous["folder"]
        target_dir = output_dir / current["folder"]

        if not source_dir.exists():
            messagebox.showwarning(APP_NAME, f"找不到上一个商品图片文件夹：\n{source_dir}")
            return
        if source_dir.resolve() == target_dir.resolve():
            messagebox.showwarning(APP_NAME, "上一个商品和当前商品的文件夹名相同，无法复制。")
            return

        try:
            copied_count, category_counts = self.copy_product_folder(source_dir, target_dir)
        except Exception as exc:
            self.status_var.set(f"复制失败：{exc}")
            self.log(f"复制上一个失败：{previous['folder']} -> {current['folder']}，{exc}")
            messagebox.showerror(APP_NAME, f"复制上一个失败：\n{exc}")
            return

        current["main"] = category_counts[MAIN_CATEGORY]
        current["detail"] = category_counts[DETAIL_CATEGORY]
        self.log(
            f"已复制上一个：{previous['folder']} -> {current['folder']}，共 {copied_count} 个文件"
        )
        self.advance_to_next_item()

    def copy_product_folder(self, source_dir: Path, target_dir: Path) -> tuple[int, dict]:
        copied_count = 0
        category_counts = {MAIN_CATEGORY: 0, DETAIL_CATEGORY: 0}
        for category in (MAIN_CATEGORY, DETAIL_CATEGORY):
            source_category = source_dir / category
            if not source_category.exists():
                continue
            for source_path in source_category.rglob("*"):
                relative_path = source_path.relative_to(source_dir)
                target_path = target_dir / relative_path
                if source_path.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                if target_path.exists() and not self.overwrite_var.get():
                    raise FileExistsError(f"文件已存在：{target_path}")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                copied_count += 1
                category_counts[category] += 1
        if copied_count == 0:
            raise FileNotFoundError(f"上一个商品没有可复制的 主图/详情 图片：{source_dir}")
        return copied_count, category_counts

    # ---- 工作模式 ----

    def open_watermark_window(self):
        if self.watermark_window is not None and self.watermark_window.winfo_exists():
            self.watermark_window.deiconify()
            self.watermark_window.lift()
            self.watermark_window.focus_force()
            return
        self.watermark_window = WatermarkWindow(self)

    def hotkey_pressed(self):
        if self.work_mode:
            if self.root.state() == "withdrawn":
                self.show_main_window()
            else:
                self.hide_main_window()
            return
        self.start_work_mode()

    def start_work_mode(self):
        if self.work_mode:
            return
        if not self.enabled_var.get():
            self.status_var.set("F9 已暂停。")
            return
        if not self.items:
            self.status_var.set("请先导入文件夹名。")
            self.root.bell()
            return
        if self.current_index >= len(self.items):
            self.status_var.set("列表已全部做完，请重置进度或导入新列表。")
            self.root.bell()
            return
        watch_dir = Path(self.watch_dir_var.get()).expanduser()
        if not watch_dir.is_dir():
            messagebox.showwarning(APP_NAME, f"监控目录不存在：\n{watch_dir}")
            return
        output_dir = Path(self.output_dir_var.get()).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showwarning(APP_NAME, f"输出目录无法创建：\n{exc}")
            return

        self.work_mode = True
        self.category_var.set(MAIN_CATEGORY)
        self.monitor.start(watch_dir)
        self.start_result_polling()
        self.mode_var.set("整理中")
        self.show_work_panel()
        self.log(f"已进入工作模式，监控目录：{watch_dir}")
        self.refresh_state()
        self.hide_main_window()
        if self.auto_open_links_var.get():
            self.root.after(250, self.open_current_link_once)

    def stop_work_mode(self, _event=None, auto: bool = False):
        if self.work_panel:
            panel = self.work_panel
            self.work_panel = None
            try:
                panel.destroy()
            except tk.TclError:
                pass
        was_active = self.work_mode
        self.work_mode = False
        self.monitor.stop()
        self.mode_var.set("已结束" if was_active else "待开始")
        self.root.deiconify()
        self.root.lift()
        self.refresh_state()
        if was_active:
            self.log("工作模式已结束。" if not auto else "列表已做完，工作模式自动结束。")

    def show_work_panel(self):
        if self.work_panel:
            try:
                self.work_panel.lift()
                return
            except tk.TclError:
                self.work_panel = None
        self.work_panel = WorkPanel(self)

    def show_main_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_main_window(self):
        if self.work_mode:
            self.root.withdraw()
            if self.work_panel:
                self.work_panel.lift()

    # ---- 下载归档 ----

    def start_result_polling(self):
        if self.polling_results:
            return
        self.polling_results = True
        self.root.after(250, self.poll_download_results)

    def poll_download_results(self):
        if not self.work_mode:
            self.polling_results = False
            return
        while True:
            try:
                path = self.monitor.results.get_nowait()
            except queue.Empty:
                break
            self.archive_download(path)
        self.root.after(250, self.poll_download_results)

    def get_counts(self) -> tuple[int, int]:
        try:
            main_count = max(0, int(self.main_count_var.get() or 0))
        except tk.TclError:
            main_count = 0
        try:
            detail_count = max(0, int(self.detail_count_var.get() or 0))
        except tk.TclError:
            detail_count = 0
        return main_count, detail_count

    def category_count(self, item, category: str) -> int:
        return item["main"] if category == MAIN_CATEGORY else item["detail"]

    def build_target_path(self, item, category: str, number: int) -> Path:
        prefix = safe_folder_name(self.prefix_var.get(), "pic")
        output_dir = Path(self.output_dir_var.get()).expanduser()
        filename = f"{prefix}{number}.jpg"
        return output_dir / item["folder"] / category / filename

    def next_free_target(self, item, category: str) -> tuple[Path, int]:
        number = self.category_count(item, category) + 1
        target = self.build_target_path(item, category, number)
        if not self.overwrite_var.get():
            while target.exists():
                number += 1
                target = self.build_target_path(item, category, number)
        return target, number

    def archive_download(self, source: Path, attempt: int = 1):
        if not self.work_mode:
            return
        item = self.current_item()
        if not item:
            self.log(f"检测到新图片但列表已做完，未归档：{source.name}")
            return

        category = self.category_var.get() or MAIN_CATEGORY
        target, number = self.next_free_target(item, category)
        quality = self.quality_var.get()

        try:
            convert_to_jpg(source, target, quality)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            if attempt == 1:
                # 文件可能还没写完或被占用，稍后重试一次。
                self.root.after(800, lambda: self.archive_download(source, attempt=2))
                return
            self.status_var.set(f"归档失败：{source.name}（{exc}）")
            self.log(f"归档失败：{source} -> {target}，{exc}")
            self.panel_status_var.set(f"归档失败：{source.name}")
            self.root.bell()
            return

        try:
            source.unlink()
        except OSError:
            self.log(f"原始下载文件删除失败（已归档成功）：{source}")

        if category == MAIN_CATEGORY:
            item["main"] = number
        else:
            item["detail"] = number
        self.undo_stack.append(
            {
                "index": self.current_index,
                "category": category,
                "target": str(target),
                "source_name": source.name,
            }
        )
        self.log(f"已归档：{source.name} -> {target}")
        self.panel_status_var.set(f"已归档 {category}/{target.name}")
        self.refresh_tree_row(self.current_index)
        self.refresh_state()

    def undo_last_archive(self):
        if not self.undo_stack:
            self.status_var.set("没有可撤销的归档记录。")
            self.panel_status_var.set("没有可撤销的归档记录")
            return
        record = self.undo_stack.pop()
        target = Path(record["target"])
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            self.log(f"撤销失败，无法删除：{target}，{exc}")
            messagebox.showerror(APP_NAME, f"撤销失败，无法删除：\n{target}\n{exc}")
            return

        index = int(record["index"])
        if 0 <= index < len(self.items):
            item = self.items[index]
            key = "main" if record["category"] == MAIN_CATEGORY else "detail"
            item[key] = max(0, item[key] - 1)
            self.refresh_tree_row(index)
        self.log(f"已撤销归档：{target.name}（来自 {record['source_name']}）")
        self.panel_status_var.set(f"已撤销：{record['category']}/{target.name}")
        self.refresh_state()

    # ---- 状态展示 ----

    def short_link_text(self, link: str) -> str:
        if not link:
            return "-"
        match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", link)
        if match:
            return match.group(1)
        return link[:42] + ("..." if len(link) > 42 else "")

    def refresh_state(self):
        if hasattr(self, "start_button"):
            self.start_button.configure(state="disabled" if self.work_mode else "normal")
            self.stop_button.configure(state="normal" if self.work_mode else "disabled")
        self.highlight_current()

        item = self.current_item()
        if not item:
            self.current_var.set("全部完成" if self.items else "-")
            self.next_path_var.set("-")
            self.panel_current_var.set("全部完成" if self.items else "-")
            self.panel_progress_var.set("进度：全部完成" if self.items else "进度：-")
            self.panel_link_var.set("链接：-")
            if self.items:
                self.status_var.set("列表已全部做完。")
            return

        main_count, detail_count = self.get_counts()
        category = self.category_var.get() or MAIN_CATEGORY
        target, _number = self.next_free_target(item, category)

        self.current_var.set(item["folder"])
        self.next_path_var.set(str(target))
        progress = (
            f"主图 {item['main']}/{main_count} · 详情 {item['detail']}/{detail_count}"
            f"　正在归档：{category}"
        )
        self.panel_current_var.set(item["folder"])
        self.panel_progress_var.set(f"进度：{progress}")
        link_state = "已打开" if item.get("opened") else "未打开"
        link_text = self.short_link_text(item.get("link", ""))
        self.panel_link_var.set(f"链接：{link_state} {link_text}" if item.get("link") else "链接：无")
        self.status_var.set(
            f"当前：{item['folder']}，下一张保存为 {category}/{target.name}"
        )

    def on_close(self):
        try:
            self.stop_work_mode()
            self.monitor.stop()
            self.hotkey.uninstall()
        finally:
            self.root.destroy()

    def run(self):
        self.log("程序已启动。")
        self.root.mainloop()


if __name__ == "__main__":
    try:
        PictureOrganizerApp().run()
    except Exception:
        write_error_log(traceback.format_exc())
