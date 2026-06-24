"""截图存图助手

工作流：
1. 导入「A列名称 + B列链接」列表，点开始 → 自动用系统默认浏览器打开当前行链接
2. 在网页里按住 Ctrl + 鼠标左键拖框选区 → 松开自动截图保存到 输出/名称/主图(或详情)/
3. 设定主图、详情张数：主图截够自动切详情，详情截够自动切下一行并打开下一个链接
4. 全部截完选择修复类型并点「AI 智能修复」：弹出缩略图窗口，人工勾选要处理的图片
5. 无需账号注册，软件自动读取本机 MAC 作为软件编号；新编号默认 10 张图片处理额度
6. 确认后按成功处理张数扣减额度，结果覆盖原图，原图备份

依赖：Pillow、openpyxl（可选，读 xlsx 用）。图片修复走服务器接口，
服务器使用已配置的阿里云百炼模型；客户端不保存阿里 API Key。
"""

import base64
import csv
import ctypes
import hashlib
import io
import json
import mimetypes
import os
import platform
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

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk


APP_NAME = "智能截图软件"
DEFAULT_SERVER_URL = "https://tools.haobanfa.online"
APP_VERSION = "V2.0.0"

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
WATERMARK_MODEL = "qwen-image-2.0"
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
    ("all", "白底上图"),
)
REPAIR_LABEL_TO_KEY = {label: key for key, label in REPAIR_MODES}
REPAIR_LABEL_TO_KEY["全部去除"] = "all"
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


def scan_image_folder(folder: Path) -> list[Path]:
    root = Path(folder)
    images: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            relative_parts = path.parts
        if BACKUP_DIR_NAME in relative_parts:
            continue
        images.append(path)
    return sorted(images, key=lambda item: str(item).lower())


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


def is_fatal_ai_error(message: str) -> bool:
    text = str(message or "").lower()
    fatal_terms = (
        "access_denied",
        "access denied",
        "forbidden",
        "permission",
        "invalidapikey",
        "invalid_api_key",
        "incorrect api key",
        "dashscope_api_key",
        "api key 无效",
        "权限",
        "无权",
        "未开通",
        "登记",
        "额度不足",
        "欠费",
        "客服",
        "401",
        "403",
    )
    return any(term.lower() in text for term in fatal_terms)


# 致命错误（连接失败/服务不可用/额度不足）文案统一含「客服」，
# is_fatal_ai_error 的 fatal_terms 含「客服」据此判断停止——改文案须保留该词。
def friendly_dashscope_error(code: str, message: str) -> str:
    text = f"{code} {message}".lower()
    if "invalidapikey" in text or "invalid_api_key" in text or "incorrect api key" in text:
        return "图片修复服务连接失败，请联系客服。"
    if "access_denied" in text or "access denied" in text:
        return "图片修复服务暂时不可用，请联系客服。"
    if "arrearage" in text:
        return "修复额度不足，请联系客服充值。"
    if "throttling" in text or "ratelimit" in text or "rate limit" in text:
        return "请求太频繁，稍后会自动重试。"
    if "datainspection" in text or "inappropriate" in text or "green" in text:
        return "图片未通过内容审核，已跳过。"
    return "图片修复失败，请稍后重试。"


# 无代理 opener：彻底绕过系统代理 / 环境变量代理直连
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _urlopen_safe(request, timeout: int = 60):
    """直连 opener：访问自己的公网服务器(tools.haobanfa.online)和阿里云 API
    一律不走系统代理。这样用户开/关 VPN / Clash 都不受影响——系统残留代理
    指向 127.0.0.1:端口（VPN 关掉后没人监听）正是 WinError 10061 的根因。

    极端情况（公司网络强制必须经代理才能出网）下直连可能不通，那时再退回
    系统默认（可能带代理）重试一次兜底。"""
    try:
        return _NO_PROXY_OPENER.open(request, timeout=timeout)
    except (urllib.error.URLError, OSError):
        # 直连不通：可能是必须走代理的网络环境，退回系统默认重试一次
        return urllib.request.urlopen(request, timeout=timeout)


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
        with _urlopen_safe(request, timeout=timeout) as response:
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
            raise DashScopeError("图片修复服务连接失败，请联系客服。")
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


