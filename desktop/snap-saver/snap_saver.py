"""截图存图助手

工作流：
1. 导入「A列名称 + B列链接」列表，点开始 → 自动用系统默认浏览器打开当前行链接
2. 在网页里按住 Ctrl + 鼠标左键拖框选区 → 松开自动截图保存到 输出/名称/主图(或详情)/
3. 设定主图、详情张数：主图截够自动切详情，详情截够自动切下一行并打开下一个链接
4. 全部截完选择修复类型并点「AI 智能修复」：AI 遍历本次截图，挑出疑似需要处理的让你确认/移除
5. 无需账号注册，软件自动读取本机 MAC 作为软件编号；新编号默认 50 张图片处理额度
6. 确认后按成功处理张数扣减额度，结果覆盖原图，原图备份

依赖：Pillow、openpyxl（可选，读 xlsx 用）。AI 检测和图片修复走服务器接口，
服务器使用已配置的阿里云百炼模型；客户端不保存阿里 API Key。
"""

import base64
import csv
import ctypes
import io
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
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageOps


APP_NAME = "智能截图软件"
DEFAULT_SERVER_URL = "https://tools.haobanfa.online"
APP_VERSION = "V1.0"

COLOR_BG = "#f5faf7"
COLOR_CARD = "#ffffff"
COLOR_TEXT = "#111827"
COLOR_MUTED = "#64748b"
COLOR_BORDER = "#dbe7df"
COLOR_GREEN = "#079a48"
COLOR_GREEN_DARK = "#04783a"
COLOR_GREEN_SOFT = "#eefbf3"
COLOR_CYAN = "#06b6d4"

MAIN_CATEGORY = "主图"
DETAIL_CATEGORY = "详情"
BACKUP_DIR_NAME = "_含水印原图"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}

# 服务器端会用这些阿里云百炼模型；客户端默认通过服务器接口调用。
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"
WATERMARK_MODEL = "wanx2.1-imageedit"
DETECT_MODEL = "qwen-vl-max-latest"
WATERMARK_MIN_SIDE = 512
WATERMARK_MAX_SIDE = 4096
WATERMARK_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_REPAIR_MODE = "watermark"
REPAIR_MODES = (
    ("watermark", "去除水印"),
    ("text_sticker", "去除文字贴纸"),
    ("marketing", "去除营销广告"),
    ("clean", "图片清爽化"),
    ("all", "全部去除"),
)
REPAIR_LABEL_TO_KEY = {label: key for key, label in REPAIR_MODES}
REPAIR_KEY_TO_LABEL = {key: label for key, label in REPAIR_MODES}

# 全局低级鼠标钩子常量
WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
VK_CONTROL = 0x11

try:
    import openpyxl
except Exception:  # pragma: no cover - 没装也能跑（只是不能读 xlsx）
    openpyxl = None


# ---------------- 基础工具 ----------------

def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def error_log_path() -> Path:
    return app_dir() / "截图存图助手错误日志.txt"


def write_error_log(message: str):
    try:
        with error_log_path().open("a", encoding="utf-8") as file:
            file.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def config_path() -> Path:
    return app_dir() / "截图存图助手配置.json"


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
        config_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        write_error_log(f"保存配置失败：{exc}")


def normalize_repair_mode(value: str) -> str:
    text = str(value or "").strip()
    if text in REPAIR_KEY_TO_LABEL:
        return text
    return REPAIR_LABEL_TO_KEY.get(text, DEFAULT_REPAIR_MODE)


def repair_mode_label(value: str) -> str:
    return REPAIR_KEY_TO_LABEL.get(normalize_repair_mode(value), REPAIR_KEY_TO_LABEL[DEFAULT_REPAIR_MODE])


def safe_folder_name(value: str, fallback: str) -> str:
    name = str(value).strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")
    return name or fallback


def try_read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


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
    if link_text.startswith("http"):
        return False
    header_words = {"名称", "商品名称", "标题", "name", "title", "链接", "网址", "link", "url", "地址"}
    return name_text in header_words or link_text in header_words


def add_import_row(rows: list, raw_name, raw_link, row_index: int):
    name = "" if raw_name is None else str(raw_name).strip()
    link = clean_link(raw_link)
    if not name and not link:
        return
    if row_index == 1 and looks_like_header(name, raw_link):
        return
    rows.append((name or f"第{row_index}行", link))


def read_import_rows(path: Path) -> list:
    path = Path(path)
    suffix = path.suffix.lower()
    rows: list = []

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
        reader = csv.reader(try_read_text_file(path).splitlines())
        for row_index, row in enumerate(reader, start=1):
            if not row:
                continue
            name = row[0] if len(row) > 0 else ""
            link = row[1] if len(row) > 1 else ""
            add_import_row(rows, name, link, row_index)
        return rows

    for row_index, line in enumerate(try_read_text_file(path).splitlines(), start=1):
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


def parse_clipboard_rows(text: str) -> list:
    rows: list = []
    for row_index, line in enumerate(str(text or "").splitlines(), start=1):
        if not line.strip():
            continue
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


def convert_to_jpg(source: Path, target: Path, quality: int):
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


# ---------------- DashScope AI ----------------

class DashScopeError(RuntimeError):
    pass


class ServerApiError(RuntimeError):
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


def _encode_multipart(fields: list, filename: str, file_bytes: bytes, field_name: str = "file"):
    boundary = f"----SnapSaver{uuid.uuid4().hex}"
    chunks = []
    for name, value in fields:
        chunks.append(
            (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
             f"{value}\r\n").encode("utf-8")
        )
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.append(
        (f"--{boundary}\r\n"
         f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
         f"Content-Type: {mime}\r\n\r\n").encode("utf-8")
    )
    chunks.append(file_bytes)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def normalize_server_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    if not url:
        url = DEFAULT_SERVER_URL
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url.rstrip("/")


def _server_error_from_body(body: str, fallback: str) -> str:
    try:
        data = json.loads(body)
        message = data.get("message") or data.get("error") or fallback
        if isinstance(data.get("errors"), dict):
            first = next(iter(data["errors"].values()), None)
            if isinstance(first, list) and first:
                message = first[0]
        return str(message)[:300]
    except Exception:
        text = re.sub(r"\s+", " ", body or "").strip()
        return (text or fallback)[:300]


def local_software_id() -> str:
    node = uuid.getnode()
    hex_value = f"{node:012X}"[-12:]
    return "-".join(hex_value[index:index + 2] for index in range(0, 12, 2))


def server_register_device(server_url: str, software_id: str) -> dict:
    payload = json.dumps({
        "software_id": software_id,
        "app": "snap-saver",
        "version": APP_VERSION,
    }).encode("utf-8")
    request = urllib.request.Request(
        normalize_server_url(server_url) + "/api/desktop/device/register", data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ServerApiError(_server_error_from_body(body, f"软件编号登记失败：HTTP {exc.code}"))
    except urllib.error.URLError as exc:
        raise ServerApiError(f"连接服务器失败：{exc.reason}")
    token = str(data.get("token") or "").strip()
    if not token:
        raise ServerApiError("服务器登记成功但没有返回 token。")
    return data


def server_device_status(server_url: str, token: str) -> dict:
    if not token:
        raise ServerApiError("请先登记软件编号。")
    request = urllib.request.Request(normalize_server_url(server_url) + "/api/desktop/device/status", method="GET")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ServerApiError(_server_error_from_body(body, f"额度同步失败：HTTP {exc.code}"))
    except urllib.error.URLError as exc:
        raise ServerApiError(f"连接服务器失败：{exc.reason}")


def _server_upload(server_url: str, token: str, path: str, image_path: Path,
                   timeout: int, expect_json: bool, fields: list | None = None):
    if not token:
        raise ServerApiError("请先登记软件编号。")
    body, content_type = _encode_multipart(fields or [], image_path.name, image_path.read_bytes(), "image")
    request = urllib.request.Request(normalize_server_url(server_url) + path, data=body, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", content_type)
    request.add_header("Accept", "application/json" if expect_json else "image/jpeg")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            if expect_json:
                return json.loads(data.decode("utf-8"))
            return data
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ServerApiError(_server_error_from_body(body, f"服务器请求失败：HTTP {exc.code}"))
    except urllib.error.URLError as exc:
        raise ServerApiError(f"连接服务器失败：{exc.reason}")


def prepare_detect_input(path: Path, temp_dir: Path) -> Path:
    with Image.open(path) as image:
        image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
        longest = max(image.size)
        if longest > 1024:
            scale = 1024 / longest
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
        target = temp_dir / f"{uuid.uuid4().hex}.jpg"
        image.save(target, "JPEG", quality=80, optimize=True)
        return target


def server_detect_watermark(server_url: str, token: str, path: Path,
                            repair_mode: str, stop_event: threading.Event) -> dict:
    if stop_event.is_set():
        raise ServerApiError("已停止。")
    with tempfile.TemporaryDirectory(prefix="snap_detect_") as tmp:
        prepared = prepare_detect_input(path, Path(tmp))
        response = _server_upload(
            server_url, token, "/api/desktop/watermark/detect", prepared, timeout=90, expect_json=True,
            fields=[("mode", normalize_repair_mode(repair_mode))])
    needs_repair = response.get("needs_repair")
    if needs_repair is None:
        needs_repair = response.get("has_watermark")
    return {
        "needs_repair": bool(needs_repair),
        "has_watermark": bool(needs_repair),
        "note": str(response.get("note") or "").strip()[:120],
    }


def server_remove_watermark_to(server_url: str, token: str, source: Path, target: Path,
                               temp_dir: Path, repair_mode: str, stop_event: threading.Event):
    if stop_event.is_set():
        raise ServerApiError("已停止。")
    prepared = prepare_watermark_input(source, temp_dir)
    try:
        data = _server_upload(
            server_url, token, "/api/desktop/watermark/remove", prepared, timeout=420, expect_json=False,
            fields=[("mode", normalize_repair_mode(repair_mode))])
    finally:
        try:
            prepared.unlink()
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_out = temp_dir / f"{uuid.uuid4().hex}.result"
    temp_out.write_bytes(data)
    try:
        convert_to_jpg(temp_out, target, quality=95)
    finally:
        try:
            temp_out.unlink()
        except OSError:
            pass


def ds_upload_image(api_key: str, path: Path) -> str:
    policy = _ds_request(
        f"{DASHSCOPE_BASE}/api/v1/uploads?action=getPolicy&model={WATERMARK_MODEL}", api_key
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
        api_key, payload,
        headers={"X-DashScope-Async": "enable", "X-DashScope-OssResourceResolve": "enable"},
    )
    task_id = (response.get("output") or {}).get("task_id")
    if not task_id:
        raise DashScopeError("创建去水印任务失败，请稍后重试。")
    return str(task_id)


def ds_wait_task(api_key: str, task_id: str, stop_event: threading.Event, timeout: float = 300.0) -> str:
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
                str(output.get("code") or status), str(output.get("message") or "任务失败")))
        stop_event.wait(2)
    raise DashScopeError("任务超时（5 分钟）。")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("` \n\r\t")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}
    return {}


def ds_detect_watermark(api_key: str, path: Path, stop_event: threading.Event) -> dict:
    if stop_event.is_set():
        raise DashScopeError("已停止。")
    with Image.open(path) as image:
        image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
        longest = max(image.size)
        if longest > 1024:
            scale = 1024 / longest
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=80)
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    payload = {
        "model": DETECT_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "判断这张图片里是否有水印（包括文字水印、半透明logo、平台角标、"
                    "网址、店铺名、防盗文字等）。只输出 JSON，格式："
                    '{"has_watermark": true 或 false, "note": "水印内容或位置的简短描述"}。')},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "temperature": 0.0,
    }
    response = _ds_request(f"{DASHSCOPE_BASE}/compatible-mode/v1/chat/completions", api_key, payload, timeout=60)
    try:
        content = response["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    except Exception:
        raise DashScopeError("检测返回格式异常。")
    data = _extract_json(str(content))
    return {"has_watermark": bool(data.get("has_watermark")), "note": str(data.get("note") or "").strip()[:80]}


def ds_download_bytes(url: str) -> bytes:
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as response:
            return response.read()
    except Exception as exc:
        raise DashScopeError(f"下载结果图失败：{exc}")


def prepare_watermark_input(path: Path, temp_dir: Path) -> Path:
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
                (max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
        target = temp_dir / f"{uuid.uuid4().hex}.jpg"
        for quality in (92, 85, 75):
            image.save(target, "JPEG", quality=quality, optimize=True)
            if target.stat().st_size <= WATERMARK_MAX_BYTES:
                break
        return target


def remove_watermark_to(api_key: str, source: Path, target: Path, temp_dir: Path, stop_event: threading.Event):
    prepared = prepare_watermark_input(source, temp_dir)
    try:
        oss_url = ds_upload_image(api_key, prepared)
        task_id = ds_create_watermark_task(api_key, oss_url)
        result_url = ds_wait_task(api_key, task_id, stop_event)
        data = ds_download_bytes(result_url)
    finally:
        try:
            prepared.unlink()
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_out = temp_dir / f"{uuid.uuid4().hex}.result"
    temp_out.write_bytes(data)
    try:
        convert_to_jpg(temp_out, target, 95)
    finally:
        try:
            temp_out.unlink()
        except OSError:
            pass


# ---------------- 全局鼠标钩子（独立线程 + Win32 消息循环） ----------------

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT), ("mouseData", ctypes.c_uint32),
        ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32), ("pt", _POINT),
    ]