def _robust_mac() -> str:
    """取本机真实网卡 MAC（12 位大写十六进制）。

    优先用 getmac 列举网卡取稳定的物理地址，取不到再回退 uuid.getnode()。
    比单用 getnode() 可靠：getnode() 打包成 exe 后取不到真实网卡时会返回随机数，
    多网卡时还可能每次返回不同值。
    """
    try:
        import subprocess
        out = subprocess.run(
            ["getmac", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000,  # CREATE_NO_WINDOW，不弹黑框
        ).stdout
        macs = []
        for token in re.findall(r'([0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5})', out):
            hexv = re.sub(r'[^0-9A-Fa-f]', '', token).upper()
            if len(hexv) == 12 and hexv != "000000000000":
                macs.append(hexv)
        if macs:
            return sorted(set(macs))[0]  # 排序取最小，保证同一台机器每次稳定
    except Exception:
        pass
    return f"{uuid.getnode():012X}"


def local_software_id() -> str:
    # 软件编号 = 本机真实网卡 MAC（明文 12 位十六进制）。
    # 软件类别（截图=pic）由登记时上报的 app 字段在服务器端区分，编号本身只放 MAC。
    # 每次启动按本机网卡「实时计算」，不从配置文件读旧值——
    # 否则把软件目录（含配置）拷到别的电脑，旧编号会被带过去，导致多台电脑同一个序列号。
    return _robust_mac()


def server_register_device(server_url: str, software_id: str, legacy_id: str = "") -> dict:
    body = {
        "software_id": software_id,
        "app": "snap-saver",
        "version": APP_VERSION,
    }
    if legacy_id and legacy_id != software_id:
        body["legacy_id"] = legacy_id
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        normalize_server_url(server_url) + "/api/desktop/device/register", data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    try:
        with _urlopen_safe(request, timeout=30) as response:
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
        with _urlopen_safe(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ServerApiError(_server_error_from_body(body, f"额度同步失败：HTTP {exc.code}"))
    except urllib.error.URLError as exc:
        raise ServerApiError(f"连接服务器失败：{exc.reason}")


def _server_json_post(server_url: str, token: str, path: str, body: dict,
                      timeout: int = 90) -> dict:
    """向桌面端接口发送带设备 token 的 JSON 请求。"""
    if not token:
        raise ServerApiError("请先登记软件编号。")
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        normalize_server_url(server_url) + path, data=payload, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json; charset=utf-8")
    request.add_header("Accept", "application/json")
    try:
        with _urlopen_safe(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise ServerApiError(_server_error_from_body(raw, f"服务器请求失败：HTTP {exc.code}"))
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
        with _urlopen_safe(request, timeout=timeout) as response:
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


def server_describe_image(server_url: str, token: str, path: Path,
                          hint: str = "", style: str = "detail") -> dict:
    """调用后端 AI 图片描述：上传截图 + 用户简介，返回 {description, charged, remaining}。
    复用 detect 的图片预处理（压到 1024px、转 JPEG）省流量、提速。"""
    with tempfile.TemporaryDirectory(prefix="snap_describe_") as tmp:
        prepared = prepare_detect_input(path, Path(tmp))
        response = _server_upload(
            server_url, token, "/api/desktop/doc/describe-image", prepared,
            timeout=150, expect_json=True,
            fields=[("hint", hint or ""), ("style", style or "detail")])
    return {
        "description": str(response.get("description") or "").strip(),
        "charged": bool(response.get("charged")),
        "remaining": response.get("remaining"),
    }


def server_generate_product_params(server_url: str, token: str, text: str) -> dict:
    """一句商品介绍 → 标题 + 参数行。"""
    response = _server_json_post(
        server_url, token, "/api/desktop/doc/generate-params", {"text": text}, timeout=90)
    rows = []
    for item in response.get("params") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if name and value:
            rows.append({"name": name[:30], "value": value[:120]})
    return {"title": str(response.get("title") or "").strip()[:80], "params": rows[:12]}


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
        with _urlopen_safe(request, timeout=180):
            pass
    except urllib.error.HTTPError as exc:
        raise DashScopeError("图片上传失败，请稍后重试。")
    except urllib.error.URLError as exc:
        raise DashScopeError("图片上传失败，请检查网络后重试。")
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
        with _urlopen_safe(urllib.request.Request(url), timeout=180) as response:
            return response.read()
    except Exception as exc:
        raise DashScopeError(f"下载结果图失败：{exc}")


def qwen_repair_prompt() -> str:
    return (
        "请基于输入图片生成一张可直接用于电商平台上架的高级白底商品主图。"
        "核心约束：只清理背景和后期叠加干扰，不要重新设计或重新拍摄商品。"
        "必须保持原图中商品的数量、排列、朝向、拍摄角度、透视方向、姿态、可见零件位置和结构关系；"
        "如果原图是双向展示、多台展示、左右对比或多角度展示，必须保持原来的数量、相对位置和各自角度，"
        "不要合并成单台，不要换成新的角度。拿捏不准、被遮挡、看不清的部位，只做最小范围修补，"
        "优先保留原图可见轮廓；不要根据常识脑补背面、侧面、支架、底座、叶片或其他看不见的结构。"
        "允许在不改变主体角度和布局的前提下轻微居中、适度留白。"
        "背景改为纯白或接近纯白，画面干净高级，边缘清晰，保留自然真实光影和轻微柔和投影。"
        "清理水印、平台角标、促销文案、价格条、店铺名、网址、杂乱背景和无关物体。"
        "必须保持商品型号、颜色、材质、比例、包装、真实品牌 logo、真实包装文字不变；"
        "不要新增文案、不要新增配件、不要改变商品卖点，不要把商品画成卡通，不要过度美颜。输出单张清晰 PNG。"
    )


def ds_qwen_repair_url(api_key: str, path: Path, stop_event: threading.Event) -> str:
    if stop_event.is_set():
        raise DashScopeError("已停止。")
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": WATERMARK_MODEL,
        "input": {
            "messages": [{
                "role": "user",
                "content": [
                    {"image": f"data:{mime};base64,{b64}"},
                    {"text": qwen_repair_prompt()},
                ],
            }],
        },
        "parameters": {
            "watermark": False,
            "negative_prompt": "旋转商品、改变角度、改变视角、改变拍摄方向、改变朝向、改变姿态、改变透视、把正面改侧面、把侧面改正面、把多台商品合并成单台、改变商品数量、脑补商品背面或侧面、补错结构、虚假配件、改变商品结构、改变商品比例、改变支架形状、改变风扇高度、错误 logo、错误包装、新增文字、模糊、低清晰度、变形、错色、复杂背景、彩色背景、过度美颜、卡通风格",
            "n": 1,
            "prompt_extend": False,
        },
    }
    response = _ds_request(
        f"{DASHSCOPE_BASE}/api/v1/services/aigc/multimodal-generation/generation",
        api_key, payload, timeout=300)
    content = (((response.get("output") or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("image"):
                return str(part["image"])
    raise DashScopeError("图片修复成功但没有返回结果，请重试。")


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
        result_url = ds_qwen_repair_url(api_key, prepared, stop_event)
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
        self.hovering = False
        self.last_move_queued = 0.0
        self.last_hover_queued = 0.0
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
            self.last_error = "截图功能启动超时，请重试或重启软件"
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
                        self.hovering = False
                        self.capturing = True
                        self.events.put(("start", x, y))
                        return 1  # 吞掉，避免网页收到这次点击
                elif msg == WM_MOUSEMOVE:
                    if self.capturing:
                        now = time.perf_counter()
                        # 钩子层先限到 120Hz，避免高回报率鼠标把事件队列塞满。
                        if now - self.last_move_queued >= 1 / 120:
                            self.last_move_queued = now
                            self.events.put(("move", x, y))
                    elif self._ctrl_down():
                        self.hovering = True
                        now = time.perf_counter()
                        if now - self.last_hover_queued >= 1 / 30:
                            self.last_hover_queued = now
                            self.events.put(("hover", x, y))
                    elif self.hovering:
                        self.hovering = False
                        self.events.put(("hover_end", x, y))
                elif msg == WM_LBUTTONUP:
                    if self.capturing:
                        self.capturing = False
                        self.events.put(("finish", x, y))
                        return 1
            except Exception:
                pass
        return self.user32.CallNextHookEx(None, n_code, w_param, l_param)


class SelectionBoxWindow(tk.Toplevel):
    """Ctrl 拖动时的全屏选框反馈窗口，坐标用屏幕物理坐标。

    按下取图键的瞬间会把整屏「冻结」成一张静态图铺在最上层：
    拖动选框时鼠标落在冻结图上，网页收不到鼠标移动，就不会再触发
    悬停放大镜/红框等浮层，避免把它们截进去。
    """

    def __init__(self, root):
        super().__init__(root)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#0b0f14", cursor="crosshair")
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+0+0")
        self.canvas = tk.Canvas(self, bg="#0b0f14", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.rect = None
        self.frozen_photo = None
        self.start = (0, 0)
        self.visible = False
        self.withdraw()

    def begin(self, x, y, frozen_photo=None):
        self.start = (x, y)
        self.canvas.delete("all")
        self.frozen_photo = frozen_photo
        if frozen_photo is not None:
            # 冻结整屏：铺满静态截图，完全不透明（看到什么就截到什么）
            self.attributes("-alpha", 1.0)
            self.canvas.create_image(0, 0, anchor="nw", image=frozen_photo)
        else:
            # 没拿到冻结图时退回半透明遮罩
            self.attributes("-alpha", 0.25)
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
        self.canvas.delete("all")
        self.rect = None
        self.frozen_photo = None
        self.withdraw()


# ---------------- 工作浮窗 ----------------

# ---------------- 多图整理成文档（长图 / PDF，可配说明） ----------------

def _doc_font(size: int, family="yahei", bold=False):
    fonts = {
        "yahei": ([r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"] if bold
                  else [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"]),
        "simsun": [r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\simhei.ttf"],
        "simhei": [r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\msyhbd.ttc"],
        "kaiti": [r"C:\Windows\Fonts\simkai.ttf", r"C:\Windows\Fonts\msyh.ttc"],
    }
    paths = fonts.get(str(family or "yahei"), fonts["yahei"])
    for path in paths + [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]:
        try:
            return ImageFont.truetype(path, max(10, int(size)))
        except Exception:
            continue
    return ImageFont.load_default()


def _doc_style(style=None):
    """清洗 Electron 传入的排版参数，旧调用不传 style 时保持原效果。"""
    raw = style if isinstance(style, dict) else {}
    def number(name, default, low, high):
        try:
            return max(low, min(high, int(raw.get(name, default))))
        except (TypeError, ValueError):
            return default
    try:
        line_spacing = float(raw.get("body_line_spacing", 1.5))
        if line_spacing > 3:
            line_spacing /= 100.0
        line_spacing = max(1.2, min(2.2, line_spacing))
    except (TypeError, ValueError):
        line_spacing = 1.5
    return {
        "font_family": raw.get("font_family") if raw.get("font_family") in
                       {"yahei", "simsun", "simhei", "kaiti"} else "yahei",
        "title_size": number("title_size", 46, 32, 80),
        "body_size": number("body_size", 28, 18, 38),
        "title_align": raw.get("title_align") if raw.get("title_align") in {"left", "center"} else "left",
        "body_align": raw.get("body_align") if raw.get("body_align") in {"left", "center"} else "left",
        "margin": raw.get("margin") if raw.get("margin") in {"narrow", "normal", "wide"} else "normal",
        "title_space": raw.get("title_space") if raw.get("title_space") in {"compact", "normal", "large"} else "normal",
        "template": raw.get("template") if raw.get("template") in {"clean", "classic", "warm"} else "clean",
        "orientation": raw.get("orientation") if raw.get("orientation") in {"portrait", "landscape"} else "portrait",
        "body_weight": raw.get("body_weight") if raw.get("body_weight") in {"regular", "bold"} else "regular",
        "body_line_spacing": line_spacing,
        "paragraph_indent": raw.get("paragraph_indent") not in {False, "none", "0", 0},
        "text_color": raw.get("text_color") if raw.get("text_color") in {"dark", "gray", "green"} else "dark",
        "caption_style": raw.get("caption_style") if raw.get("caption_style") in {"plain", "highlight", "quote"} else "plain",
        "show_number": raw.get("show_number") not in {False, "hide", "0", 0},
    }


def _text_x(draw, line, font, left, width, align):
    if align != "center":
        return left
    return left + max(0, (width - draw.textlength(line, font=font)) / 2)


def _caption_background(draw, box, style, scale):
    if style["caption_style"] == "highlight":
        draw.rounded_rectangle(box, radius=max(6, round(8 * scale)), fill="#f0f8f3")
    elif style["caption_style"] == "quote":
        x1, y1, _x2, y2 = box
        draw.rounded_rectangle(
            (x1, y1, x1 + max(5, round(6 * scale)), y2),
            radius=max(2, round(3 * scale)), fill="#079a48")


def _wrap_text(draw, text, font, max_width, indent=False):
    """按像素宽度把文本（含中文）折行。
    indent=True 时每个自然段首行缩进两个全角字符（中文排版习惯）。"""
    lead = "　　" if indent else ""  # 两个全角空格
    lines = []
    for para in str(text).split("\n"):
        if para == "":
            lines.append("")
            continue
        para = lead + para  # 段首缩进并入正文，折行时自然占位
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_width or not cur:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def _doc_target_width(items, cap_min=1100, cap_max=2400):
    """内容区目标宽度：取所有图最大宽度（限制在 1100~2400），避免把高清截图降采样糊掉。
    item 兼容 (img, cap) 或 (img, cap, size)，只取第一个元素（图）。"""
    if not items:
        return cap_min
    return max(cap_min, min(cap_max, max(it[0].width for it in items)))


def render_doc_card(image, caption, index, target_inner, scale, layout="auto", size="big", style=None):
    """单张截图卡片，自适应版式 + 自动缩放：
      - 竖图（高>宽 1.15 倍）且文字较多 → 图左文右（图自动放大填满文字高度，无留白）
      - 其它（横图/方图/文字很少）→ 图上文下（图按 size 档位缩放，居中）
    size 档位（只作用于「图上文下」版式，控制图占内容宽度的比例）：
      big=100% / medium=72% / small=48%。让用户能把大截图排成中/小图。
    放大有上限（最多 1.8 倍）防止把低清小图拉糊。
    layout 可强制 'top' / 'side' / 'auto'。所有排版尺寸随 scale 等比。"""
    style = _doc_style(style)
    pad_base = {"narrow": 24, "normal": 40, "wide": 68}[style["margin"]]
    pad = round(pad_base * scale)
    gap = round(36 * scale)
    img = image.convert("RGB")
    cap_font = _doc_font(round(style["body_size"] * scale), style["font_family"],
                         bold=style["body_weight"] == "bold")
    line_h = max(24, round(style["body_size"] * style["body_line_spacing"] * scale))
    text = str(caption or "").strip()
    if text and style["show_number"]:
        text = f"{index}. {text}"
    indent = style["paragraph_indent"] and style["body_align"] == "left"
    text_fill = {"dark": "#222222", "gray": "#55605a", "green": "#075c32"}[style["text_color"]]
    measure = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    card_w = target_inner + pad * 2
    MAX_UPSCALE = 1.8  # 放大上限，超过会糊

    # size 档位 → 图占内容区的宽度比例（A4 版面：全宽 / 2/3 / 1/2 / 1/4）
    size_ratio = {
        "full": 1.0, "two_third": 0.667, "half": 0.5, "quarter": 0.25,
        # 兼容旧值
        "big": 1.0, "medium": 0.667, "small": 0.5,
    }.get(size, 1.0)

    # ── 自动判定版式 ──
    # 1) 竖图有文字 → 图左文右
    # 2) 图被缩小到 ≤55%（half / quarter）→ 图左文右环绕（旁边留白给文字，更紧凑好看）
    # 3) 其它（全宽 / 2/3 横图）→ 图上文下
    is_portrait = img.height > img.width * 1.15
    if layout == "auto":
        if text and (is_portrait or size_ratio <= 0.55):
            layout = "side"
        else:
            layout = "top"

    # ───── 图左文右（文字环绕在图旁）─────
    if layout == "side" and text:
        # 图宽：竖图按填满文字高度，横图按 size_ratio（缩小档）控制
        if is_portrait:
            # 竖图：先估文字高，让图高≈文字高，消除留白
            est_text_w = card_w - (pad + round(target_inner * 0.50) + gap) - pad
            est_lines = _wrap_text(measure, text, cap_font, est_text_w, indent=indent)
            target_img_h = (len(est_lines) * line_h) or img.height
            scale_by_h = target_img_h / img.height
            scale_by_w = round(target_inner * 0.55) / img.width
            factor = max(0.05, min(scale_by_h, scale_by_w, MAX_UPSCALE))
        else:
            # 横图缩小档：图宽 = 内容区 × size_ratio
            factor = (target_inner * size_ratio) / img.width
            factor = max(0.05, min(factor, MAX_UPSCALE))
        img_w = max(1, round(img.width * factor))
        img_h = max(1, round(img.height * factor))
        img = img.resize((img_w, img_h), Image.LANCZOS)

        text_x = pad + img_w + gap
        text_w = card_w - text_x - pad
        cap_lines = _wrap_text(measure, text, cap_font, text_w, indent=indent)
        text_h = len(cap_lines) * line_h
        content_h = max(img_h, text_h)
        card = Image.new("RGB", (card_w, pad + content_h + pad), "white")
        card.paste(img, (pad, pad + (content_h - img_h) // 2))
        draw = ImageDraw.Draw(card)
        _caption_background(draw, (text_x - round(10 * scale), pad - round(8 * scale),
                                   card_w - pad + round(10 * scale),
                                   pad + text_h + round(8 * scale)), style, scale)
        y = pad
        for ln in cap_lines:
            x_line = _text_x(draw, ln, cap_font, text_x, text_w, style["body_align"])
            draw.text((x_line, y), ln, fill=text_fill, font=cap_font)
            y += line_h
        return card

    # ───── 图上文下（默认）─────
    box_w = max(1, round(target_inner * size_ratio))
    w = img.width
    factor = box_w / w
    factor = min(factor, MAX_UPSCALE)  # 小图放大不超上限，防糊
    new_w = max(1, round(w * factor))
    new_h = max(1, round(img.height * factor))
    if (new_w, new_h) != img.size:
        img = img.resize((new_w, new_h), Image.LANCZOS)
    x = (card_w - img.width) // 2
    cap_lines = _wrap_text(measure, text, cap_font, target_inner, indent=indent) if text else []
    cap_block = (round(16 * scale) + len(cap_lines) * line_h) if cap_lines else 0
    card = Image.new("RGB", (card_w, pad + img.height + cap_block + pad), "white")
    card.paste(img, (x, pad))
    if cap_lines:
        draw = ImageDraw.Draw(card)
        y = pad + img.height + round(16 * scale)
        _caption_background(draw, (pad - round(10 * scale), y - round(8 * scale),
                                   card_w - pad + round(10 * scale),
                                   y + len(cap_lines) * line_h + round(8 * scale)), style, scale)
        for ln in cap_lines:
            x_line = _text_x(draw, ln, cap_font, pad, target_inner, style["body_align"])
            draw.text((x_line, y), ln, fill=text_fill, font=cap_font)
            y += line_h
    return card


def render_doc_title(title, intro, target_inner, scale, style=None):
    style = _doc_style(style)
    pad_base = {"narrow": 24, "normal": 40, "wide": 68}[style["margin"]]
    pad = round(pad_base * scale)
    card_w = target_inner + pad * 2
    t_font = _doc_font(round(style["title_size"] * scale), style["font_family"], bold=True)
    intro_size = max(18, round(style["body_size"] * .88))
    i_font = _doc_font(round(intro_size * scale), style["font_family"])
    t_lh = max(40, round(style["title_size"] * 1.32 * scale))
    i_lh = max(26, round(intro_size * 1.5 * scale))
    measure = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    t_lines = _wrap_text(measure, title or "使用说明", t_font, target_inner)
    i_lines = _wrap_text(measure, intro, i_font, target_inner) if str(intro or "").strip() else []
    height = pad + len(t_lines) * t_lh + (round(24 * scale) + len(i_lines) * i_lh if i_lines else 0) + pad
    min_height = {"compact": 150, "normal": 230, "large": 380}[style["title_space"]]
    backgrounds = {"clean": "#ffffff", "classic": "#eff8f2", "warm": "#fff8ee"}
    title_colors = {"clean": "#0b1f16", "classic": "#075c32", "warm": "#70421f"}
    page = Image.new("RGB", (card_w, max(height, round(min_height * scale))), backgrounds[style["template"]])
    draw = ImageDraw.Draw(page)
    if style["template"] != "clean":
        accent = "#079a48" if style["template"] == "classic" else "#d78b42"
        draw.rectangle((0, 0, max(6, round(8 * scale)), page.height), fill=accent)
    y = pad
    for ln in t_lines:
        x_line = _text_x(draw, ln, t_font, pad, target_inner, style["title_align"])
        draw.text((x_line, y), ln, fill=title_colors[style["template"]], font=t_font)
        y += t_lh
    y += round(24 * scale)
    for ln in i_lines:
        x_line = _text_x(draw, ln, i_font, pad, target_inner, style["title_align"])
        draw.text((x_line, y), ln, fill="#444444", font=i_font)
        y += i_lh
    return page


DOC_WATERMARK = "好办法智能截图  ·  tools.haobanfa.online"


def _tile_watermark(page, scale, text=DOC_WATERMARK):
    """在整张页面铺满斜 45° 的淡色水印（试用版用）。原地叠加，不改尺寸。"""
    if not text:
        return page
    base = page.convert("RGB")
    W, H = base.size
    wm_font = _doc_font(max(22, round(30 * scale)))

    # 先把一条水印文字画到透明小图上，再旋转 45°，然后平铺整页
    measure = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    tw = int(measure.textlength(text, font=wm_font))
    th = max(28, round(40 * scale))
    tile = Image.new("RGBA", (tw + 20, th + 20), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((10, 6), text, font=wm_font, fill=(150, 150, 150, 70))
    tile = tile.rotate(45, expand=True, resample=Image.BICUBIC)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    step_x = int(tile.width * 0.9)
    step_y = int(tile.height * 1.4)
    if step_x < 10:
        step_x = 10
    if step_y < 10:
        step_y = 10
    row = 0
    y = -tile.height
    while y < H:
        # 隔行错位，平铺更自然
        x = -tile.width + (step_x // 2 if row % 2 else 0)
        while x < W:
            overlay.alpha_composite(tile, (x, y))
            x += step_x
        y += step_y
        row += 1

    out = Image.alpha_composite(base.convert("RGBA"), overlay)
    return out.convert("RGB")


DOC_DPI = 200
A4_PORTRAIT = (1654, 2339)  # 210 × 297 mm @ 200 DPI


def _resize_doc_block(block, ratio):
    if ratio >= 0.999:
        return block
    return block.resize((max(1, round(block.width * ratio)),
                         max(1, round(block.height * ratio))), Image.LANCZOS)


def _compose_a4_page(blocks, page_size, outer, content_h, gap, page_no, style, scale):
    page_w, page_h = page_size
    backgrounds = {"clean": "#ffffff", "classic": "#f7fbf8", "warm": "#fffcf7"}
    page = Image.new("RGB", page_size, backgrounds[style["template"]])
    if len(blocks) > 1:
        gap = min(gap, max(8, (content_h - sum(b.height for b in blocks)) // (len(blocks) - 1)))
    y = outer
    for block in blocks:
        page.paste(block, ((page_w - block.width) // 2, y))
        y += block.height + gap
    draw = ImageDraw.Draw(page)
    footer_font = _doc_font(max(14, round(16 * scale)), style["font_family"])
    footer = f"—  {page_no}  —"
    footer_w = draw.textlength(footer, font=footer_font)
    draw.text(((page_w - footer_w) / 2, outer + content_h + round(18 * scale)),
              footer, fill="#87918c", font=footer_font)
    return page


def build_doc_pages(title, intro, items, watermark=True, size="big", style=None):
    """把标题和图片块排入固定 A4 页面；横竖版均保持标准打印比例。

    当某个内容块只会超出当前页不到 10% 时，自动压缩该页间距和内容，
    将少量尾巴合并回上一页，避免打印出只有一点内容的尾页。
    items 兼容 (img, caption, size, layout, align)。
    """
    style = _doc_style(style)
    portrait = A4_PORTRAIT
    page_size = portrait if style["orientation"] == "portrait" else (portrait[1], portrait[0])
    page_w, page_h = page_size
    scale = DOC_DPI / 150.0
    outer = {"narrow": 82, "normal": 112, "wide": 152}[style["margin"]]
    footer_h = round(58 * scale)
    content_w = page_w - outer * 2
    content_h = page_h - outer * 2 - footer_h
    gap = max(12, round(18 * scale))
    card_pad = round({"narrow": 24, "normal": 40, "wide": 68}[style["margin"]] * scale)
    target_inner = max(200, content_w - card_pad * 2)

    blocks = [render_doc_title(title, intro, target_inner, scale, style=style)]
    for i, it in enumerate(items, 1):
        img, cap = it[0], it[1]
        item_size = it[2] if len(it) > 2 and it[2] else size
        item_layout = it[3] if len(it) > 3 and it[3] in {"auto", "top", "side"} else "auto"
        item_style = dict(style)
        if len(it) > 4 and it[4] in {"left", "center"}:
            item_style["body_align"] = it[4]
        blocks.append(render_doc_card(
            img, cap, i, target_inner, scale, layout=item_layout,
            size=item_size, style=item_style))

    # 所有块先约束到单页内容区内，避免超高截图生成非 A4 页面。
    fitted = []
    for block in blocks:
        ratio = min(1.0, content_w / block.width, content_h / block.height)
        fitted.append(_resize_doc_block(block, ratio))

    groups = []
    current = []
    used = 0
    for block in fitted:
        required = block.height + (gap if current else 0)
        if used + required <= content_h:
            current.append(block)
            used += required
            continue

        overflow = used + required - content_h
        # 只多出不足一页 10%：整页轻微紧凑，避免少量内容被甩到新页。
        if current and overflow <= content_h * 0.10:
            combined = current + [block]
            compact_gap = max(8, gap // 2)
            available = content_h - compact_gap * (len(combined) - 1)
            ratio = min(1.0, available / sum(b.height for b in combined))
            groups.append([_resize_doc_block(b, ratio) for b in combined])
            current, used = [], 0
        else:
            if current:
                groups.append(current)
            current, used = [block], block.height
    if current:
        groups.append(current)

    # 最后一页本身占用不足 10% 时，尽可能并回前页。
    if len(groups) > 1:
        tail_used = sum(b.height for b in groups[-1]) + gap * (len(groups[-1]) - 1)
        if tail_used < content_h * 0.10:
            combined = groups[-2] + groups[-1]
            compact_gap = max(8, gap // 2)
            available = content_h - compact_gap * (len(combined) - 1)
            ratio = min(1.0, available / sum(b.height for b in combined))
            if ratio >= 0.90:
                groups[-2] = [_resize_doc_block(b, ratio) for b in combined]
                groups.pop()

    pages = [_compose_a4_page(group, page_size, outer, content_h, gap, i, style, scale)
             for i, group in enumerate(groups, 1)]
    if watermark:
        pages = [_tile_watermark(page, scale) for page in pages]
    return pages


def build_long_image(title, intro, items, watermark=True, size="big", style=None):
    pages = build_doc_pages(title, intro, items, watermark=watermark, size=size, style=style)
    width = max(p.width for p in pages)
    gap = 24
    total_h = sum(p.height for p in pages) + gap * (len(pages) - 1) + 40
    out = Image.new("RGB", (width, total_h), "#eef2ef")
    y = 20
    for p in pages:
        out.paste(p, ((width - p.width) // 2, y))
        y += p.height + gap
    return out


def build_doc_pdf(path, title, intro, items, watermark=True, size="big", style=None):
    pages = build_doc_pages(title, intro, items, watermark=watermark, size=size, style=style)
    # quality=95 + 不降采样，避免 PIL 存 PDF 时把截图压糊
    pages[0].save(str(path), "PDF", save_all=True, append_images=pages[1:],
                  resolution=float(DOC_DPI), quality=95)


class ExportDocWindow(tk.Toplevel):
    """把多张截图整理成「带说明的长图 / PDF」使用文档。"""

    def __init__(self, owner):
        super().__init__(owner.root)
        self.owner = owner
        self.title("整理成文档（长图 / PDF）")
        self.geometry("820x680")
        self.minsize(700, 560)
        # 不用 transient：transient 的子窗口在 Windows 上没有最大化/最小化按钮。
        # 去掉它，标题栏就有完整的「最小化 / 最大化 / 关闭」三个系统按钮。
        self.configure(bg=COLOR_BG)
        # 双击标题栏或下面这行都能最大化；这里保证窗口可被系统正常最大化
        try:
            self.resizable(True, True)
        except Exception:
            pass
        self.items = []        # [{path, caption, _entry}]
        self.thumb_refs = []

        top = tk.Frame(self, bg=COLOR_BG)
        top.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(top, text="文档标题", bg=COLOR_BG, anchor="w").pack(fill="x")
        self.title_var = tk.StringVar(value="使用说明")
        tk.Entry(top, textvariable=self.title_var).pack(fill="x", pady=(2, 8))
        tk.Label(top, text="整体说明（可选，显示在文档开头）", bg=COLOR_BG, anchor="w").pack(fill="x")
        self.intro_text = tk.Text(top, height=3, wrap="word")
        self.intro_text.pack(fill="x", pady=(2, 0))

        bar = tk.Frame(self, bg=COLOR_BG)
        bar.pack(fill="x", padx=14, pady=8)
        tk.Button(bar, text="添加图片", command=self.add_images).pack(side="left")
        tk.Button(bar, text="加载本轮截图", command=lambda: self.load_free_dir(only_session=True)).pack(side="left", padx=(8, 0))
        tk.Button(bar, text="全部历史截图", command=lambda: self.load_free_dir(only_session=False)).pack(side="left", padx=(8, 0))
        tk.Button(bar, text="清空", command=self.clear_items).pack(side="left", padx=(8, 0))
        self.count_label = tk.Label(bar, text="共 0 张", bg=COLOR_BG, fg=COLOR_MUTED)
        self.count_label.pack(side="right")
        tk.Label(bar, text="每张图可单独选「文档宽度」", bg=COLOR_BG, fg=COLOR_MUTED,
                 font=("Microsoft YaHei UI", 9)).pack(side="right", padx=(0, 10))

        mid = tk.Frame(self, bg=COLOR_BG)
        mid.pack(fill="both", expand=True, padx=14)
        canvas = tk.Canvas(mid, bg=COLOR_BG, highlightthickness=0)
        self._list_canvas = canvas
        scroll = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        self.list_frame = tk.Frame(canvas, bg=COLOR_BG)
        self.list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._list_window = canvas.create_window((0, 0), window=self.list_frame, anchor="nw", width=720)
        # 行宽跟随 canvas 实际宽度，保证右侧按钮组在任何窗口尺寸下都贴右可见
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(self._list_window, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # 鼠标滚轮滚动：鼠标移入整理窗口时全局绑定，移出时解绑（不影响主窗口）
        def _on_wheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
            return "break"
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", _on_wheel))
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))
        # 关窗时确保解绑，避免残留全局钩子
        self.bind("<Destroy>", lambda e: (self.unbind_all("<MouseWheel>") if e.widget is self else None))

        bottom = tk.Frame(self, bg=COLOR_BG)
        bottom.pack(fill="x", padx=14, pady=12)
        self.status_var = tk.StringVar(value="添加截图 → 给每张填一句说明 → 导出长图或 PDF。")
        tk.Label(bottom, textvariable=self.status_var, bg=COLOR_BG, fg=COLOR_GREEN, anchor="w").pack(fill="x", pady=(0, 8))
        tk.Button(bottom, text="导出长图", command=self.export_long, bg=COLOR_GREEN, fg="#ffffff",
                  bd=0, relief="flat", cursor="hand2", padx=16, pady=8,
                  font=("Microsoft YaHei UI", 10, "bold")).pack(side="right")
        tk.Button(bottom, text="导出 PDF", command=self.export_pdf, bg=COLOR_GREEN, fg="#ffffff",
                  bd=0, relief="flat", cursor="hand2", padx=16, pady=8,
                  font=("Microsoft YaHei UI", 10, "bold")).pack(side="right", padx=(0, 8))
        # 打开整理文档时，自动把「本轮」自由截图加载进来（用户的核心诉求：
        # 默认只整理这一轮截的图，不用每次手动加载、也不会混入历史图）
        loaded = self.load_free_dir(only_session=True, silent=True)
        if loaded:
            self.status_var.set(f"已自动载入本轮 {loaded} 张截图，可拖动排序、填说明或点 ✨AI描述。")
        self.render_list()

    def _sync_captions(self):
        for it in self.items:
            entry = it.get("_entry")
            if entry is not None:
                try:
                    # Text 多行框：取全部内容并去掉末尾换行
                    it["caption"] = entry.get("1.0", "end").strip()
                except tk.TclError:
                    pass
            hint_entry = it.get("_hint_entry")
            if hint_entry is not None:
                try:
                    it["hint"] = hint_entry.get().strip()
                except tk.TclError:
                    pass

    def add_images(self):
        names = filedialog.askopenfilenames(
            parent=self, title="选择截图",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp"), ("所有文件", "*.*")])
        if not names:
            return
        self._sync_captions()
        for n in names:
            self.items.append({"path": Path(n), "caption": ""})
        self.render_list()

    def load_free_dir(self, only_session=True, silent=False):
        """加载自由截图。
        only_session=True（默认）：只加载「本轮」自由截图（最近一次开启自由截图后截的），
                                  避免把历史所有截图都塞进来。
        only_session=False：加载目录里全部历史截图。"""
        folder = Path(self.owner.output_dir_var.get()) / "自由截图"
        if not folder.exists():
            if not silent:
                messagebox.showinfo("整理文档", "还没有「自由截图」目录，先去截几张图。", parent=self)
            return 0

        # 本轮截图：优先用主程序记录的本轮文件列表；没有就按本轮起点时间过滤
        session_files = list(getattr(self.owner, "free_session_files", []) or [])
        session_start = getattr(self.owner, "free_session_start", None)

        all_jpg = sorted(folder.glob("*.jpg"))
        if only_session:
            if session_files:
                paths = [p for p in session_files if Path(p).exists()]
            elif session_start:
                paths = [p for p in all_jpg if p.stat().st_mtime >= session_start]
            else:
                paths = []  # 还没截过本轮 → 不自动塞历史图
        else:
            paths = all_jpg

        if not paths:
            if not silent:
                tip = "这一轮还没有自由截图。点「自由截图」去截几张，或点「全部历史截图」加载以前的。" \
                      if only_session else "「自由截图」目录是空的。"
                messagebox.showinfo("整理文档", tip, parent=self)
            return 0

        self._sync_captions()
        # 去重：已在列表里的不重复加
        existing = {str(Path(it["path"]).resolve()) for it in self.items}
        added = 0
        for p in paths:
            if str(Path(p).resolve()) in existing:
                continue
            self.items.append({"path": Path(p), "caption": ""})
            added += 1
        self.render_list()
        scope = "本轮" if only_session else "全部"
        self.status_var.set(f"已加载{scope} {added} 张自由截图。")
        return added

    def clear_items(self):
        self.items = []
        self.render_list()

    def move(self, i, delta):
        self._sync_captions()
        j = i + delta
        if 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self.render_list()

    def remove(self, i):
        self._sync_captions()
        del self.items[i]
        self.render_list()

    def render_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.thumb_refs = []
        self._row_frames = []
        for i, it in enumerate(self.items):
            row = tk.Frame(self.list_frame, bg=COLOR_CARD, highlightbackground="#dde7e1", highlightthickness=1)
            row.pack(fill="x", pady=3)
            self._row_frames.append(row)

            # 两段式布局，彻底避免横向溢出：
            #   左块（固定宽）= 手柄 + 序号 + 缩略图 + 操作按钮组（按钮在缩略图下方竖排）
            #   右块（fill x）= 多行说明框
            # 第 1 列：拖动手柄 + 序号（竖排，窄）
            grip = tk.Frame(row, bg=COLOR_CARD)
            grip.pack(side="left", padx=(4, 0), pady=4)
            handle = tk.Label(grip, text="⠿", bg=COLOR_CARD, fg=COLOR_MUTED,
                              font=("Microsoft YaHei UI", 14), cursor="fleur", width=2)
            handle.pack(side="top")
            seq = tk.Label(grip, text=str(i + 1), bg=COLOR_CARD, fg=COLOR_MUTED, width=2,
                           font=("Microsoft YaHei UI", 11, "bold"))
            seq.pack(side="top", pady=(2, 0))

            # 第 2 列：大预览图（512 上限），方便看清内容再写描述
            photo = self._thumb_cache.get(str(it["path"])) if hasattr(self, "_thumb_cache") else None
            if photo is None:
                try:
                    thumb = Image.open(it["path"])
                    thumb.thumbnail((512, 512))
                    photo = ImageTk.PhotoImage(thumb)
                    if not hasattr(self, "_thumb_cache"):
                        self._thumb_cache = {}
                    self._thumb_cache[str(it["path"])] = photo
                except Exception:
                    photo = None
            if photo is not None:
                self.thumb_refs.append(photo)
                thumb_lbl = tk.Label(row, image=photo, bg=COLOR_CARD)
                thumb_lbl.pack(side="left", padx=8, pady=4)
            else:
                thumb_lbl = tk.Label(row, text="图片打不开", bg=COLOR_CARD, fg=COLOR_MUTED, width=12)
                thumb_lbl.pack(side="left", padx=8, pady=4)

            # 第 3 列：提示框 + 说明框 + 操作按钮（竖排，填满剩余宽度）
            right = tk.Frame(row, bg=COLOR_CARD)
            right.pack(side="left", fill="both", expand=True, padx=6, pady=6)

            # 操作按钮一排（AI / ↑ / ↓ / ✕）
            btns = tk.Frame(right, bg=COLOR_CARD)
            btns.pack(fill="x")
            ai_btn = tk.Button(btns, text="✨ AI 描述这张图", command=lambda i=i: self._ai_describe(i),
                               bd=0, bg=COLOR_GREEN_SOFT, fg=COLOR_GREEN_DARK,
                               activebackground="#d7f3e3", cursor="hand2",
                               font=("Microsoft YaHei UI", 10, "bold"), padx=10, pady=3)
            ai_btn.pack(side="left")
            it["_ai_btn"] = ai_btn

            # 每张图单独选在文档里的宽度（A4 比例），改了立即写回该 item
            tk.Label(btns, text="文档宽度", bg=COLOR_CARD, fg=COLOR_MUTED,
                     font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(12, 2))
            sz_label = {"full": "全宽", "two_third": "三分之二",
                        "half": "二分之一", "quarter": "四分之一"}.get(it.get("size", "full"), "全宽")
            sz_var = tk.StringVar(value=sz_label)
            it["_size_var"] = sz_var
            def _on_size(idx=i, var=sz_var):
                m = {"全宽": "full", "三分之二": "two_third", "二分之一": "half", "四分之一": "quarter"}
                self.items[idx]["size"] = m.get(var.get(), "full")
            cb = ttk.Combobox(btns, textvariable=sz_var, state="readonly", width=8,
                              values=["全宽", "三分之二", "二分之一", "四分之一"])
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", lambda e, f=_on_size: f())

            tk.Button(btns, text="✕ 删除", command=lambda i=i: self.remove(i), bd=0, bg=COLOR_CARD,
                      fg="#c0392b", cursor="hand2", padx=8,
                      font=("Microsoft YaHei UI", 9)).pack(side="right")
            tk.Button(btns, text="↓", command=lambda i=i: self.move(i, 1), bd=0, bg=COLOR_CARD,
                      width=2, cursor="hand2").pack(side="right")
            tk.Button(btns, text="↑", command=lambda i=i: self.move(i, -1), bd=0, bg=COLOR_CARD,
                      width=2, cursor="hand2").pack(side="right")

            # 提示框（单行）
            hint_row = tk.Frame(right, bg=COLOR_CARD)
            hint_row.pack(fill="x", pady=(6, 0))
            tk.Label(hint_row, text="给AI的提示：", bg=COLOR_CARD, fg=COLOR_MUTED,
                     font=("Microsoft YaHei UI", 9)).pack(side="left")
            hint_entry = tk.Entry(hint_row, font=("Microsoft YaHei UI", 10),
                                  relief="solid", bd=1, width=42)
            hint_entry.insert(0, it.get("hint", ""))
            hint_entry.pack(side="left", padx=(2, 0))
            it["_hint_entry"] = hint_entry

            # 说明文字（最终进文档）；AI 描述结果填到这里。
            # 限定宽度（width=46 字符），不撑满整屏，读写更舒适。
            entry = tk.Text(right, height=5, width=46, wrap="word", font=("Microsoft YaHei UI", 10),
                            relief="solid", bd=1, highlightthickness=0)
            entry.insert("1.0", it.get("caption", ""))
            entry.pack(anchor="w", pady=(4, 0))
            it["_entry"] = entry

            # 在手柄、序号、缩略图上启用拖拽重排（避开 Entry，免得抢输入焦点）
            for w in (handle, seq, thumb_lbl):
                w.bind("<ButtonPress-1>", lambda e, i=i: self._drag_start(i))
                w.bind("<B1-Motion>", self._drag_motion)
                w.bind("<ButtonRelease-1>", self._drag_drop)
        self.count_label.configure(text=f"共 {len(self.items)} 张")

    # ───── 鼠标拖拽重排 ─────
    def _drag_start(self, index):
        self._drag_index = index
        self._drag_target = index
        # 高亮被拖的行
        try:
            self._row_frames[index].configure(highlightbackground=COLOR_GREEN, highlightthickness=2)
        except Exception:
            pass

    def _drag_motion(self, event):
        if getattr(self, "_drag_index", None) is None:
            return
        # 鼠标在 list_frame 里的绝对 y，落在哪一行就把那行标为目标
        try:
            y_root = event.y_root
            target = self._drag_index
            for idx, row in enumerate(self._row_frames):
                top = row.winfo_rooty()
                bottom = top + row.winfo_height()
                if top <= y_root <= bottom:
                    target = idx
                    break
            else:
                # 拖到最顶/最底之外
                if self._row_frames and y_root < self._row_frames[0].winfo_rooty():
                    target = 0
                elif self._row_frames:
                    target = len(self._row_frames) - 1
            if target != getattr(self, "_drag_target", target):
                # 更新落点提示高亮
                for idx, row in enumerate(self._row_frames):
                    if idx == self._drag_index:
                        continue
                    hl = COLOR_CYAN if idx == target else "#dde7e1"
                    th = 2 if idx == target else 1
                    try:
                        row.configure(highlightbackground=hl, highlightthickness=th)
                    except Exception:
                        pass
                self._drag_target = target
        except Exception:
            pass

    def _drag_drop(self, event):
        src = getattr(self, "_drag_index", None)
        dst = getattr(self, "_drag_target", None)
        self._drag_index = None
        self._drag_target = None
        if src is None or dst is None or src == dst:
            self.render_list()  # 复位高亮
            return
        self._sync_captions()
        item = self.items.pop(src)
        self.items.insert(dst, item)
        self.render_list()

    # ───── AI 图片描述 ─────
    def _ai_describe(self, index):
        """对某张图调用后端 AI：结合用户已填的简介，生成详细说明并回填。"""
        self._sync_captions()
        if not (0 <= index < len(self.items)):
            return
        it = self.items[index]
        token = getattr(self.owner, "server_token", "")
        if not token:
            messagebox.showinfo(
                "AI 描述",
                "还没登记软件编号，无法使用 AI 描述。\n请先在主界面登记/同步设备。",
                parent=self)
            return

        path = Path(it["path"])
        # 优先用「给AI的提示」框；没填则退回用已有说明文字当提示
        hint = it.get("hint", "").strip() or it.get("caption", "").strip()
        server_url = self.owner.server_url_var.get()

        # 禁用按钮 + 提示，后台线程跑，避免卡界面
        btn = it.get("_ai_btn")
        if btn is not None:
            try:
                btn.configure(state="disabled", text="生成中…")
            except tk.TclError:
                pass
        self.status_var.set(f"正在为第 {index + 1} 张图生成 AI 描述…")

        def worker():
            try:
                result = server_describe_image(server_url, token, path, hint=hint, style="detail")
                desc = result.get("description", "").strip()
                self.after(0, lambda: self._apply_ai_desc(index, desc, result))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._ai_desc_failed(index, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_ai_desc(self, index, desc, result):
        if not (0 <= index < len(self.items)):
            return
        if not desc:
            self._ai_desc_failed(index, "AI 返回了空描述，请重试。")
            return
        # 回填到数据 + 输入框
        self.items[index]["caption"] = desc
        entry = self.items[index].get("_entry")
        if entry is not None:
            try:
                entry.delete("1.0", "end")
                entry.insert("1.0", desc)
            except tk.TclError:
                pass
        btn = self.items[index].get("_ai_btn")
        if btn is not None:
            try:
                btn.configure(state="normal", text="✨重写")
            except tk.TclError:
                pass
        charged = result.get("charged")
        tail = "（已扣 1 次额度）" if charged else "（当前免费）"
        self.status_var.set(f"第 {index + 1} 张图 AI 描述已生成 {tail}")

    def _ai_desc_failed(self, index, msg):
        btn = None
        if 0 <= index < len(self.items):
            btn = self.items[index].get("_ai_btn")
        if btn is not None:
            try:
                btn.configure(state="normal", text="✨AI描述")
            except tk.TclError:
                pass
        self.status_var.set("AI 描述失败。")
        messagebox.showwarning("AI 描述", f"生成失败：{msg}", parent=self)

    def _collect(self):
        self._sync_captions()
        loaded = []
        for it in self.items:
            try:
                with Image.open(it["path"]) as im:
                    # 每张图带自己的尺寸档位（默认 full）
                    loaded.append((im.convert("RGB"), it.get("caption", ""), it.get("size", "full")))
            except Exception as exc:
                self.owner.log(f"读取图片失败 {Path(it['path']).name}：{exc}")
        return loaded

    def _out_dir(self):
        folder = Path(self.owner.output_dir_var.get()) / "文档"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def export_long(self):
        items = self._collect()
        if not items:
            messagebox.showinfo("整理文档", "请先添加截图。", parent=self)
            return
        try:
            wm = not bool(getattr(self.owner, "is_paid_user", False))
            image = build_long_image(self.title_var.get(), self.intro_text.get("1.0", "end").strip(), items, watermark=wm)
            name = safe_folder_name(self.title_var.get(), "使用说明")
            out = self._out_dir() / f"{name}_{time.strftime('%Y%m%d-%H%M%S')}.jpg"
            image.save(out, "JPEG", quality=92)
            self.status_var.set(f"已导出长图：{out.name}")
            self.owner.log(f"已导出长图：{out}")
            os.startfile(str(out.parent))
        except Exception as exc:
            messagebox.showerror("整理文档", f"导出长图失败：{exc}", parent=self)
            write_error_log(f"导出长图失败：{exc}")

    def export_pdf(self):
        items = self._collect()
        if not items:
            messagebox.showinfo("整理文档", "请先添加截图。", parent=self)
            return
        try:
            name = safe_folder_name(self.title_var.get(), "使用说明")
            out = self._out_dir() / f"{name}_{time.strftime('%Y%m%d-%H%M%S')}.pdf"
            wm = not bool(getattr(self.owner, "is_paid_user", False))
            build_doc_pdf(out, self.title_var.get(), self.intro_text.get("1.0", "end").strip(), items, watermark=wm)
            self.status_var.set(f"已导出 PDF：{out.name}")
            self.owner.log(f"已导出 PDF：{out}")
            os.startfile(str(out.parent))
        except Exception as exc:
            messagebox.showerror("整理文档", f"导出 PDF 失败：{exc}", parent=self)
            write_error_log(f"导出 PDF 失败：{exc}")


class FreePanel(tk.Toplevel):
    """自由截图模式的置顶小浮窗：显示已截数量 + 打开目录 / 结束 / 显示主程序。"""

    def __init__(self, owner):
        super().__init__(owner.root)
        self.owner = owner
        self.title("自由截图")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)
        self.protocol("WM_DELETE_WINDOW", owner.stop_free)

        frame = tk.Frame(self, bg=COLOR_CARD, padx=14, pady=12,
                         highlightbackground="#c9d7cf", highlightthickness=1)
        frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        frame.columnconfigure(0, weight=1, uniform="half")
        frame.columnconfigure(1, weight=1, uniform="half")

        tk.Label(frame, text="●  自由截图中", bg=COLOR_CARD, fg=COLOR_GREEN,
                 font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(frame, textvariable=owner.free_count_var, bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Microsoft YaHei UI", 11, "bold"), anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        tk.Label(frame, text="按住 Ctrl + 鼠标拖动框选，松开自动保存", bg=COLOR_CARD, fg=COLOR_MUTED,
                 font=("Microsoft YaHei UI", 9), anchor="w", wraplength=230, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tk.Button(frame, text="打开目录", command=owner.open_free_dir,
                  bg="#eef3f0", fg=COLOR_TEXT, bd=0, relief="flat", cursor="hand2",
                  font=("Microsoft YaHei UI", 10), padx=10, pady=8).grid(
            row=3, column=0, sticky="ew", padx=(0, 4))
        tk.Button(frame, text="结束自由截图", command=owner.stop_free,
                  bg=COLOR_GREEN, fg="#ffffff", activebackground=COLOR_GREEN_DARK,
                  activeforeground="#ffffff", bd=0, relief="flat", cursor="hand2",
                  font=("Microsoft YaHei UI", 10, "bold"), padx=10, pady=8).grid(
            row=3, column=1, sticky="ew", padx=(4, 0))
        tk.Button(frame, text="显示主程序", command=owner.show_main,
                  bg="#eef3f0", fg=COLOR_TEXT, bd=0, relief="flat", cursor="hand2",
                  font=("Microsoft YaHei UI", 9), padx=10, pady=6).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        self.geometry(f"+{sw - self.winfo_width() - 40}+60")


class FloatPanel(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner.root)
        self.owner = owner
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)
        self.protocol("WM_DELETE_WINDOW", owner.stop_work)

        frame = tk.Frame(self, bg=COLOR_CARD, padx=14, pady=12,
                         highlightbackground="#c9d7cf", highlightthickness=1)
        frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        frame.columnconfigure(0, weight=1, uniform="half")
        frame.columnconfigure(1, weight=1, uniform="half")

        title_row = tk.Frame(frame, bg=COLOR_CARD)
        title_row.grid(row=0, column=0, columnspan=2, sticky="ew")
        title_row.columnconfigure(0, weight=1)
        tk.Label(title_row, text="●  截图中", bg=COLOR_CARD, fg=COLOR_GREEN,
                 font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Button(title_row, text="结束 ✕", command=owner.stop_work, bd=0, bg=COLOR_CARD,
                  fg=COLOR_MUTED, activebackground="#f1f5f9", cursor="hand2",
                  font=("Microsoft YaHei UI", 9)).grid(row=0, column=1)

        tk.Label(frame, textvariable=owner.panel_name_var, bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Microsoft YaHei UI", 12, "bold"), anchor="w", wraplength=230,
                 justify="left").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 2))
        tk.Label(frame, textvariable=owner.panel_progress_var, bg=COLOR_CARD, fg=COLOR_MUTED,
                 font=("Microsoft YaHei UI", 9), anchor="w", wraplength=230,
                 justify="left").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        self.main_btn = self._panel_button(frame, "▣  主图", lambda: owner.set_category(MAIN_CATEGORY),
                                           row=3, column=0, padx=(0, 4))
        self.detail_btn = self._panel_button(frame, "☰  详情", lambda: owner.set_category(DETAIL_CATEGORY),
                                             row=3, column=1, padx=(4, 0))

        self.next_btn = tk.Button(frame, text="下一行  ▶", command=owner.next_row_manual,
                                  bg=COLOR_GREEN, fg="#ffffff", activebackground=COLOR_GREEN_DARK,
                                  activeforeground="#ffffff", bd=0, relief="flat", cursor="hand2",
                                  font=("Microsoft YaHei UI", 12, "bold"), padx=12, pady=10)
        self.next_btn.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        self.copy_btn = self._panel_button(frame, "复制上一行", owner.copy_previous,
                                           row=5, column=0, padx=(0, 4))
        self.reopen_btn = self._panel_button(frame, "重开链接", owner.open_current_link,
                                             row=5, column=1, padx=(4, 0))
        self.show_btn = self._panel_button(frame, "显示主程序", owner.show_main,
                                           row=6, column=0, columnspan=2)

        tk.Label(frame, text="按住 Ctrl + 鼠标拖动框选截图", bg=COLOR_CARD, fg=COLOR_MUTED,
                 font=("Microsoft YaHei UI", 9), anchor="center").grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        self.geometry(f"+{screen_w - self.winfo_width() - 40}+60")
        self.refresh_category()

    def _panel_button(self, parent, text, command, row, column=0, columnspan=1, padx=0):
        button = tk.Button(parent, text=text, command=command,
                           bg="#ffffff", fg=COLOR_TEXT, activebackground="#f8fafc",
                           activeforeground=COLOR_TEXT, bd=0, relief="flat", cursor="hand2",
                           highlightbackground="#d7ded9", highlightthickness=1,
                           font=("Microsoft YaHei UI", 10), padx=10, pady=7)
        button.grid(row=row, column=column, columnspan=columnspan, sticky="ew", padx=padx, pady=(0, 8))
        return button

    def refresh_category(self):
        active = self.owner.category_var.get()
        for btn, name in ((self.main_btn, MAIN_CATEGORY), (self.detail_btn, DETAIL_CATEGORY)):
            try:
                if name == active:
                    btn.configure(bg=COLOR_GREEN_SOFT, fg=COLOR_GREEN, highlightbackground=COLOR_GREEN,
                                  font=("Microsoft YaHei UI", 10, "bold"))
                else:
                    btn.configure(bg="#ffffff", fg=COLOR_TEXT, highlightbackground="#d7ded9",
                                  font=("Microsoft YaHei UI", 10))
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


class ManualRepairDialog(tk.Toplevel):
    """缩略图人工勾选窗口：跳过 AI 检测，用户自己选择要修复的图片。"""

    def __init__(self, owner, captures: list, mode_label: str):
        super().__init__(owner.root)
        self.owner = owner
        self.mode_label = mode_label
        self.title(f"选择要{mode_label}的图片")
        self.geometry("940x680")
        self.minsize(760, 520)
        self.transient(owner.root)
        self.result: list | None = None
        self.items = []
        self.photos = []

        for capture in captures:
            path = capture["path"]
            self.items.append({
                "path": path,
                "name": str(capture.get("name") or path.parent.name),
                "var": tk.BooleanVar(value=False),
            })

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(
            self,
            text=f"人工勾选需要「{mode_label}」的图片。只会处理你勾选的图片，不再做 AI 检测。",
            style="Hint.TLabel",
            wraplength=880,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        holder = ttk.Frame(self)
        holder.grid(row=1, column=0, sticky="nsew", padx=16)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(holder, bg=COLOR_BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        bar.columnconfigure(5, weight=1)
        ttk.Button(bar, text="全选", command=self.select_all).grid(row=0, column=0)
        ttk.Button(bar, text="全不选", command=self.clear_all).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(bar, text="反选", command=self.invert_selection).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(bar, text="打开选中", command=self.open_selected).grid(row=0, column=3, padx=(8, 0))
        self.count_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.count_var, style="Hint.TLabel").grid(row=0, column=5, sticky="e")

        action = ttk.Frame(self)
        action.grid(row=3, column=0, sticky="ew", padx=16, pady=14)
        action.columnconfigure(0, weight=1)
        ttk.Button(action, text="取消", command=self._cancel).grid(row=0, column=1)
        ttk.Button(action, text="确认修复", style="Accent.TButton", command=self._confirm).grid(
            row=0, column=2, padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.render_items()
        self.update_count()

    def render_items(self):
        columns = 4
        for col in range(columns):
            self.grid_frame.columnconfigure(col, weight=1, uniform="thumb")

        for index, item in enumerate(self.items):
            row, col = divmod(index, columns)
            card = tk.Frame(
                self.grid_frame,
                bg=COLOR_CARD,
                padx=8,
                pady=8,
                highlightbackground=COLOR_BORDER,
                highlightthickness=1,
            )
            card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            card.columnconfigure(0, weight=1)

            image_label = tk.Label(card, bg=COLOR_CARD, cursor="hand2")
            image_label.grid(row=0, column=0, sticky="nsew")
            self._set_thumbnail(image_label, item["path"])
            image_label.bind("<Button-1>", lambda _event, i=index: self.toggle(i))
            image_label.bind("<Double-1>", lambda _event, i=index: self.open_item(i))

            cb = ttk.Checkbutton(
                card,
                variable=item["var"],
                command=self.update_count,
                text=item["path"].name,
            )
            cb.grid(row=1, column=0, sticky="w", pady=(8, 0))
            ttk.Label(
                card,
                text=item["name"],
                style="CardHint.TLabel",
                wraplength=180,
            ).grid(row=2, column=0, sticky="w", pady=(2, 0))
            item["var"].trace_add("write", lambda *_args: self.update_count())

    def _set_thumbnail(self, label, path: Path):
        try:
            with Image.open(path) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image.thumbnail((180, 140), Image.LANCZOS)
                thumb = ImageTk.PhotoImage(image)
            label.configure(image=thumb, width=180, height=140)
            label.image = thumb
            self.photos.append(thumb)
        except Exception:
            label.configure(
                text="无法预览\n"+path.name,
                width=22,
                height=8,
                fg="#b91c1c",
                justify="center",
            )

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        if not self.winfo_exists():
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def toggle(self, index: int):
        item = self.items[index]
        item["var"].set(not item["var"].get())

    def selected_items(self) -> list:
        return [item for item in self.items if item["var"].get()]

    def update_count(self):
        count = len(self.selected_items())
        self.count_var.set(f"已选 {count}/{len(self.items)} 张；成功修复每张扣 1 张额度")

    def select_all(self):
        for item in self.items:
            item["var"].set(True)
        self.update_count()

    def clear_all(self):
        for item in self.items:
            item["var"].set(False)
        self.update_count()

    def invert_selection(self):
        for item in self.items:
            item["var"].set(not item["var"].get())
        self.update_count()

    def open_item(self, index: int):
        try:
            os.startfile(str(self.items[index]["path"]))
        except Exception as exc:
            messagebox.showinfo(APP_NAME, f"无法打开图片：{exc}", parent=self)

    def open_selected(self):
        selected = self.selected_items()
        if not selected:
            messagebox.showinfo(APP_NAME, "请先勾选一张图片。", parent=self)
            return
        self.open_item(self.items.index(selected[0]))

    def _confirm(self):
        selected = self.selected_items()
        if not selected:
            messagebox.showinfo(APP_NAME, "请先勾选需要修复的图片。", parent=self)
            return
        if self.mode_label == "白底上图":
            if not messagebox.askyesno(
                    APP_NAME,
                    "「白底上图」会把背景和画面氛围改成电商白底主图。\n\n"
                    "适合直接做上架主图；如果必须保留原场景，请选择更窄的修复类型。\n\n"
                    "确定继续使用「白底上图」吗？",
                    parent=self):
                return
        if not messagebox.askyesno(
                APP_NAME,
                f"确定用「{self.mode_label}」处理 {len(selected)} 张图吗？\n\n"
                f"成功处理每张扣 1 张图片额度，本次最多扣除 {len(selected)} 张。",
                parent=self):
            return
        self.canvas.unbind_all("<MouseWheel>")
        self.result = [item["path"] for item in selected]
        self.destroy()

    def _cancel(self):
        self.canvas.unbind_all("<MouseWheel>")
        self.result = None
        self.destroy()


# ---------------- 结果核对（原图/修改后对比）对话框 ----------------

class ResultReviewDialog(tk.Toplevel):
    """修复完成后弹出：原图 → 修改后 并排滚动核对，勾选不满意的一键二次修复。"""

    def __init__(self, owner, results: list, mode_label: str):
        super().__init__(owner.root)
        self.owner = owner
        self.mode_label = mode_label
        self.title("结果核对")
        self.geometry("1040x720")
        self.minsize(820, 560)
        self.transient(owner.root)
        self.action = "done"          # "done" 或 "rerun"
        self.selected: list = []       # 需要二次修复的 after 路径（Path）
        self.items = []
        self.photos = []

        for record in results:
            self.items.append({
                "before": Path(record["before"]) if record.get("before") else None,
                "after": Path(record["after"]),
                "name": str(record.get("name") or ""),
                "round": int(record.get("round", 1)),
                "var": tk.BooleanVar(value=False),
            })

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(
            self,
            text=f"已完成「{mode_label}」{len(self.items)} 张。左为原图、右为修改后；"
                 f"勾选不满意的，点「二次修复」会再处理一次（每张再扣 1 张额度）。",
            style="Hint.TLabel",
            wraplength=980,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        holder = ttk.Frame(self)
        holder.grid(row=1, column=0, sticky="nsew", padx=16)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(holder, bg=COLOR_BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        bar.columnconfigure(3, weight=1)
        ttk.Button(bar, text="全选", command=self.select_all).grid(row=0, column=0)
        ttk.Button(bar, text="全不选", command=self.clear_all).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(bar, text="打开结果", command=self.open_selected).grid(row=0, column=2, padx=(8, 0))
        self.count_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.count_var, style="Hint.TLabel").grid(row=0, column=3, sticky="e")

        action = ttk.Frame(self)
        action.grid(row=3, column=0, sticky="ew", padx=16, pady=14)
        action.columnconfigure(0, weight=1)
        self.rerun_button = ttk.Button(action, text="二次修复选中", command=self._rerun)
        self.rerun_button.grid(row=0, column=1)
        ttk.Button(action, text="完成", style="Accent.TButton", command=self._done).grid(
            row=0, column=2, padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self._done)
        self.render_items()
        self.update_count()

    def render_items(self):
        columns = 3
        for col in range(columns):
            self.grid_frame.columnconfigure(col, weight=1, uniform="cmp")

        for index, item in enumerate(self.items):
            row, col = divmod(index, columns)
            card = tk.Frame(self.grid_frame, bg=COLOR_CARD, padx=8, pady=8,
                            highlightbackground=COLOR_BORDER, highlightthickness=1)
            card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            card.columnconfigure(0, weight=1)

            pair = tk.Frame(card, bg=COLOR_CARD)
            pair.grid(row=0, column=0, sticky="nsew")
            pair.columnconfigure(0, weight=1)
            pair.columnconfigure(2, weight=1)

            before_box = tk.Frame(pair, bg=COLOR_CARD)
            before_box.grid(row=0, column=0)
            tk.Label(before_box, text="原图", bg=COLOR_CARD, fg=COLOR_MUTED,
                     font=("Microsoft YaHei UI", 8)).grid(row=0, column=0)
            blabel = tk.Label(before_box, bg=COLOR_CARD)
            blabel.grid(row=1, column=0)
            self._set_thumbnail(blabel, item["before"], "原图缺失")

            tk.Label(pair, text="→", bg=COLOR_CARD, fg=COLOR_GREEN,
                     font=("Microsoft YaHei UI", 14, "bold")).grid(row=0, column=1, padx=4)

            after_box = tk.Frame(pair, bg=COLOR_CARD)
            after_box.grid(row=0, column=2)
            tk.Label(after_box, text="修改后", bg=COLOR_CARD, fg=COLOR_GREEN,
                     font=("Microsoft YaHei UI", 8, "bold")).grid(row=0, column=0)
            alabel = tk.Label(after_box, bg=COLOR_CARD, cursor="hand2")
            alabel.grid(row=1, column=0)
            self._set_thumbnail(alabel, item["after"], "无法预览")
            alabel.bind("<Double-1>", lambda _e, i=index: self.open_item(i))

            round_tag = f"（已修 {item['round']} 次）" if item["round"] > 1 else ""
            cb = ttk.Checkbutton(card, variable=item["var"], command=self.update_count,
                                 text=f"需要二次修复{round_tag}")
            cb.grid(row=1, column=0, sticky="w", pady=(8, 0))
            ttk.Label(card, text=f"{item['name']} / {item['after'].name}",
                      style="CardHint.TLabel", wraplength=280).grid(row=2, column=0, sticky="w", pady=(2, 0))

    def _set_thumbnail(self, label, path, missing_text: str):
        if not path or not Path(path).exists():
            label.configure(text=missing_text, width=18, height=7, fg=COLOR_MUTED,
                            justify="center", bg=COLOR_CARD)
            return
        try:
            with Image.open(path) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image.thumbnail((150, 130), Image.LANCZOS)
                thumb = ImageTk.PhotoImage(image)
            label.configure(image=thumb, width=150, height=130)
            label.image = thumb
            self.photos.append(thumb)
        except Exception:
            label.configure(text="无法预览", width=18, height=7, fg="#b91c1c", justify="center")

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        if not self.winfo_exists():
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def selected_items(self) -> list:
        return [item for item in self.items if item["var"].get()]

    def update_count(self):
        count = len(self.selected_items())
        self.count_var.set(f"已选 {count}/{len(self.items)} 张需二次修复；成功每张扣 1 张额度")

    def select_all(self):
        for item in self.items:
            item["var"].set(True)
        self.update_count()

    def clear_all(self):
        for item in self.items:
            item["var"].set(False)
        self.update_count()

    def open_item(self, index: int):
        try:
            os.startfile(str(self.items[index]["after"]))
        except Exception as exc:
            messagebox.showinfo(APP_NAME, f"无法打开图片：{exc}", parent=self)

    def open_selected(self):
        selected = self.selected_items()
        target = selected[0] if selected else (self.items[0] if self.items else None)
        if not target:
            return
        self.open_item(self.items.index(target))

    def _rerun(self):
        selected = self.selected_items()
        if not selected:
            messagebox.showinfo(APP_NAME, "请先勾选需要二次修复的图片。", parent=self)
            return
        if not messagebox.askyesno(
                APP_NAME,
                f"对勾选的 {len(selected)} 张再做一次「{self.mode_label}」吗？\n\n"
                f"会在当前结果上继续处理，成功每张再扣 1 张图片额度。", parent=self):
            return
        self.canvas.unbind_all("<MouseWheel>")
        self.action = "rerun"
        self.selected = [item["after"] for item in selected]
        self.destroy()

    def _done(self):
        self.canvas.unbind_all("<MouseWheel>")
        self.action = "done"
        self.destroy()


# ---------------- 主程序 ----------------

class SnapSaverApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1200x740")
        self.root.minsize(1120, 640)

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
        self.frozen_image = None
        self.grabbing = False
        self.hook_polling = False
        self.busy = False
        self.stop_event = threading.Event()
        self.temp_dir = None
        self.ai_thread = None
        self.ai_events: queue.Queue = queue.Queue()
        # 「结果核对」对比窗状态
        self.review_results: list = []      # [{name, before, after, round}]
        self.review_mode_key = DEFAULT_REPAIR_MODE
        self.review_mode_label = repair_mode_label(DEFAULT_REPAIR_MODE)

        self.server_url_var = tk.StringVar(value=str(config.get("server_url") or os.environ.get("HAOBANFA_SERVER_URL", DEFAULT_SERVER_URL)))
        # 编号每次按本机网卡实时算，不读配置里的旧值（防止拷贝软件目录导致多机同号）；
        # 旧编号仅留作一次性迁移上报，让老用户的额度平滑过渡到新编号。
        self.software_id_var = tk.StringVar(value=local_software_id())
        self.legacy_software_id = str(config.get("software_id") or "").strip()
        self.server_token = str(config.get("server_token") or os.environ.get("HAOBANFA_TOKEN", "")).strip()
        self.output_dir_var = tk.StringVar(value=str(Path(saved_out) if saved_out else app_dir() / "存图结果"))
        self.free_count_var = tk.StringVar(value="本次自由截图：0 张")
        self.free_mode = False
        self.free_count = 0
        self.free_panel = None
        # 本轮自由截图的起点时间戳（整理文档时默认只加载这之后截的图）
        self.free_session_start = None
        self.free_session_files = []  # 本轮截的图路径（按顺序）
        self.main_count_var = tk.IntVar(value=int(config.get("main_count", 1) or 1))
        self.detail_count_var = tk.IntVar(value=int(config.get("detail_count", 3) or 3))
        self.prefix_var = tk.StringVar(value=str(config.get("prefix", "pic")))
        self.quality_var = tk.IntVar(value=int(config.get("quality", 95) or 95))
        self.auto_open_var = tk.BooleanVar(value=bool(config.get("auto_open", True)))
        self.repair_mode_var = tk.StringVar(value=repair_mode_label(str(config.get("repair_mode") or DEFAULT_REPAIR_MODE)))
        # 修复后是否保留原图：False=直接覆盖原图（默认），True=原图备份到「_含水印原图」目录
        self.keep_original_var = tk.BooleanVar(value=bool(config.get("keep_original", False)))
        self.category_var = tk.StringVar(value=MAIN_CATEGORY)

        self.status_var = tk.StringVar(value="导入「名称+链接」列表，点开始即可。")
        self.progress_summary_var = tk.StringVar(value="尚未导入列表")
        self.panel_name_var = tk.StringVar(value="-")
        self.panel_progress_var = tk.StringVar(value="主图 0/0 · 详情 0/0")
        self.hook_state_var = tk.StringVar(value="")
        self.device_state_var = tk.StringVar(value="设备：未登记" if not self.server_token else "设备：已登记")
        self.quota_var = tk.StringVar(value="图片额度：未同步")
        self.is_paid_user = False  # 充值用户导出不打试用水印（同步额度后更新）

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
        style.configure("TButton", padding=(10, 5), background="#ffffff", foreground=COLOR_TEXT,
                        bordercolor=COLOR_BORDER)
        style.map("TButton", background=[("active", "#f1f5f9")])
        style.configure("Accent.TButton", padding=(20, 6), background=COLOR_GREEN, foreground="#ffffff",
                        bordercolor=COLOR_GREEN, font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("disabled", "#a7d9bd"), ("active", COLOR_GREEN_DARK)],
                  foreground=[("disabled", "#ffffff"), ("active", "#ffffff")])
        style.configure("Repair.TButton", padding=(14, 6), background=COLOR_GREEN_SOFT,
                        foreground=COLOR_GREEN_DARK, bordercolor=COLOR_GREEN,
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Repair.TButton", background=[("active", "#ddf5e7")])
        style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT,
                        font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("Hint.TLabel", foreground=COLOR_MUTED, background=COLOR_BG)
        style.configure("CardHint.TLabel", foreground=COLOR_MUTED, background=COLOR_CARD)
        style.configure("Status.TLabel", foreground=COLOR_GREEN_DARK, background=COLOR_BG)
        style.configure("Card.TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT)
        style.map("Card.TCheckbutton", background=[("active", COLOR_CARD)])
        style.configure("TLabelframe", background=COLOR_CARD, bordercolor=COLOR_BORDER, relief="solid")
        style.configure("TLabelframe.Label", background=COLOR_CARD, foreground=COLOR_MUTED,
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Treeview", rowheight=28, background="#ffffff", fieldbackground="#ffffff",
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

        # 顶栏：标题 + 钩子状态 + 额度
        header = ttk.Frame(root, padding=(20, 12, 20, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        title_box = ttk.Frame(header)
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text=f" {APP_VERSION} · 按住 Ctrl 拖动框选，松开自动保存",
                  style="Hint.TLabel").grid(row=0, column=1, sticky="sw", pady=(0, 3))

        status_box = ttk.Frame(header)
        status_box.grid(row=0, column=2, sticky="e")
        ttk.Label(status_box, textvariable=self.hook_state_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="e", padx=(0, 12))
        tk.Label(status_box, textvariable=self.quota_var, bg=COLOR_GREEN_SOFT, fg=COLOR_GREEN_DARK,
                 font=("Microsoft YaHei UI", 9, "bold"), padx=10, pady=4).grid(row=0, column=1, sticky="e")

        # 设置区：左「采集设置」+ 右「服务与额度」
        cfg_row = ttk.Frame(root, padding=(20, 0, 20, 8))
        cfg_row.grid(row=1, column=0, sticky="ew")
        cfg_row.columnconfigure(0, weight=3)
        cfg_row.columnconfigure(1, weight=2)

        work = ttk.LabelFrame(cfg_row, text="采集设置", padding=(14, 6, 14, 10))
        work.grid(row=0, column=0, sticky="nsew")
        work.columnconfigure(1, weight=1)

        ttk.Label(work, text="输出目录", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(work, textvariable=self.output_dir_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(work, text="选择", command=self.choose_output).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(work, text="打开", command=self.open_output).grid(row=0, column=3, padx=(4, 0))

        nums = ttk.Frame(work, style="Card.TFrame")
        nums.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(nums, text="主图", style="Card.TLabel").grid(row=0, column=0, padx=(0, 6))
        ttk.Spinbox(nums, from_=0, to=99, width=5, textvariable=self.main_count_var).grid(row=0, column=1)
        ttk.Label(nums, text="详情", style="Card.TLabel").grid(row=0, column=2, padx=(14, 6))
        ttk.Spinbox(nums, from_=0, to=99, width=5, textvariable=self.detail_count_var).grid(row=0, column=3)
        ttk.Label(nums, text="文件名前缀", style="Card.TLabel").grid(row=0, column=4, padx=(18, 6))
        ttk.Entry(nums, width=8, textvariable=self.prefix_var).grid(row=0, column=5)
        ttk.Label(nums, text="JPG质量", style="Card.TLabel").grid(row=0, column=6, padx=(14, 6))
        ttk.Spinbox(nums, from_=30, to=100, width=5, textvariable=self.quality_var).grid(row=0, column=7)

        opts = ttk.Frame(work, style="Card.TFrame")
        opts.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(opts, text="切行自动开链接", variable=self.auto_open_var,
                        style="Card.TCheckbutton").grid(row=0, column=0, sticky="w")
        ttk.Label(opts, text="主图/详情截够自动切换、自动下一行", style="CardHint.TLabel").grid(
            row=0, column=1, sticky="w", padx=(14, 0))

        svc = ttk.LabelFrame(cfg_row, text="服务与额度", padding=(14, 6, 14, 10))
        svc.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        svc.columnconfigure(1, weight=1)

        ttk.Label(svc, text="软件编号", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.software_id_entry = ttk.Entry(svc, textvariable=self.software_id_var, state="readonly")
        self.software_id_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(svc, text="复制", command=self.copy_software_id).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(svc, text="服务器", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(svc, textvariable=self.server_url_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(svc, text="同步额度", command=self.sync_quota).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))

        svc_btns = ttk.Frame(svc)
        svc_btns.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(svc_btns, textvariable=self.device_state_var, style="CardHint.TLabel").pack(side="left")
        tk.Button(svc_btns, text="💰 充值续费", command=self.open_recharge,
                  bd=0, bg=COLOR_GREEN, fg="#ffffff", activebackground=COLOR_GREEN_DARK,
                  cursor="hand2", padx=12, pady=3,
                  font=("Microsoft YaHei UI", 9, "bold")).pack(side="left", padx=(12, 0))

        # 操作栏：导入 | 截图 ┄┄ 修复类型 + AI 修复（右对齐）
        toolbar = ttk.Frame(root, padding=(20, 0, 20, 8))
        toolbar.grid(row=2, column=0, sticky="ew")
        toolbar.columnconfigure(7, weight=1)  # 弹性间隔，把修复区推到右侧
        ttk.Button(toolbar, text="导入文件", command=self.import_file).grid(row=0, column=0)
        ttk.Button(toolbar, text="从剪贴板导入", command=self.import_clipboard).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(toolbar, text="导入图片文件夹", command=self.import_image_folder).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(toolbar, text="清空列表", command=self.clear_rows).grid(row=0, column=3, padx=(6, 0))
        ttk.Separator(toolbar, orient="vertical").grid(row=0, column=4, sticky="ns", padx=12)
        self.start_button = ttk.Button(toolbar, text="▶  开始截图", style="Accent.TButton", command=self.start_work)
        self.start_button.grid(row=0, column=5)
        self.stop_button = ttk.Button(toolbar, text="结束截图", command=self.stop_work, state="disabled")
        self.stop_button.grid(row=0, column=6, padx=(6, 0))
        self.free_button = ttk.Button(toolbar, text="自由截图", command=self.start_free)
        self.free_button.grid(row=0, column=7, padx=(6, 0))
        # 右侧修复区
        ttk.Label(toolbar, text="修复类型").grid(row=0, column=8, padx=(0, 6))
        self.repair_mode_combo = ttk.Combobox(
            toolbar,
            textvariable=self.repair_mode_var,
            values=[label for _, label in REPAIR_MODES],
            state="readonly",
            width=12,
        )
        self.repair_mode_combo.grid(row=0, column=9)
        ttk.Checkbutton(toolbar, text="保留原图", variable=self.keep_original_var,
                        command=self._save_keep_original).grid(row=0, column=10, padx=(10, 0))
        self.repair_button = ttk.Button(toolbar, text="AI 智能修复", style="Repair.TButton", command=self.ai_repair)
        self.repair_button.grid(row=0, column=11, padx=(8, 0))
        self.doc_button = ttk.Button(toolbar, text="整理成文档", command=self.open_export_doc)
        self.doc_button.grid(row=0, column=12, padx=(14, 0))

        # 列表 + 日志
        body = ttk.Panedwindow(root, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 8))
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=1)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        list_head = ttk.Frame(left)
        list_head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        list_head.columnconfigure(0, weight=1)
        ttk.Label(list_head, text="商品截图进度", font=("Microsoft YaHei UI", 11, "bold")).grid(
            row=0, column=0, sticky="w")
        ttk.Label(list_head, textvariable=self.progress_summary_var, style="Hint.TLabel").grid(
            row=0, column=1, sticky="e")

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
        self.tree.tag_configure("even", background="#f7fbf8")
        self.tree.tag_configure("current", background=COLOR_GREEN_SOFT, foreground=COLOR_GREEN_DARK)
        self.tree.tag_configure("done", foreground=COLOR_MUTED)

        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="运行日志", font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.log_box = scrolledtext.ScrolledText(
            right, width=30, wrap="word", font=("Microsoft YaHei UI", 9),
            bd=0, relief="flat", highlightthickness=1,
            highlightbackground=COLOR_BORDER, highlightcolor=COLOR_BORDER)
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.log_box.configure(state="disabled")

        # 底部状态栏
        footer = tk.Frame(root, bg=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
        footer.grid(row=4, column=0, sticky="ew")
        tk.Label(footer, textvariable=self.status_var, bg=COLOR_CARD, fg=COLOR_GREEN_DARK,
                 font=("Microsoft YaHei UI", 9), anchor="w", padx=20, pady=6).grid(
            row=0, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

    # ----- 通用 -----

    def copy_software_id(self):
        value = self.software_id_var.get().strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.set_status(f"已复制软件编号：{value}")

    def _resolve_pay_qr(self):
        """找收款码图片：优先 PyInstaller 解压目录，其次 exe 同级，最后源码同级。"""
        cands = []
        if getattr(sys, "frozen", False):
            cands.append(Path(getattr(sys, "_MEIPASS", "")) / "pay_qr.png")
            cands.append(Path(sys.executable).resolve().parent / "pay_qr.png")
        cands.append(Path(__file__).resolve().parent / "pay_qr.png")
        for p in cands:
            try:
                if p and p.exists():
                    return p
            except Exception:
                continue
        return None

    def _software_tail8(self) -> str:
        """软件编号去分隔符后的后 8 位（充值备注用，完整编号太长）。"""
        s = "".join(ch for ch in self.software_id_var.get() if ch.isalnum())
        return s[-8:] if len(s) >= 8 else s

    def open_recharge(self):
        """弹出充值续费对话框：支付宝收款码 + 备注编号（编号后 8 位）。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("充值续费")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)

        wrap = tk.Frame(dlg, bg=COLOR_BG)
        wrap.pack(padx=20, pady=18)
        tk.Label(wrap, text="支付宝扫码转账，到账后联系客服为你充值额度",
                 bg=COLOR_BG, fg=COLOR_TEXT, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")

        body = tk.Frame(wrap, bg=COLOR_BG)
        body.pack(fill="x", pady=(12, 0))

        # 左：收款码
        qr_path = self._resolve_pay_qr()
        qr_box = tk.Frame(body, bg="#ffffff", highlightbackground=COLOR_BORDER,
                          highlightthickness=1, width=200, height=200)
        qr_box.pack(side="left")
        qr_box.pack_propagate(False)
        self._recharge_qr_img = None
        if qr_path is not None:
            try:
                img = Image.open(qr_path)
                img.thumbnail((184, 184))
                self._recharge_qr_img = ImageTk.PhotoImage(img)
                tk.Label(qr_box, image=self._recharge_qr_img, bg="#ffffff").pack(expand=True)
            except Exception:
                self._recharge_qr_img = None
        if self._recharge_qr_img is None:
            tk.Label(qr_box, text="收款码未配置", bg="#ffffff", fg=COLOR_MUTED,
                     font=("Microsoft YaHei UI", 10)).pack(expand=True)

        # 右：备注说明
        right = tk.Frame(body, bg=COLOR_BG)
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))
        tail = self._software_tail8()
        tk.Label(right, text="⚠️ 转账时务必在「备注 / 留言」里填写下面的编号：",
                 bg=COLOR_BG, fg="#c2410c", justify="left", wraplength=260,
                 font=("Microsoft YaHei UI", 10)).pack(anchor="w")
        note = tk.Frame(right, bg="#fef9c3")
        note.pack(anchor="w", fill="x", pady=(8, 8))
        tk.Label(note, text="备注：", bg="#fef9c3", fg=COLOR_TEXT,
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(10, 2), pady=8)
        tk.Label(note, text=tail, bg="#fef9c3", fg="#c0392b",
                 font=("Consolas", 16, "bold")).pack(side="left", pady=8)

        def copy_note():
            self.root.clipboard_clear(); self.root.clipboard_append(tail)
            self.set_status(f"已复制备注编号：{tail}")
        tk.Button(right, text="复制备注编号", command=copy_note,
                  bd=0, bg=COLOR_GREEN, fg="#ffffff", activebackground=COLOR_GREEN_DARK,
                  cursor="hand2", padx=12, pady=4,
                  font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        tk.Label(right, text="（编号是你软件编号的后 8 位；\n充值、续费、定制需求也可加客服微信 18033086531）",
                 bg=COLOR_BG, fg=COLOR_MUTED, justify="left", wraplength=260,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(8, 0))

        dlg.update_idletasks()
        # 居中到主窗口
        try:
            x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
            y = self.root.winfo_rooty() + 80
            dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _save_keep_original(self):
        keep = bool(self.keep_original_var.get())
        save_config({"keep_original": keep})
        if keep:
            self.set_status(f"修复后将保留原图：备份到各「{BACKUP_DIR_NAME}」目录。")
        else:
            self.set_status("修复后将直接覆盖原图（不保留备份）。")

    def _set_quota_from_response(self, data: dict):
        quota = data.get("quota") if isinstance(data, dict) else None
        if isinstance(quota, dict):
            available = int(quota.get("available") or 0)
            free = int(quota.get("free") or 0)
            paid = int(quota.get("paid") or 0)
            self.quota_var.set(f"图片额度：剩余 {available} 张（默认 {free} / 充值 {paid}）")
            # 记录付费状态：充值过(paid>0)的用户导出文档不打试用水印
            self.is_paid_user = paid > 0

    def register_device(self, silent: bool = False) -> bool:
        software_id = self.software_id_var.get().strip()
        legacy_id = getattr(self, "legacy_software_id", "")
        try:
            data = server_register_device(self.server_url_var.get(), software_id, legacy_id)
        except ServerApiError as exc:
            self.device_state_var.set("设备：登记失败")
            self.log(f"软件编号登记失败：{exc}")
            if not silent:
                messagebox.showerror(APP_NAME, f"软件编号登记失败：\n{exc}", parent=self.root)
            return False
        self.server_token = str(data.get("token") or "").strip()
        self.device_state_var.set("设备：已登记")
        self._set_quota_from_response(data)
        # 迁移已完成，清掉旧编号，避免配置被拷到别的电脑时重复触发迁移
        self.legacy_software_id = ""
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

    def import_image_folder(self):
        if self.busy:
            messagebox.showinfo(APP_NAME, "AI 正在处理图片，请稍后再导入。", parent=self.root)
            return
        if self.work_mode:
            messagebox.showinfo(APP_NAME, "请先结束截图，再导入图片文件夹。", parent=self.root)
            return
        folder = filedialog.askdirectory(title="选择要修复的图片文件夹", parent=self.root)
        if not folder:
            return
        root = Path(folder)
        images = scan_image_folder(root)
        if not images:
            messagebox.showinfo(APP_NAME, "这个文件夹里没有找到可处理的图片。", parent=self.root)
            return

        replace = True
        if self.captures:
            answer = messagebox.askyesnocancel(
                APP_NAME,
                f"当前待修复列表已有 {len(self.captures)} 张图片。\n\n"
                "是：替换为这个文件夹\n"
                "否：追加到当前列表\n"
                "取消：不导入",
                parent=self.root,
            )
            if answer is None:
                return
            replace = bool(answer)
        if replace:
            self.captures = []

        existing = set()
        for capture in self.captures:
            try:
                existing.add(str(capture["path"].resolve()).lower())
            except Exception:
                existing.add(str(capture.get("path", "")).lower())

        imported = 0
        skipped = 0
        root_resolved = root.resolve()
        for image_path in images:
            try:
                key = str(image_path.resolve()).lower()
            except Exception:
                key = str(image_path).lower()
            if key in existing:
                skipped += 1
                continue
            try:
                relative = image_path.resolve().relative_to(root_resolved)
            except Exception:
                relative = Path(image_path.name)
            parent = relative.parent
            name = root.name if str(parent) in ("", ".") else str(parent)
            self.captures.append({
                "path": image_path,
                "row_index": None,
                "name": name,
                "category": "文件夹导入",
            })
            existing.add(key)
            imported += 1

        self.set_status(f"已导入图片文件夹：{imported} 张，可直接点「AI 智能修复」。")
        message = f"从图片文件夹导入 {imported} 张：{root}"
        if skipped:
            message += f"；跳过重复 {skipped} 张"
        self.log(message)

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
            is_current = self.work_mode and index == self.current_index
            mark = "▶" if is_current else ""
            if is_current:
                tag = "current"
            elif row["status"] == "完成":
                tag = "done"
            else:
                tag = "even" if index % 2 else ""
            self.tree.insert("", "end", iid=str(index), tags=(tag,) if tag else (), values=(
                f"{mark}{index + 1}", row["name"],
                "有" if row["link"] else "无",
                main_done, detail_done, row["status"]))
        if self.work_mode and 0 <= self.current_index < len(self.rows):
            try:
                self.tree.selection_set(str(self.current_index))
                self.tree.see(str(self.current_index))
            except tk.TclError:
                pass
        total = len(self.rows)
        if total:
            finished = sum(1 for row in self.rows if row["status"] == "完成")
            self.progress_summary_var.set(f"完成 {finished}/{total} 行 · 本次截图 {len(self.captures)} 张")
        else:
            self.progress_summary_var.set("尚未导入列表")

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
            messagebox.showwarning(APP_NAME, "截图功能启用失败，可能被安全软件拦截。\n"
                                             "请在安全软件里允许本程序后重试。", parent=self.root)
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

    # ---------------- 自由截图模式（不绑列表，自己开网页/程序随手截图） ----------------

    def start_free(self):
        if self.work_mode:
            messagebox.showinfo(APP_NAME, "请先结束商品采集，再使用自由截图。", parent=self.root)
            return
        if self.free_mode:
            self.stop_free()
            return
        save_config({"output_dir": self.output_dir_var.get(), "quality": int(self.quality_var.get() or 95)})

        self.selection_box = SelectionBoxWindow(self.root)
        ok = False
        try:
            ok = self.hook.install()
        except Exception as exc:
            self.log(f"启用 Ctrl 拖动失败：{exc}")
        if not ok:
            self.hook_state_var.set("● Ctrl 拖动截图：启用失败")
            self.log(f"Ctrl 拖动启用失败：{self.hook.last_error or '可能被安全软件拦截'}。")
            messagebox.showwarning(APP_NAME, "截图功能启用失败，可能被安全软件拦截。\n"
                                             "请在安全软件里允许本程序后重试。", parent=self.root)
            if self.selection_box is not None:
                try:
                    self.selection_box.destroy()
                except tk.TclError:
                    pass
                self.selection_box = None
            return

        self.free_mode = True
        self.free_count = 0
        self.free_count_var.set("本次自由截图：0 张")
        # 记录本轮起点：整理文档默认只收这之后的图（减 2 秒容差，防止边界图漏掉）
        self.free_session_start = time.time() - 2
        self.free_session_files = []
        self.hook_polling = True
        self.root.after(15, self.poll_hook)
        self.hook_state_var.set("● 自由截图中：按住 Ctrl 拖动")
        self.free_button.configure(text="结束自由截图")
        self.start_button.configure(state="disabled")
        self.free_panel = FreePanel(self)
        self.hide_main()
        self.set_status("自由截图已开启：到任意网页/程序，按住 Ctrl 拖动框选，自动存到「自由截图」。")
        self.log("自由截图已开启，按住 Ctrl 拖动鼠标截图。")

    def stop_free(self, _event=None):
        if not self.free_mode:
            return
        self.free_mode = False
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
        if self.free_panel is not None:
            try:
                self.free_panel.destroy()
            except tk.TclError:
                pass
            self.free_panel = None
        self.hook_state_var.set("")
        self.free_button.configure(text="自由截图")
        self.start_button.configure(state="normal")
        self.show_main()
        self.set_status(f"自由截图已结束，本次共 {self.free_count} 张，存在「自由截图」文件夹。")

    def open_free_dir(self):
        path = Path(self.output_dir_var.get()) / "自由截图"
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))
        except Exception as exc:
            self.log(f"打开目录失败：{exc}")

    def open_export_doc(self):
        ExportDocWindow(self)

    def _save_free_capture(self, image):
        target_dir = Path(self.output_dir_var.get()) / "自由截图"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = target_dir / f"截图_{stamp}.jpg"
        index = 2
        while target.exists():
            target = target_dir / f"截图_{stamp}-{index}.jpg"
            index += 1
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(target, "JPEG", quality=int(self.quality_var.get() or 95))
        self.free_count += 1
        self.free_session_files.append(target)
        self.free_count_var.set(f"本次自由截图：{self.free_count} 张")
        self.log(f"已存：自由截图/{target.name}（{image.width}x{image.height}）")

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
                    # 在显示选框之前先把整屏冻结成静态图（不含本程序的选框窗）
                    self.frozen_image = self._freeze_screen()
                    if self.selection_box:
                        photo = None
                        if self.frozen_image is not None:
                            try:
                                photo = ImageTk.PhotoImage(self.frozen_image)
                            except Exception:
                                photo = None
                        self.selection_box.begin(x, y, photo)
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

    def _freeze_screen(self):
        try:
            from PIL import ImageGrab
        except Exception:
            return None
        try:
            # 抓主屏物理像素，坐标与钩子坐标一致，裁剪时直接按屏幕坐标切。
            return ImageGrab.grab()
        except Exception as exc:
            write_error_log(f"冻结屏幕失败：{exc}")
            return None

    def _finish_gesture(self, sx, sy, ex, ey):
        left, top = min(sx, ex), min(sy, ey)
        right, bottom = max(sx, ex), max(sy, ey)
        if right - left < 5 or bottom - top < 5:
            self.frozen_image = None
            self.log("框选区域太小，已忽略。")
            return
        self.grabbing = True
        self.hook.enabled = False
        try:
            self._crop_frozen((int(left), int(top), int(right), int(bottom)))
        finally:
            self.grabbing = False
            self.hook.enabled = True

    def _crop_frozen(self, bbox):
        frozen = self.frozen_image
        self.frozen_image = None
        try:
            inside_frozen = False
            if frozen is not None:
                width, height = frozen.size
                # 选区完整落在主屏冻结图范围内才用冻结图裁剪；否则（多屏副屏、
                # 冻结失败）退回直接抓当前屏幕，保证多显示器下坐标正确。
                inside_frozen = (
                    bbox[0] >= 0 and bbox[1] >= 0
                    and bbox[2] <= width and bbox[3] <= height
                )
            if inside_frozen:
                image = frozen.crop((bbox[0], bbox[1], bbox[2], bbox[3]))
            else:
                from PIL import ImageGrab
                image = ImageGrab.grab(bbox=bbox, all_screens=True)
            self.save_capture(image)
        except Exception as exc:
            self.log(f"截图失败：{exc}")
            write_error_log(f"截图失败：{exc}")

    def save_capture(self, image):
        if self.free_mode:
            self._save_free_capture(image)
            return
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
            messagebox.showinfo(APP_NAME, "还没有任何截图或导入的图片。", parent=self.root)
            return
        existing = [c for c in self.captures if c["path"].exists()]
        if not existing:
            messagebox.showinfo(APP_NAME, "图片文件都不在了。", parent=self.root)
            return
        mode_key = normalize_repair_mode(self.repair_mode_var.get())
        mode_label = repair_mode_label(mode_key)
        self.repair_mode_var.set(mode_label)
        save_config({"repair_mode": mode_key})
        self.show_main()
        dialog = ManualRepairDialog(self, existing, mode_label)
        self.root.wait_window(dialog)
        targets = dialog.result
        if not targets:
            self.set_status("已取消图片修复。")
            return
        if not self.ensure_server_login():
            return
        self.busy = True
        self.stop_event = threading.Event()
        self.repair_button.configure(state="disabled")
        self.log(f"人工选择 {len(targets)} 张图片，修复类型：{mode_label}。")
        self._start_remove(targets, mode_key, mode_label)

    def _detect_worker(self, server_url: str, token: str, captures: list, mode_key: str, mode_label: str):
        candidates = []
        failures = 0
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
                failures += 1
                self.ai_events.put(("error", message, capture["path"].name))
                if is_fatal_ai_error(message):
                    self.ai_events.put(("fatal", message))
                    return
            except Exception as exc:
                failures += 1
                self.ai_events.put(("error", str(exc), capture["path"].name))
        if captures and failures >= len(captures) and not candidates and not self.stop_event.is_set():
            self.ai_events.put(("fatal", "所有图片检测都失败了，请先检查服务器模型配置、网络或额度后再试。"))
            return
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
        keep_original = bool(self.keep_original_var.get())
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snap_wm_"))
        # 记录修复类型，供「结果核对」窗里的二次修复复用；重置上一轮对比结果
        self.review_mode_key = mode_key
        self.review_mode_label = mode_label
        self.review_results = []
        self.set_status(f"正在{mode_label} 0/{len(targets)}...")
        self.log(f"开始{mode_label} {len(targets)} 张（{'保留原图备份' if keep_original else '直接覆盖原图'}）。")
        self.ai_events = queue.Queue()
        self.ai_thread = threading.Thread(
            target=self._remove_worker,
            args=(server_url, token, targets, mode_key, mode_label, keep_original, True), daemon=True)
        self.ai_thread.start()
        self.root.after(200, self._poll_remove)

    def _remove_worker(self, server_url: str, token: str, targets: list, mode_key: str,
                       mode_label: str, keep_original: bool, cache_original: bool):
        done = 0
        failed = 0
        results = []
        for index, path in enumerate(targets):
            if self.stop_event.is_set():
                break
            try:
                before_path = ""
                if cache_original:
                    # keep_original=True 时把原图备份到「_含水印原图」目录（持久，新旧分开）
                    if keep_original:
                        backup = path.parent / BACKUP_DIR_NAME
                        backup.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, backup / path.name)
                    # 无论是否保留，都先缓存一份原图到临时目录，供「结果核对」窗对比；
                    # 临时目录在对比窗关闭后清理。
                    orig_dir = self.temp_dir / "orig"
                    orig_dir.mkdir(parents=True, exist_ok=True)
                    before_path = str(orig_dir / f"{uuid.uuid4().hex}.jpg")
                    shutil.copy2(path, before_path)
                server_remove_watermark_to(server_url, token, path, path, self.temp_dir, mode_key, self.stop_event)
                done += 1
                results.append({"name": path.parent.parent.name or path.parent.name,
                                "before": before_path, "after": str(path)})
                self.ai_events.put(("removed", index + 1, len(targets), path.name, mode_label))
            except ServerApiError as exc:
                failed += 1
                message = str(exc)
                self.ai_events.put(("rm_error", message, path.name))
                if is_fatal_ai_error(message):
                    self.ai_events.put(("rm_fatal", message))
                    return
            except Exception as exc:
                failed += 1
                self.ai_events.put(("rm_error", str(exc), path.name))
        self.ai_events.put(("remove_done", done, failed, keep_original, results))

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
                elif kind == "rm_fatal":
                    self.busy = False
                    self.repair_button.configure(state="normal")
                    self._cleanup_temp_dir()
                    self.set_status(f"图片修复停止：{event[1]}")
                    messagebox.showerror(APP_NAME, f"图片修复停止：\n{event[1]}", parent=self.root)
                    return
                elif kind == "remove_done":
                    self._on_remove_done(event[1], event[2], event[3], event[4])
                    return
        except queue.Empty:
            pass
        if self.busy:
            self.root.after(200, self._poll_remove)

    def _cleanup_temp_dir(self):
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

    def _on_remove_done(self, done: int, failed: int, keep_original: bool, results: list):
        self.busy = False
        self.repair_button.configure(state="normal")
        if keep_original:
            note = f"原图已备份到各「{BACKUP_DIR_NAME}」目录。"
        else:
            note = "修复结果已直接覆盖原图。"
        self.set_status(f"图片修复完成：成功 {done} 张，失败 {failed} 张。{note}")
        self.log(f"图片修复结束：成功 {done}，失败 {failed}。")
        self.sync_quota()
        # 合并本轮结果：二次修复时按 after 路径匹配，保留首轮缓存的「原图」，只刷新「修改后」
        for record in results:
            existing = next((r for r in self.review_results if r["after"] == record["after"]), None)
            if existing:
                existing["round"] = existing.get("round", 1) + 1
            else:
                record["round"] = 1
                self.review_results.append(record)
        if self.review_results:
            self._open_review()
        else:
            self._cleanup_temp_dir()
            messagebox.showinfo(APP_NAME, f"图片修复完成：成功 {done} 张，失败 {failed} 张。\n{note}",
                                parent=self.root)

    def _open_review(self):
        dialog = ResultReviewDialog(self, self.review_results, self.review_mode_label)
        self.root.wait_window(dialog)
        action = dialog.action
        if action == "rerun" and dialog.selected:
            self._review_rerun(dialog.selected)
        else:
            self._cleanup_temp_dir()
            self.review_results = []
            self.set_status("图片核对完成。")

    def _review_rerun(self, targets: list):
        server_url = normalize_server_url(self.server_url_var.get())
        token = self.server_token
        mode_key = self.review_mode_key
        mode_label = self.review_mode_label
        self.busy = True
        self.repair_button.configure(state="disabled")
        self.set_status(f"正在二次{mode_label} 0/{len(targets)}...")
        self.log(f"二次{mode_label} {len(targets)} 张。")
        self.ai_events = queue.Queue()
        # 二次修复：复用已有临时目录，不再重新缓存原图（对比始终对照首轮真·原图）
        self.ai_thread = threading.Thread(
            target=self._remove_worker,
            args=(server_url, token, targets, mode_key, mode_label, False, False), daemon=True)
        self.ai_thread.start()
        self.root.after(200, self._poll_remove)

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