class CtrlDragHook:
    """全局低级鼠标钩子，检测「按住 Ctrl + 左键拖动」手势。

    关键：钩子必须装在一个跑着 Win32 消息循环的线程里，回调才会被触发——
    这就是之前挂在 Tkinter 上「没反应」的根因。这里用独立线程 + GetMessage。
    """

    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.hook = None
        self.thread = None
        self.thread_id = 0
        self.ready = threading.Event()
        self.stop_requested = False
        self.hook_lock = threading.Lock()
        self.last_error = ""
        self.enabled = True
        self.capturing = False
        self.events: queue.Queue = queue.Queue()

        self.HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p)
        self._proc = self.HOOKPROC(self._callback)

        u = self.user32
        u.SetWindowsHookExW.restype = ctypes.c_void_p
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, self.HOOKPROC, ctypes.c_void_p, ctypes.c_uint]
        u.CallNextHookEx.restype = ctypes.c_ssize_t
        u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p]
        u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        u.UnhookWindowsHookEx.restype = ctypes.c_bool
        u.GetAsyncKeyState.restype = ctypes.c_short
        u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u.GetMessageW.restype = ctypes.c_int
        u.GetMessageW.argtypes = [ctypes.POINTER(_MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        u.PeekMessageW.restype = ctypes.c_bool
        u.PeekMessageW.argtypes = [ctypes.POINTER(_MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        u.TranslateMessage.restype = ctypes.c_bool
        u.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
        u.DispatchMessageW.restype = ctypes.c_ssize_t
        u.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
        u.PostThreadMessageW.restype = ctypes.c_bool
        u.PostThreadMessageW.argtypes = [ctypes.c_uint32, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        self.kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        self.kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        self.kernel32.GetCurrentThreadId.restype = ctypes.c_uint32

    def install(self) -> bool:
        if self.thread and self.thread.is_alive() and self.hook:
            return True
        self.ready.clear()
        self.stop_requested = False
        self.last_error = ""
        self.thread = threading.Thread(target=self._thread_main, name="ctrl-drag-hook", daemon=True)
        self.thread.start()
        if not self.ready.wait(2.0):
            self.last_error = "钩子线程启动超时"
            self.stop_requested = True
            if self.thread_id:
                self.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
            return False
        return bool(self.hook)

    def uninstall(self):
        self.stop_requested = True
        if self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self.thread and self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.0)
        with self.hook_lock:
            if self.hook:
                self.user32.UnhookWindowsHookEx(self.hook)
                self.hook = None
        self.thread = None
        self.thread_id = 0
        self.capturing = False

    def _thread_main(self):
        msg = _MSG()
        self.thread_id = self.kernel32.GetCurrentThreadId()
        # 先建立线程消息队列
        self.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        hmod = self.kernel32.GetModuleHandleW(None)
        hook = self.user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, hmod, 0)
        if not hook:
            self.last_error = f"SetWindowsHookExW 失败：{ctypes.get_last_error()}"
            self.ready.set()
            return
        with self.hook_lock:
            self.hook = hook
        self.ready.set()
        try:
            while not self.stop_requested:
                result = self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0 or result == -1:
                    break
                self.user32.TranslateMessage(ctypes.byref(msg))
                self.user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            with self.hook_lock:
                if self.hook:
                    self.user32.UnhookWindowsHookEx(self.hook)
                    self.hook = None
            self.capturing = False
            self.thread_id = 0

    def _ctrl_down(self) -> bool:
        return bool(self.user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)

    def _callback(self, n_code, w_param, l_param):
        if n_code >= 0 and self.enabled:
            try:
                msg = int(w_param)
                info = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                x, y = int(info.pt.x), int(info.pt.y)
                if msg == WM_LBUTTONDOWN:
                    if self._ctrl_down():
                        self.capturing = True
                        self.events.put(("start", x, y))
                        return 1  # 吞掉，避免网页收到这次点击
                elif msg == WM_MOUSEMOVE:
                    if self.capturing:
                        self.events.put(("move", x, y))
                elif msg == WM_LBUTTONUP:
                    if self.capturing:
                        self.capturing = False
                        self.events.put(("finish", x, y))
                        return 1
            except Exception:
                pass
        return self.user32.CallNextHookEx(None, n_code, w_param, l_param)


class SelectionBoxWindow(tk.Toplevel):
    """Ctrl 拖动时的全屏选框反馈窗口，坐标用屏幕物理坐标。"""

    def __init__(self, root):
        super().__init__(root)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.25)
        self.configure(bg="#0b0f14", cursor="crosshair")
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+0+0")
        self.canvas = tk.Canvas(self, bg="#0b0f14", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.rect = None
        self.start = (0, 0)
        self.visible = False
        self.withdraw()

    def begin(self, x, y):
        self.start = (x, y)
        self.canvas.delete("all")
        self.rect = self.canvas.create_rectangle(x, y, x, y, outline=COLOR_CYAN, width=2, dash=(6, 3))
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.visible = True

    def update_to(self, x, y):
        if self.rect:
            self.canvas.coords(self.rect, self.start[0], self.start[1], x, y)

    def end(self):
        self.visible = False
        self.withdraw()


# ---------------- 工作浮窗 ----------------

class FloatPanel(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner.root)
        self.owner = owner
        self.title("智能截图软件 V1.0")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)
        self.protocol("WM_DELETE_WINDOW", owner.stop_work)

        frame = tk.Frame(self, bg=COLOR_CARD, padx=16, pady=14,
                         highlightbackground="#c9d7cf", highlightthickness=1)
        frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        frame.columnconfigure(0, weight=1)

        title_row = tk.Frame(frame, bg=COLOR_CARD)
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.columnconfigure(0, weight=1)
        tk.Label(title_row, text=f"智能截图软件 {APP_VERSION}", bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Microsoft YaHei UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        tk.Button(title_row, text="×", command=owner.stop_work, bd=0, bg=COLOR_CARD,
                  fg="#334155", activebackground="#f1f5f9",
                  font=("Microsoft YaHei UI", 12)).grid(row=0, column=1)

        tk.Label(frame, textvariable=owner.panel_name_var, bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Microsoft YaHei UI", 11, "bold"), anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(12, 2))
        tk.Label(frame, textvariable=owner.panel_progress_var, bg=COLOR_CARD, fg=COLOR_MUTED,
                 font=("Microsoft YaHei UI", 9), anchor="w").grid(row=2, column=0, sticky="ew", pady=(0, 12))

        self.main_btn = self._panel_button(frame, "▣  主图", lambda: owner.set_category(MAIN_CATEGORY), 3)
        self.detail_btn = self._panel_button(frame, "☰  详情", lambda: owner.set_category(DETAIL_CATEGORY), 4)
        self.next_btn = self._panel_button(frame, "↓  下一行", owner.next_row_manual, 5)
        self.copy_btn = self._panel_button(frame, "↶  复制上一行", owner.copy_previous, 6)
        self.reopen_btn = self._panel_button(frame, "↻  重开链接", owner.open_current_link, 7)

        tk.Button(frame, text="⌂  显示主程序", command=owner.show_main,
                  bg=COLOR_GREEN, fg="#ffffff", activebackground=COLOR_GREEN_DARK,
                  activeforeground="#ffffff", bd=0, relief="flat", cursor="hand2",
                  font=("Microsoft YaHei UI", 12, "bold"), padx=12, pady=12).grid(
            row=8, column=0, sticky="ew", pady=(10, 0))

        tk.Label(frame, text="按住 Ctrl + 鼠标拖动框选截图", bg=COLOR_CARD, fg=COLOR_MUTED,
                 font=("Microsoft YaHei UI", 9), anchor="w").grid(row=9, column=0, sticky="ew", pady=(12, 0))

        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        self.geometry(f"+{screen_w - self.winfo_width() - 40}+60")
        self.refresh_category()

    def _panel_button(self, parent, text, command, row):
        button = tk.Button(parent, text=text, command=command, anchor="w",
                           bg="#ffffff", fg=COLOR_TEXT, activebackground="#f8fafc",
                           activeforeground=COLOR_TEXT, bd=0, relief="flat", cursor="hand2",
                           highlightbackground="#d7ded9", highlightthickness=1,
                           font=("Microsoft YaHei UI", 12), padx=16, pady=10)
        button.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        return button

    def refresh_category(self):
        active = self.owner.category_var.get()
        for btn, name in ((self.main_btn, MAIN_CATEGORY), (self.detail_btn, DETAIL_CATEGORY)):
            try:
                if name == active:
                    btn.configure(bg=COLOR_GREEN_SOFT, fg=COLOR_GREEN, highlightbackground=COLOR_GREEN)
                else:
                    btn.configure(bg="#ffffff", fg=COLOR_TEXT, highlightbackground="#d7ded9")
            except tk.TclError:
                pass


# ---------------- 图片修复确认对话框 ----------------

class ConfirmDialog(tk.Toplevel):
    """列出疑似需要修复的截图，用户移除不需要处理的，剩下的确认处理。"""

    def __init__(self, owner, candidates: list, mode_label: str):
        super().__init__(owner.root)
        self.owner = owner
        self.mode_label = mode_label
        self.title(f"确认{mode_label}")
        self.geometry("640x520")
        self.minsize(560, 440)
        self.transient(owner.root)
        self.result: list | None = None
        self.items = list(candidates)  # [{path, name, note}]

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text=f"下面是 AI 认为需要「{mode_label}」的图。选中不需要处理的点「移除选中」，"
                             "剩下的会批量修复。双击可打开图片查看。",
                  style="Hint.TLabel", wraplength=600).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))

        table = ttk.Frame(self)
        table.grid(row=1, column=0, sticky="nsew", padx=14)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("name", "file", "note")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("name", text="商品")
        self.tree.heading("file", text="文件")
        self.tree.heading("note", text="检测原因")
        self.tree.column("name", width=160, anchor="w")
        self.tree.column("file", width=150, anchor="w")
        self.tree.column("note", width=260, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._open_image)

        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 0))
        bar.columnconfigure(2, weight=1)
        ttk.Button(bar, text="移除选中", command=self._remove_selected).grid(row=0, column=0)
        ttk.Button(bar, text="打开图片", command=self._open_image).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(bar, textvariable=self._make_cost_var(), style="Hint.TLabel").grid(row=0, column=2, sticky="e")

        action = ttk.Frame(self)
        action.grid(row=3, column=0, sticky="ew", padx=14, pady=12)
        action.columnconfigure(0, weight=1)
        ttk.Button(action, text="取消", command=self._cancel).grid(row=0, column=1)
        ttk.Button(action, text="确认修复", style="Accent.TButton", command=self._confirm).grid(
            row=0, column=2, padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.refresh()

    def _make_cost_var(self):
        self.cost_var = tk.StringVar(value="")
        return self.cost_var

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(self.items):
            self.tree.insert("", "end", iid=str(index),
                             values=(item["name"], item["path"].name, item["note"] or "（未给出描述）"))
        count = len(self.items)
        self.cost_var.set(f"将处理 {count} 张，扣除 {count} 张图片处理额度")

    def _remove_selected(self):
        selected = {int(iid) for iid in self.tree.selection()}
        if not selected:
            return
        self.items = [item for index, item in enumerate(self.items) if index not in selected]
        self.refresh()

    def _open_image(self, _event=None):
        selection = self.tree.selection()
        index = int(selection[0]) if selection else 0
        if 0 <= index < len(self.items):
            try:
                os.startfile(str(self.items[index]["path"]))
            except Exception as exc:
                messagebox.showinfo(APP_NAME, f"无法打开图片：{exc}", parent=self)

    def _confirm(self):
        if not self.items:
            messagebox.showinfo(APP_NAME, "没有要处理的图片了。", parent=self)
            return
        count = len(self.items)
        if not messagebox.askyesno(
                APP_NAME,
                f"确定用「{self.mode_label}」处理 {count} 张图吗？\n\n"
                f"成功处理每张扣 1 张图片额度，本次最多扣除 {count} 张。", parent=self):
            return
        self.result = [item["path"] for item in self.items]
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------- 主程序 ----------------

class SnapSaverApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1120x740")
        self.root.minsize(980, 640)

        config = load_config()
        saved_out = config.get("output_dir")

        self.rows: list = []          # [{name, link, status}]
        self.current_index = 0
        self.work_mode = False
        self.captures: list = []      # 本次所有截图 [{path, row_index, name, category}]
        self.float_panel: FloatPanel | None = None
        self.selection_box: SelectionBoxWindow | None = None
        self.hook = CtrlDragHook()
        self.gesture_start = None
        self.grabbing = False
        self.hook_polling = False
        self.busy = False
        self.stop_event = threading.Event()
        self.temp_dir = None
        self.ai_thread = None
        self.ai_events: queue.Queue = queue.Queue()

        self.server_url_var = tk.StringVar(value=str(config.get("server_url") or os.environ.get("HAOBANFA_SERVER_URL", DEFAULT_SERVER_URL)))
        self.software_id_var = tk.StringVar(value=str(config.get("software_id") or local_software_id()))
        self.server_token = str(config.get("server_token") or os.environ.get("HAOBANFA_TOKEN", "")).strip()
        self.output_dir_var = tk.StringVar(value=str(Path(saved_out) if saved_out else app_dir() / "存图结果"))
        self.main_count_var = tk.IntVar(value=int(config.get("main_count", 1) or 1))
        self.detail_count_var = tk.IntVar(value=int(config.get("detail_count", 3) or 3))
        self.prefix_var = tk.StringVar(value=str(config.get("prefix", "pic")))
        self.quality_var = tk.IntVar(value=int(config.get("quality", 95) or 95))
        self.auto_open_var = tk.BooleanVar(value=bool(config.get("auto_open", True)))
        self.repair_mode_var = tk.StringVar(value=repair_mode_label(str(config.get("repair_mode") or DEFAULT_REPAIR_MODE)))
        self.category_var = tk.StringVar(value=MAIN_CATEGORY)

        self.status_var = tk.StringVar(value="导入「名称+链接」列表，点开始即可。")
        self.panel_name_var = tk.StringVar(value="-")
        self.panel_progress_var = tk.StringVar(value="主图 0/0 · 详情 0/0")
        self.hook_state_var = tk.StringVar(value="")
        self.device_state_var = tk.StringVar(value="设备：未登记" if not self.server_token else "设备：已登记")
        self.quota_var = tk.StringVar(value="图片额度：未同步")

        self.configure_style()
        self.build_ui()
        self.root.report_callback_exception = self.report_exception
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ----- 样式/UI -----

    def configure_style(self):
        self.root.configure(bg=COLOR_BG)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Microsoft YaHei UI", 10), background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_CARD)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT)
        style.configure("TButton", padding=(12, 7), background="#ffffff", foreground=COLOR_TEXT, bordercolor=COLOR_BORDER)
        style.configure("Accent.TButton", padding=(14, 8), background=COLOR_GREEN, foreground="#ffffff",
                        bordercolor=COLOR_GREEN, font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", COLOR_GREEN_DARK)], foreground=[("active", "#ffffff")])
        style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT,
                        font=("Microsoft YaHei UI", 28, "bold"))
        style.configure("Subtitle.TLabel", background=COLOR_BG, foreground="#334155",
                        font=("Microsoft YaHei UI", 14))
        style.configure("Hint.TLabel", foreground=COLOR_MUTED, background=COLOR_BG)
        style.configure("CardHint.TLabel", foreground=COLOR_MUTED, background=COLOR_CARD)
        style.configure("Status.TLabel", foreground=COLOR_GREEN_DARK, background=COLOR_BG)
        style.configure("TLabelframe", background=COLOR_CARD, bordercolor=COLOR_BORDER, relief="solid")
        style.configure("TLabelframe.Label", background=COLOR_CARD, foreground=COLOR_TEXT,
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Treeview", rowheight=30, background="#ffffff", fieldbackground="#ffffff",
                        foreground=COLOR_TEXT, bordercolor=COLOR_BORDER)
        style.configure("Treeview.Heading", background="#f8fafc", foreground="#334155",
                        font=("Microsoft YaHei UI", 10, "bold"))

    def report_exception(self, exc_type, exc_value, exc_tb):
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
        root.rowconfigure(3, weight=1)

        header = ttk.Frame(root, padding=(28, 24, 28, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title_line = ttk.Frame(header)
        title_line.grid(row=0, column=0, sticky="ew")
        title_line.columnconfigure(0, weight=1)
        ttk.Label(title_line, text=f"智能截图软件  {APP_VERSION}", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(title_line, textvariable=self.hook_state_var, style="Hint.TLabel").grid(
            row=0, column=1, sticky="e")

        ttk.Label(header, text="高效截图 · 智能识别 · 一键导出", style="Subtitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(header, text="导入名称+链接后自动打开网页；按住 Ctrl 拖动鼠标框选，松开自动保存；截完后选择修复类型，AI 先筛图再批量修复。",
                  style="Hint.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))

        chips = ttk.Frame(header)
        chips.grid(row=3, column=0, sticky="w", pady=(18, 0))
        for col, (icon, title, desc) in enumerate((
                ("▣", "智能识别", "自动检测需修复图片"),
                ("↯", "高效操作", "一键截图快速采集"),
                ("✓", "便捷管理", "分类保存轻松查找"),
        )):
            chip = tk.Frame(chips, bg=COLOR_CARD, padx=12, pady=8,
                            highlightbackground=COLOR_BORDER, highlightthickness=1)
            chip.grid(row=0, column=col, padx=(0, 12))
            tk.Label(chip, text=icon, bg=COLOR_CARD, fg=COLOR_GREEN,
                     font=("Microsoft YaHei UI", 18, "bold")).grid(row=0, column=0, rowspan=2, padx=(0, 8))
            tk.Label(chip, text=title, bg=COLOR_CARD, fg=COLOR_GREEN,
                     font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=1, sticky="w")
            tk.Label(chip, text=desc, bg=COLOR_CARD, fg=COLOR_MUTED,
                     font=("Microsoft YaHei UI", 8)).grid(row=1, column=1, sticky="w")

        # 设置区
        cfg = ttk.LabelFrame(root, text="运行设置", padding=(18, 12))
        cfg.grid(row=1, column=0, sticky="ew", padx=28, pady=(8, 10))
        cfg.columnconfigure(1, weight=1)

        ttk.Label(cfg, text="服务器").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(cfg, textvariable=self.server_url_var).grid(row=0, column=1, columnspan=3, sticky="ew")
        ttk.Label(cfg, textvariable=self.device_state_var, style="Hint.TLabel").grid(row=0, column=4, sticky="e", padx=(8, 0))

        ttk.Label(cfg, text="软件编号").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self.software_id_entry = ttk.Entry(cfg, textvariable=self.software_id_var, state="readonly")
        self.software_id_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(cfg, text="复制编号", command=self.copy_software_id).grid(row=1, column=3, padx=(8, 0), pady=(8, 0))
        ttk.Button(cfg, text="同步额度", command=self.sync_quota).grid(row=1, column=4, padx=(8, 0), pady=(8, 0))
        ttk.Label(cfg, textvariable=self.quota_var, style="Hint.TLabel").grid(
            row=2, column=1, columnspan=4, sticky="w", pady=(6, 0))

        ttk.Label(cfg, text="输出目录").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(cfg, textvariable=self.output_dir_var).grid(row=3, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(cfg, text="选择", command=self.choose_output).grid(row=3, column=3, padx=(8, 0), pady=(8, 0))
        ttk.Button(cfg, text="打开", command=self.open_output).grid(row=3, column=4, padx=(8, 0), pady=(8, 0))

        nums = ttk.Frame(cfg)
        nums.grid(row=4, column=0, columnspan=5, sticky="w", pady=(10, 0))
        ttk.Label(nums, text="主图").grid(row=0, column=0, padx=(0, 6))
        ttk.Spinbox(nums, from_=0, to=99, width=5, textvariable=self.main_count_var).grid(row=0, column=1)
        ttk.Label(nums, text="详情").grid(row=0, column=2, padx=(14, 6))
        ttk.Spinbox(nums, from_=0, to=99, width=5, textvariable=self.detail_count_var).grid(row=0, column=3)
        ttk.Label(nums, text="（截够自动切换 / 下一行）", style="Hint.TLabel").grid(row=0, column=4, padx=(8, 0))
        ttk.Label(nums, text="文件名前缀").grid(row=0, column=5, padx=(20, 6))
        ttk.Entry(nums, width=8, textvariable=self.prefix_var).grid(row=0, column=6)
        ttk.Label(nums, text="JPG质量").grid(row=0, column=7, padx=(14, 6))
        ttk.Spinbox(nums, from_=30, to=100, width=5, textvariable=self.quality_var).grid(row=0, column=8)
        ttk.Checkbutton(nums, text="切行自动开链接", variable=self.auto_open_var).grid(row=0, column=9, padx=(16, 0))

        # 工具条
        toolbar = ttk.Frame(root, padding=(28, 0, 28, 10))
        toolbar.grid(row=2, column=0, sticky="ew")
        ttk.Button(toolbar, text="导入文件", command=self.import_file).grid(row=0, column=0)
        ttk.Button(toolbar, text="从剪贴板导入", command=self.import_clipboard).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(toolbar, text="清空列表", command=self.clear_rows).grid(row=0, column=2, padx=(8, 0))
        self.start_button = ttk.Button(toolbar, text="开始截图", style="Accent.TButton", command=self.start_work)
        self.start_button.grid(row=0, column=3, padx=(24, 0))
        self.stop_button = ttk.Button(toolbar, text="结束截图", command=self.stop_work, state="disabled")
        self.stop_button.grid(row=0, column=4, padx=(8, 0))
        ttk.Label(toolbar, text="修复类型").grid(row=0, column=5, padx=(24, 6))
        self.repair_mode_combo = ttk.Combobox(
            toolbar,
            textvariable=self.repair_mode_var,
            values=[label for _, label in REPAIR_MODES],
            state="readonly",
            width=12,
        )
        self.repair_mode_combo.grid(row=0, column=6)
        self.repair_button = ttk.Button(toolbar, text="AI 智能修复", command=self.ai_repair)
        self.repair_button.grid(row=0, column=7, padx=(8, 0))

        # 列表 + 日志
        body = ttk.Panedwindow(root, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew", padx=28, pady=(0, 10))
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="商品截图进度", font=("Microsoft YaHei UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6))

        columns = ("index", "name", "link", "main", "detail", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for key, text, width, anchor in (
            ("index", "#", 44, "center"), ("name", "名称", 220, "w"), ("link", "链接", 80, "center"),
            ("main", "主图", 70, "center"), ("detail", "详情", 70, "center"), ("status", "状态", 80, "center"),
        ):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))
        self.tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="运行日志", font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.log_box = scrolledtext.ScrolledText(right, width=36, wrap="word")
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.log_box.configure(state="disabled")

        footer = ttk.Frame(root, padding=(28, 0, 28, 16))
        footer.grid(row=4, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")

    # ----- 通用 -----

    def copy_software_id(self):
        value = self.software_id_var.get().strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.set_status(f"已复制软件编号：{value}")

    def _set_quota_from_response(self, data: dict):
        quota = data.get("quota") if isinstance(data, dict) else None
        if isinstance(quota, dict):
            available = int(quota.get("available") or 0)
            free = int(quota.get("free") or 0)
            paid = int(quota.get("paid") or 0)
            self.quota_var.set(f"图片额度：剩余 {available} 张（默认 {free} / 充值 {paid}）")

    def register_device(self, silent: bool = False) -> bool:
        software_id = self.software_id_var.get().strip()
        try:
            data = server_register_device(self.server_url_var.get(), software_id)
        except ServerApiError as exc:
            self.device_state_var.set("设备：登记失败")
            self.log(f"软件编号登记失败：{exc}")
            if not silent:
                messagebox.showerror(APP_NAME, f"软件编号登记失败：\n{exc}", parent=self.root)
            return False
        self.server_token = str(data.get("token") or "").strip()
        self.device_state_var.set("设备：已登记")
        self._set_quota_from_response(data)
        save_config({
            "server_url": normalize_server_url(self.server_url_var.get()),
            "software_id": software_id,
            "server_token": self.server_token,
        })
        self.log(f"软件编号已登记：{software_id}")
        return True

    def ensure_server_login(self) -> bool:
        if self.server_token:
            try:
                data = server_device_status(self.server_url_var.get(), self.server_token)
                self._set_quota_from_response(data)
                self.device_state_var.set("设备：已登记")
                save_config({
                    "server_url": normalize_server_url(self.server_url_var.get()),
                    "software_id": self.software_id_var.get().strip(),
                })
                return True
            except ServerApiError:
                self.device_state_var.set("设备：重新登记中")
        return self.register_device()

    def sync_quota(self):
        if not self.server_token:
            self.register_device(silent=True)
            return
        try:
            data = server_device_status(self.server_url_var.get(), self.server_token)
            self._set_quota_from_response(data)
            self.device_state_var.set("设备：已登记")
        except ServerApiError as exc:
            self.device_state_var.set("设备：需重新登记")
            self.log(f"额度同步失败：{exc}")

    def log(self, message: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_status(self, message: str):
        self.status_var.set(message)

    def choose_output(self):
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_dir_var.set(folder)

    def open_output(self):
        path = Path(self.output_dir_var.get())
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showinfo(APP_NAME, f"无法打开目录：{exc}", parent=self.root)

    # ----- 导入 -----

    def import_file(self):
        path = filedialog.askopenfilename(
            title="导入名称+链接列表",
            filetypes=[("表格/文本", "*.xlsx *.xlsm *.csv *.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            rows = read_import_rows(Path(path))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"导入失败：{exc}", parent=self.root)
            return
        self.set_rows(rows)

    def import_clipboard(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(APP_NAME, "剪贴板是空的。", parent=self.root)
            return
        self.set_rows(parse_clipboard_rows(text))

    def set_rows(self, rows: list):
        if not rows:
            messagebox.showinfo(APP_NAME, "没有读到有效的「名称+链接」数据。", parent=self.root)
            return
        self.rows = [{"name": name, "link": link, "status": "待截图"} for name, link in rows]
        self.current_index = 0
        self.refresh_tree()
        self.set_status(f"已导入 {len(self.rows)} 行。点「开始截图」自动打开第一行链接。")
        self.log(f"导入 {len(self.rows)} 行。")

    def clear_rows(self):
        if self.work_mode:
            messagebox.showinfo(APP_NAME, "请先结束截图再清空。", parent=self.root)
            return
        self.rows = []
        self.current_index = 0
        self.refresh_tree()
        self.set_status("列表已清空。")

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            main_done, detail_done = self.counts_for(index)
            mark = "▶" if (self.work_mode and index == self.current_index) else ""
            self.tree.insert("", "end", iid=str(index), values=(
                f"{mark}{index + 1}", row["name"],
                "有" if row["link"] else "无",
                main_done, detail_done, row["status"]))
        if self.work_mode and 0 <= self.current_index < len(self.rows):
            try:
                self.tree.selection_set(str(self.current_index))
                self.tree.see(str(self.current_index))
            except tk.TclError:
                pass

    def counts_for(self, index: int) -> tuple:
        if not (0 <= index < len(self.rows)):
            return 0, 0
        main_done = sum(1 for c in self.captures if c.get("row_index") == index and c["category"] == MAIN_CATEGORY)
        detail_done = sum(1 for c in self.captures if c.get("row_index") == index and c["category"] == DETAIL_CATEGORY)
        return main_done, detail_done

    # ----- 工作模式 -----

    def start_work(self):
        if self.work_mode:
            return
        if not self.rows:
            messagebox.showinfo(APP_NAME, "请先导入名称+链接列表。", parent=self.root)
            return
        save_config({
            "server_url": normalize_server_url(self.server_url_var.get()),
            "software_id": self.software_id_var.get().strip(),
            "server_token": self.server_token,
            "output_dir": self.output_dir_var.get(),
            "main_count": int(self.main_count_var.get() or 0),
            "detail_count": int(self.detail_count_var.get() or 0),
            "prefix": self.prefix_var.get().strip() or "pic",
            "quality": int(self.quality_var.get() or 95),
            "auto_open": bool(self.auto_open_var.get()),
            "repair_mode": normalize_repair_mode(self.repair_mode_var.get()),
        })
        self.work_mode = True
        self.category_var.set(MAIN_CATEGORY)
        self.rows[self.current_index]["status"] = "进行中"
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        self.selection_box = SelectionBoxWindow(self.root)
        ok = False
        try:
            ok = self.hook.install()
        except Exception as exc:
            self.log(f"启用 Ctrl 拖动失败：{exc}")
        if ok:
            self.hook_state_var.set("● Ctrl 拖动截图：已启用")
            self.log("已启用「按住 Ctrl 拖动鼠标」截图，直接到网页里框选即可。")
        else:
            self.hook_state_var.set("● Ctrl 拖动截图：启用失败")
            self.log(f"Ctrl 拖动启用失败：{self.hook.last_error or '可能被安全软件拦截'}。")
            messagebox.showwarning(APP_NAME, "全局截图钩子启用失败，可能被安全软件拦截。\n"
                                             "请允许本程序的鼠标钩子后重试。", parent=self.root)
            self.work_mode = False
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            if self.selection_box is not None:
                try:
                    self.selection_box.destroy()
                except tk.TclError:
                    pass
                self.selection_box = None
            return
        self.hook_polling = True
        self.root.after(15, self.poll_hook)

        self.float_panel = FloatPanel(self)
        self.refresh_state()
        self.open_current_link()
        self.hide_main()
        self.set_status("工作模式已开启。")

    def stop_work(self, _event=None):
        if not self.work_mode:
            return
        self.work_mode = False
        self.hook_polling = False
        try:
            self.hook.uninstall()
        except Exception:
            pass
        if self.selection_box is not None:
            try:
                self.selection_box.destroy()
            except tk.TclError:
                pass
            self.selection_box = None
        if self.float_panel is not None:
            try:
                self.float_panel.destroy()
            except tk.TclError:
                pass
            self.float_panel = None
        self.hook_state_var.set("")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.show_main()
        self.refresh_tree()
        self.set_status(f"已结束截图。本次共 {len(self.captures)} 张，可点「AI 智能修复」处理图片。")

    def current_row(self):
        if 0 <= self.current_index < len(self.rows):
            return self.rows[self.current_index]
        return None

    def open_current_link(self):
        row = self.current_row()
        if not row:
            return
        if not self.auto_open_var.get():
            return
        link = row["link"]
        if not link:
            self.log(f"第 {self.current_index + 1} 行没有链接，跳过自动打开。")
            return
        try:
            webbrowser.open(link)
            self.log(f"已打开：{row['name']}")
        except Exception as exc:
            self.log(f"打开链接失败：{exc}")

    def set_category(self, category: str):
        self.category_var.set(category)
        self.refresh_state()

    def refresh_state(self):
        row = self.current_row()
        name = row["name"] if row else "-"
        main_done, detail_done = self.counts_for(self.current_index)
        main_count = int(self.main_count_var.get() or 0)
        detail_count = int(self.detail_count_var.get() or 0)
        self.panel_name_var.set(f"{self.current_index + 1}/{len(self.rows)}　{name}")
        self.panel_progress_var.set(
            f"主图 {main_done}/{main_count} · 详情 {detail_done}/{detail_count} · 当前存：{self.category_var.get()}")
        if self.float_panel is not None:
            self.float_panel.refresh_category()
        self.refresh_tree()

    # ----- 截图手势 -----

    def poll_hook(self):
        try:
            while True:
                kind, x, y = self.hook.events.get_nowait()
                if kind == "start":
                    if self.busy or self.grabbing:
                        continue
                    self.gesture_start = (x, y)
                    if self.selection_box:
                        self.selection_box.begin(x, y)
                elif kind == "move":
                    if self.selection_box and self.selection_box.visible:
                        self.selection_box.update_to(x, y)
                elif kind == "finish":
                    if self.gesture_start and self.selection_box:
                        sx, sy = self.gesture_start
                        self.gesture_start = None
                        self.selection_box.end()
                        self._finish_gesture(sx, sy, x, y)
        except queue.Empty:
            pass
        if self.hook_polling:
            self.root.after(15, self.poll_hook)

    def _finish_gesture(self, sx, sy, ex, ey):
        left, top = min(sx, ex), min(sy, ey)
        right, bottom = max(sx, ex), max(sy, ey)
        if right - left < 5 or bottom - top < 5:
            self.log("框选区域太小，已忽略。")
            return
        self.grabbing = True
        self.hook.enabled = False
        self.root.after(120, lambda: self._grab((int(left), int(top), int(right), int(bottom))))

    def _grab(self, bbox):
        try:
            from PIL import ImageGrab
        except Exception:
            messagebox.showerror(APP_NAME, "当前环境不支持屏幕截图（缺少 ImageGrab）。", parent=self.root)
            self.grabbing = False
            self.hook.enabled = True
            return
        try:
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
            self.save_capture(image)
        except Exception as exc:
            self.log(f"截图失败：{exc}")
            write_error_log(f"截图失败：{exc}")
        finally:
            self.grabbing = False
            self.hook.enabled = True

    def save_capture(self, image):
        row = self.current_row()
        if not row:
            self.log("没有当前行，截图忽略。")
            return
        category = self.category_var.get()
        name = safe_folder_name(row["name"], f"第{self.current_index + 1}行")
        prefix = self.prefix_var.get().strip() or "pic"
        done = self.counts_for(self.current_index)[0 if category == MAIN_CATEGORY else 1]
        target = Path(self.output_dir_var.get()) / name / category / f"{prefix}{done + 1}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(target, "JPEG", quality=int(self.quality_var.get() or 95))
        self.captures.append({
            "path": target,
            "row_index": self.current_index,
            "name": row["name"],
            "category": category,
        })
        self.log(f"已存：{name}/{category}/{target.name}（{image.width}x{image.height}）")
        self.after_capture()

    def after_capture(self):
        main_count = int(self.main_count_var.get() or 0)
        detail_count = int(self.detail_count_var.get() or 0)
        main_done, detail_done = self.counts_for(self.current_index)
        category = self.category_var.get()

        if category == MAIN_CATEGORY:
            if main_count and main_done >= main_count:
                if detail_count > 0:
                    self.category_var.set(DETAIL_CATEGORY)
                    self.log("主图截够，自动切到「详情」。")
                else:
                    self.advance_row(auto=True)
                    return
        else:
            if detail_count and detail_done >= detail_count:
                self.advance_row(auto=True)
                return
        self.refresh_state()

    def advance_row(self, auto: bool):
        row = self.current_row()
        if row:
            row["status"] = "已完成"
        if self.current_index + 1 >= len(self.rows):
            self.refresh_state()
            self.log("所有行已截完。可以点「AI 智能修复」。")
            self.set_status("全部截完，选择修复类型后点「AI 智能修复」。")
            if auto:
                messagebox.showinfo(APP_NAME, "列表已全部截完，可以点「AI 智能修复」。", parent=self.root)
            return
        self.current_index += 1
        self.category_var.set(MAIN_CATEGORY)
        self.rows[self.current_index]["status"] = "进行中"
        self.log(f"切到第 {self.current_index + 1} 行：{self.rows[self.current_index]['name']}")
        self.open_current_link()
        self.refresh_state()

    def next_row_manual(self):
        if not self.work_mode:
            return
        main_done, detail_done = self.counts_for(self.current_index)
        if main_done + detail_done == 0:
            if not messagebox.askyesno(APP_NAME, "当前商品一张图都没截，确定跳到下一行吗？", parent=self.root):
                return
        self.advance_row(auto=False)

    def copy_previous(self):
        if not self.work_mode:
            return
        if self.current_index <= 0:
            messagebox.showinfo(APP_NAME, "已经是第一行，没有上一行可复制。", parent=self.root)
            return
        prev = self.rows[self.current_index - 1]
        cur = self.current_row()
        prev_dir = Path(self.output_dir_var.get()) / safe_folder_name(prev["name"], "上一行")
        cur_name = safe_folder_name(cur["name"], f"第{self.current_index + 1}行")
        cur_dir = Path(self.output_dir_var.get()) / cur_name
        if not prev_dir.exists():
            messagebox.showinfo(APP_NAME, "上一行还没有截图，无法复制。", parent=self.root)
            return
        copied = 0
        for category in (MAIN_CATEGORY, DETAIL_CATEGORY):
            src = prev_dir / category
            if not src.exists():
                continue
            dst = cur_dir / category
            dst.mkdir(parents=True, exist_ok=True)
            for file in sorted(src.glob("*.jpg")):
                target = dst / file.name
                shutil.copy2(file, target)
                self.captures.append({
                    "path": target,
                    "row_index": self.current_index,
                    "name": cur["name"],
                    "category": category,
                })
                copied += 1
        self.log(f"已从上一行复制 {copied} 张到「{cur_name}」。")
        self.advance_row(auto=False)

    def show_main(self):
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass

    def hide_main(self):
        try:
            self.root.withdraw()
        except tk.TclError:
            pass

    # ----- AI 智能修复 -----

    def ai_repair(self):
        if self.busy:
            return
        if not self.captures:
            messagebox.showinfo(APP_NAME, "本次还没有任何截图。", parent=self.root)
            return
        if not self.ensure_server_login():
            return
        existing = [c for c in self.captures if c["path"].exists()]
        if not existing:
            messagebox.showinfo(APP_NAME, "截图文件都不在了。", parent=self.root)
            return
        mode_key = normalize_repair_mode(self.repair_mode_var.get())
        mode_label = repair_mode_label(mode_key)
        self.repair_mode_var.set(mode_label)
        save_config({"repair_mode": mode_key})
        server_url = normalize_server_url(self.server_url_var.get())
        token = self.server_token
        self.busy = True
        self.stop_event = threading.Event()
        self.repair_button.configure(state="disabled")
        self.set_status(f"AI 正在检测 {len(existing)} 张截图是否需要「{mode_label}」...")
        self.log(f"开始检测 {len(existing)} 张截图，修复类型：{mode_label}。")
        self.ai_events = queue.Queue()
        self.ai_thread = threading.Thread(
            target=self._detect_worker, args=(server_url, token, existing, mode_key, mode_label), daemon=True)
        self.ai_thread.start()
        self.root.after(200, self._poll_detect)

    def _detect_worker(self, server_url: str, token: str, captures: list, mode_key: str, mode_label: str):
        candidates = []
        for index, capture in enumerate(captures):
            if self.stop_event.is_set():
                break
            try:
                result = server_detect_watermark(server_url, token, capture["path"], mode_key, self.stop_event)
                self.ai_events.put(("progress", index + 1, len(captures)))
                if result["needs_repair"]:
                    candidates.append({"path": capture["path"], "name": capture["name"], "note": result["note"]})
            except ServerApiError as exc:
                message = str(exc)
                self.ai_events.put(("error", message, capture["path"].name))
                if "登记" in message or "额度不足" in message or "欠费" in message:
                    self.ai_events.put(("fatal", message))
                    return
            except Exception as exc:
                self.ai_events.put(("error", str(exc), capture["path"].name))
        self.ai_events.put(("detect_done", candidates, mode_key, mode_label))

    def _poll_detect(self):
        try:
            while True:
                event = self.ai_events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self.set_status(f"AI 检测中 {event[1]}/{event[2]}...")
                elif kind == "error":
                    self.log(f"检测失败：{event[2]} —— {event[1]}")
                elif kind == "fatal":
                    self.busy = False
                    self.repair_button.configure(state="normal")
                    self.set_status(f"AI 检测停止：{event[1]}")
                    messagebox.showerror(APP_NAME, f"AI 检测停止：\n{event[1]}", parent=self.root)
                    return
                elif kind == "detect_done":
                    self._on_detect_done(event[1], event[2], event[3])
                    return
        except queue.Empty:
            pass
        if self.busy:
            self.root.after(200, self._poll_detect)

    def _on_detect_done(self, candidates: list, mode_key: str, mode_label: str):
        if self.stop_event.is_set() and not candidates:
            self.busy = False
            self.repair_button.configure(state="normal")
            self.set_status("已停止检测。")
            return
        self.log(f"检测完成，疑似需要「{mode_label}」{len(candidates)} 张。")
        if not candidates:
            self.busy = False
            self.repair_button.configure(state="normal")
            self.set_status(f"AI 没检测到需要「{mode_label}」的图。")
            messagebox.showinfo(APP_NAME, f"AI 没有发现明显需要「{mode_label}」的图片。", parent=self.root)
            return
        self.show_main()
        dialog = ConfirmDialog(self, candidates, mode_label)
        self.root.wait_window(dialog)
        targets = dialog.result
        if not targets:
            self.busy = False
            self.repair_button.configure(state="normal")
            self.set_status("已取消图片修复。")
            return
        self._start_remove(targets, mode_key, mode_label)

    def _start_remove(self, targets: list, mode_key: str, mode_label: str):
        server_url = normalize_server_url(self.server_url_var.get())
        token = self.server_token
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snap_wm_"))
        self.set_status(f"正在{mode_label} 0/{len(targets)}...")
        self.log(f"开始{mode_label} {len(targets)} 张。")
        self.ai_events = queue.Queue()
        self.ai_thread = threading.Thread(
            target=self._remove_worker, args=(server_url, token, targets, mode_key, mode_label), daemon=True)
        self.ai_thread.start()
        self.root.after(200, self._poll_remove)

    def _remove_worker(self, server_url: str, token: str, targets: list, mode_key: str, mode_label: str):
        done = 0
        failed = 0
        for index, path in enumerate(targets):
            if self.stop_event.is_set():
                break
            try:
                # 备份原图，再原地覆盖为修复结果
                backup = path.parent / BACKUP_DIR_NAME
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup / path.name)
                server_remove_watermark_to(server_url, token, path, path, self.temp_dir, mode_key, self.stop_event)
                done += 1
                self.ai_events.put(("removed", index + 1, len(targets), path.name, mode_label))
            except ServerApiError as exc:
                failed += 1
                self.ai_events.put(("rm_error", str(exc), path.name))
                if "登记" in str(exc) or "额度不足" in str(exc) or "欠费" in str(exc):
                    break
            except Exception as exc:
                failed += 1
                self.ai_events.put(("rm_error", str(exc), path.name))
        self.ai_events.put(("remove_done", done, failed))

    def _poll_remove(self):
        try:
            while True:
                event = self.ai_events.get_nowait()
                kind = event[0]
                if kind == "removed":
                    self.set_status(f"正在{event[4]} {event[1]}/{event[2]}...")
                    self.log(f"{event[4]}完成：{event[3]}")
                elif kind == "rm_error":
                    self.log(f"图片修复失败：{event[2]} —— {event[1]}")
                elif kind == "remove_done":
                    self._on_remove_done(event[1], event[2])
                    return
        except queue.Empty:
            pass
        if self.busy:
            self.root.after(200, self._poll_remove)

    def _on_remove_done(self, done: int, failed: int):
        self.busy = False
        self.repair_button.configure(state="normal")
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None
        self.set_status(f"图片修复完成：成功 {done} 张，失败 {failed} 张。原图已备份到各「{BACKUP_DIR_NAME}」目录。")
        self.log(f"图片修复结束：成功 {done}，失败 {failed}。")
        self.sync_quota()
        messagebox.showinfo(APP_NAME, f"图片修复完成：成功 {done} 张，失败 {failed} 张。\n"
                                      f"原图已备份到各商品的「{BACKUP_DIR_NAME}」目录。", parent=self.root)

    # ----- 关闭 -----

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno(APP_NAME, "AI 正在处理，确定停止并退出吗？", parent=self.root):
                return
            self.stop_event.set()
        try:
            self.hook.uninstall()
        except Exception:
            pass
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.root.destroy()

    def run(self):
        self.log("程序已启动。")
        self.root.mainloop()


def enable_dpi_awareness():
    """让进程 DPI 感知，使钩子坐标、选框窗口、ImageGrab 三者用同一套物理坐标。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


if __name__ == "__main__":
    enable_dpi_awareness()
    try:
        SnapSaverApp().run()
    except Exception:
        write_error_log(traceback.format_exc())
