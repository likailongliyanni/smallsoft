"""Local backend for Haobanfa AI document manager.

The desktop app never uploads original files in this first architecture.
It scans local folders, counts billable pages, stores metadata in a local
SQLite library, and sends only device/quota requests to tools.haobanfa.
Future OCR/AI extraction commands should send text, not the source file.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import docintel

APP_CODE = "AIDOC"
APP_NAME = "ai-doc"
APP_VERSION = "0.1.0"
FREE_PAGES = 50
DEFAULT_SERVER_URL = "https://tools.haobanfa.online"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".docx",
    ".xlsx",
    ".xlsm",
    ".txt",
    ".csv",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXTENSIONS = {".txt", ".csv"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".xlsm"}

APP_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "HaobanfaAIDoc"
CONFIG_PATH = APP_DIR / "config.json"

STATE: dict[str, Any] = {"token": "", "unlocked": False}
CONFIG_LOCK = threading.Lock()


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def load_config() -> dict[str, Any]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        return {
            "server_url": DEFAULT_SERVER_URL,
            "free_pages": FREE_PAGES,
        }
    try:
        return json.loads(CONFIG_PATH.read_text("utf-8"))
    except Exception:
        return {
            "server_url": DEFAULT_SERVER_URL,
            "free_pages": FREE_PAGES,
        }


def save_config(patch: dict[str, Any]) -> dict[str, Any]:
    with CONFIG_LOCK:
        config = load_config()
        config.update(patch)
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")
        return config


def server_url() -> str:
    return str(load_config().get("server_url") or DEFAULT_SERVER_URL).rstrip("/")


def robust_mac() -> str:
    try:
        result = subprocess.run(
            ["getmac", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        macs: list[str] = []
        for token in re.findall(r"([0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5})", result.stdout):
            value = re.sub(r"[^0-9A-Fa-f]", "", token).upper()
            if len(value) == 12 and value != "000000000000":
                macs.append(value)
        if macs:
            return sorted(set(macs))[0]
    except Exception:
        pass
    return f"{uuid.getnode():012X}"


def raw_software_id() -> str:
    return f"{robust_mac()}-{APP_CODE}"


def pretty_serial(raw: str | None = None) -> str:
    value = str(raw or raw_software_id()).upper()
    if value.endswith(f"-{APP_CODE}"):
        value = value[: -len(APP_CODE) - 1]
    hexs = "".join(ch for ch in value if ch.isalnum()).upper()[:12]
    if len(hexs) == 12:
        return "-".join(hexs[i : i + 2] for i in range(0, 12, 2)) + f"-{APP_CODE}"
    return str(raw or raw_software_id())


def pbkdf2_hash(password: str, salt: bytes | None = None) -> dict[str, str]:
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return {
        "scheme": "pbkdf2_sha256",
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(digest).decode("ascii"),
    }


def verify_password(password: str, stored: dict[str, str] | None) -> bool:
    if not stored:
        return False
    try:
        salt = base64.b64decode(stored["salt"])
        expected = base64.b64decode(stored["hash"])
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(actual, expected)


def request_json(path: str, body: dict[str, Any] | None = None, token: str = "", timeout: int = 30) -> dict[str, Any]:
    url = server_url() + path
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="GET" if body is None else "POST")
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_quota(data: dict[str, Any] | None = None) -> dict[str, int]:
    quota = (data or {}).get("quota") if isinstance(data, dict) else None
    if isinstance(quota, dict):
        return {
            "free": int(quota.get("free") or quota.get("free_pages") or 0),
            "paid": int(quota.get("paid") or quota.get("paid_pages") or 0),
            "available": int(quota.get("available") or quota.get("available_pages") or 0),
            "used": int(quota.get("used") or quota.get("used_pages") or 0),
            "unit": "page",
        }
    config = load_config()
    return {
        "free": int(config.get("free_pages") or FREE_PAGES),
        "paid": 0,
        "available": int(config.get("free_pages") or FREE_PAGES),
        "used": 0,
        "unit": "page",
    }


def command_get_serial(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "serial": pretty_serial(),
        "raw": raw_software_id(),
        "app": APP_NAME,
        "unit": "page",
    }


def command_register(_: dict[str, Any]) -> dict[str, Any]:
    serial = raw_software_id()
    try:
        data = request_json(
            "/api/desktop/device/register",
            {
                "software_id": serial,
                "app": APP_NAME,
                "version": APP_VERSION,
                "quota_unit": "page",
                "free_quota": FREE_PAGES,
            },
        )
        STATE["token"] = str(data.get("token") or "")
        return {
            "online": True,
            "serial": pretty_serial(data.get("software_id") or serial),
            "quota": normalize_quota(data),
        }
    except Exception as exc:
        return {
            "online": False,
            "serial": pretty_serial(serial),
            "quota": normalize_quota(),
            "message": f"后台暂不可用，已进入本地模式：{str(exc)[:160]}",
        }


def command_sync_quota(_: dict[str, Any]) -> dict[str, Any]:
    if not STATE.get("token"):
        return command_register({})
    try:
        data = request_json("/api/desktop/device/status", token=STATE["token"])
        return {"online": True, "quota": normalize_quota(data)}
    except Exception as exc:
        return {
            "online": False,
            "quota": normalize_quota(),
            "message": f"同步失败，显示本地免费额度：{str(exc)[:160]}",
        }


def command_get_state(_: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    has_password = bool(config.get("password"))
    return {
        "serial": pretty_serial(),
        "raw_serial": raw_software_id(),
        "has_password": has_password,
        "unlocked": bool(STATE.get("unlocked")) or not has_password,
        "library_dir": config.get("library_dir") or "",
        "server_url": config.get("server_url") or DEFAULT_SERVER_URL,
        "quota": normalize_quota(),
    }


def command_set_password(args: dict[str, Any]) -> dict[str, Any]:
    password = str(args.get("password") or "")
    if len(password) < 4:
        raise RuntimeError("本地密码至少 4 位。")
    save_config({"password": pbkdf2_hash(password)})
    STATE["unlocked"] = True
    return {"has_password": True, "unlocked": True}


def command_verify_password(args: dict[str, Any]) -> dict[str, Any]:
    password = str(args.get("password") or "")
    ok = verify_password(password, load_config().get("password"))
    if ok:
        STATE["unlocked"] = True
    return {"unlocked": ok}


def require_unlocked() -> None:
    config = load_config()
    if config.get("password") and not STATE.get("unlocked"):
        raise RuntimeError("请先输入本地密码。")


def library_dir() -> Path:
    config = load_config()
    value = str(config.get("library_dir") or "").strip()
    if not value:
        raise RuntimeError("请先设置本地资料库位置。")
    root = Path(value).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "files").mkdir(exist_ok=True)
    return root


def db_path(root: Path | None = None) -> Path:
    return (root or library_dir()) / "aidoc.db"


def connect_db(root: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(root)))
    conn.row_factory = sqlite3.Row  # 既能按列名也能按下标取值，兼容旧的 row[0] 写法
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          original_path TEXT NOT NULL,
          managed_path TEXT,
          file_name TEXT NOT NULL,
          extension TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          size_bytes INTEGER NOT NULL DEFAULT 0,
          page_count INTEGER NOT NULL DEFAULT 1,
          page_count_method TEXT NOT NULL,
          import_mode TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'imported',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256)")
    conn.commit()
    ensure_recognition_columns(conn)
    return conn


def command_set_library_dir(args: dict[str, Any]) -> dict[str, Any]:
    require_unlocked()
    target = Path(str(args.get("path") or "")).expanduser().resolve()
    if not str(target):
        raise RuntimeError("请选择资料库位置。")
    target.mkdir(parents=True, exist_ok=True)
    (target / "files").mkdir(exist_ok=True)
    connect_db(target).close()
    save_config({"library_dir": str(target)})
    return {"library_dir": str(target), "db": str(db_path(target))}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_pdf_pages(path: Path) -> tuple[int, str]:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        return max(1, len(reader.pages)), "pypdf"
    except Exception:
        try:
            data = path.read_bytes()
            count = len(re.findall(rb"/Type\s*/Page\b", data))
            return max(1, count), "pdf_regex"
        except Exception:
            return 1, "pdf_fallback"


def count_docx_pages(path: Path) -> tuple[int, str]:
    try:
        from docx import Document  # type: ignore

        document = Document(str(path))
        words = 0
        for paragraph in document.paragraphs:
            words += len(re.findall(r"\S+", paragraph.text))
        return max(1, (words + 899) // 900), "docx_word_estimate"
    except Exception:
        return 1, "docx_fallback"


def count_xlsx_pages(path: Path) -> tuple[int, str]:
    try:
        import openpyxl  # type: ignore

        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        try:
            return max(1, len(workbook.sheetnames)), "xlsx_sheets"
        finally:
            workbook.close()
    except Exception:
        try:
            with zipfile.ZipFile(path) as archive:
                sheets = [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")]
                return max(1, len(sheets)), "xlsx_zip_sheets"
        except Exception:
            return 1, "xlsx_fallback"


def count_text_pages(path: Path) -> tuple[int, str]:
    try:
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
                rows = sum(1 for _ in csv.reader(handle))
            return max(1, (rows + 49) // 50), "csv_50_rows_estimate"
        chars = len(path.read_text("utf-8", errors="ignore"))
        return max(1, (chars + 1799) // 1800), "text_char_estimate"
    except Exception:
        return 1, "text_fallback"


def count_pages(path: Path) -> tuple[int, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return count_pdf_pages(path)
    if suffix in IMAGE_EXTENSIONS:
        return 1, "image"
    if suffix == ".docx":
        return count_docx_pages(path)
    if suffix in {".xlsx", ".xlsm"}:
        return count_xlsx_pages(path)
    if suffix in TEXT_EXTENSIONS:
        return count_text_pages(path)
    return 1, "file_fallback"


def iter_supported_files(root: Path, recursive: bool) -> list[Path]:
    if recursive:
        iterator = root.rglob("*")
    else:
        iterator = root.glob("*")
    files: list[Path] = []
    for path in iterator:
        if not path.is_file():
            continue
        if path.name.startswith("~$"):
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    files.sort(key=lambda item: str(item).lower())
    return files


@dataclass
class ImportResult:
    created: bool
    document_id: int
    managed_path: str


def import_document(conn: sqlite3.Connection, src: Path, root: Path, digest: str, pages: int, method: str, import_mode: str) -> ImportResult:
    now = datetime.now().isoformat(timespec="seconds")
    existing = conn.execute("SELECT id, managed_path FROM documents WHERE sha256 = ?", (digest,)).fetchone()
    if existing:
        return ImportResult(False, int(existing[0]), str(existing[1] or ""))

    managed_path = ""
    if import_mode == "copy":
        stamp = datetime.now().strftime("%Y/%m")
        target_dir = root / "files" / stamp
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest[:16]}{src.suffix.lower()}"
        if not target.exists():
            shutil.copy2(src, target)
        managed_path = str(target)

    cursor = conn.execute(
        """
        INSERT INTO documents (
          original_path, managed_path, file_name, extension, sha256, size_bytes,
          page_count, page_count_method, import_mode, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported', ?, ?)
        """,
        (
            str(src),
            managed_path,
            src.name,
            src.suffix.lower().lstrip("."),
            digest,
            src.stat().st_size,
            pages,
            method,
            import_mode,
            now,
            now,
        ),
    )
    conn.commit()
    return ImportResult(True, int(cursor.lastrowid), managed_path)


def command_scan_folder(args: dict[str, Any]) -> dict[str, Any]:
    require_unlocked()
    source = Path(str(args.get("path") or "")).expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise RuntimeError("请选择有效的文件夹。")
    recursive = bool(args.get("recursive", True))
    import_mode = str(args.get("import_mode") or "copy")
    if import_mode not in {"copy", "index"}:
        import_mode = "copy"

    root = library_dir()
    conn = connect_db(root)
    job_id = uuid.uuid4().hex
    started = time.time()

    emit({
        "event": "aidoc_progress",
        "job_id": job_id,
        "stage": "scan",
        "stage_label": "正在扫描文件夹",
        "done_pages": 0,
        "total_pages": 0,
        "current_file": "",
    })

    files = iter_supported_files(source, recursive)
    total_files = len(files)
    total_pages = 0
    success_pages = 0
    skipped_pages = 0
    failed_pages = 0
    created_documents = 0
    skipped_documents = 0
    rows: list[dict[str, Any]] = []

    for index, file_path in enumerate(files, 1):
        rel = str(file_path.relative_to(source)) if file_path.is_relative_to(source) else file_path.name
        emit({
            "event": "aidoc_progress",
            "job_id": job_id,
            "stage": "count",
            "stage_label": "正在统计页数",
            "file_index": index,
            "file_total": total_files,
            "current_file": rel,
            "done_pages": total_pages,
            "total_pages": None,
        })
        try:
            pages, method = count_pages(file_path)
            digest = file_sha256(file_path)
            total_pages += pages
            result = import_document(conn, file_path, root, digest, pages, method, import_mode)
            if result.created:
                created_documents += 1
                success_pages += pages
                status = "imported"
            else:
                skipped_documents += 1
                skipped_pages += pages
                status = "duplicate"
            rows.append({
                "id": result.document_id,
                "name": file_path.name,
                "path": str(file_path),
                "managed_path": result.managed_path,
                "extension": file_path.suffix.lower().lstrip("."),
                "pages": pages,
                "method": method,
                "status": status,
            })
            emit({
                "event": "aidoc_progress",
                "job_id": job_id,
                "stage": "import",
                "stage_label": "正在导入资料库",
                "file_index": index,
                "file_total": total_files,
                "current_file": rel,
                "current_file_pages": pages,
                "done_pages": success_pages + skipped_pages + failed_pages,
                "total_pages": total_pages,
                "success_pages": success_pages,
                "skipped_pages": skipped_pages,
                "failed_pages": failed_pages,
            })
        except Exception as exc:
            failed_pages += 1
            rows.append({
                "id": None,
                "name": file_path.name,
                "path": str(file_path),
                "extension": file_path.suffix.lower().lstrip("."),
                "pages": 1,
                "method": "failed",
                "status": "failed",
                "error": str(exc)[:240],
            })
            emit({
                "event": "aidoc_progress",
                "job_id": job_id,
                "stage": "failed",
                "stage_label": "文件处理失败",
                "file_index": index,
                "file_total": total_files,
                "current_file": rel,
                "done_pages": success_pages + skipped_pages + failed_pages,
                "total_pages": total_pages,
                "success_pages": success_pages,
                "skipped_pages": skipped_pages,
                "failed_pages": failed_pages,
                "error": str(exc)[:240],
            })

    conn.close()
    elapsed = max(0.001, time.time() - started)
    emit({
        "event": "aidoc_progress",
        "job_id": job_id,
        "stage": "done",
        "stage_label": "已完成",
        "done_pages": success_pages + skipped_pages + failed_pages,
        "total_pages": total_pages,
        "success_pages": success_pages,
        "skipped_pages": skipped_pages,
        "failed_pages": failed_pages,
    })

    return {
        "job_id": job_id,
        "source": str(source),
        "library_dir": str(root),
        "file_count": total_files,
        "created_documents": created_documents,
        "skipped_documents": skipped_documents,
        "total_pages": total_pages,
        "billable_pages": success_pages,
        "skipped_pages": skipped_pages,
        "failed_pages": failed_pages,
        "elapsed_seconds": round(elapsed, 2),
        "items": rows[-200:],
    }


RECOGNITION_COLUMNS = [
    ("document_type", "TEXT"),
    ("document_type_label", "TEXT"),
    ("company_name", "TEXT"),
    ("brand", "TEXT"),
    ("certificate_no", "TEXT"),
    ("issuer", "TEXT"),
    ("issued_at", "TEXT"),
    ("expires_at", "TEXT"),
    ("applicable_scope", "TEXT"),
    ("extra_fields", "TEXT"),
    ("tags", "TEXT"),
    ("ai_summary", "TEXT"),
    ("ai_confidence", "INTEGER"),
    ("review_status", "TEXT"),
    ("duplicate_of_id", "INTEGER"),
    ("duplicate_reason", "TEXT"),
    ("recognized_at", "TEXT"),
]


def ensure_recognition_columns(conn: sqlite3.Connection) -> None:
    """给老库补识别相关列（sqlite 没有 ADD COLUMN IF NOT EXISTS，按 pragma 判断）。"""
    have = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    for name, col_type in RECOGNITION_COLUMNS:
        if name not in have:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {col_type}")
    conn.commit()


# 最近一次识别失败的真实原因（CLI/调用方诊断用；成功时为空串）
LAST_RECOGNIZE_ERROR = ""


def recognize_via_server(mode: str, text: str, images: list[bytes], page_count: int, filename: str) -> dict[str, Any] | None:
    """把证据（文字或页图 base64）发服务器做 AI 识别，按页计费。
    失败返回 None 并把真实原因写入 LAST_RECOGNIZE_ERROR，调用方退回纯规则识别。"""
    global LAST_RECOGNIZE_ERROR
    LAST_RECOGNIZE_ERROR = ""
    token = STATE.get("token") or ""
    if not token:
        LAST_RECOGNIZE_ERROR = "未注册或离线（没有 token）"
        return None
    body: dict[str, Any] = {
        "mode": mode,
        "filename": filename,
        "page_count": int(page_count),
        "instruction": docintel.extraction_instruction(),
    }
    if mode == "vision":
        body["images"] = [base64.b64encode(b).decode("ascii") for b in images[:4]]
    else:
        body["text"] = text[:20000]
    try:
        resp = request_json("/api/desktop/document/recognize", body, token=token, timeout=300)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
            msg = json.loads(detail).get("message") or detail
        except Exception:
            msg = ""
        LAST_RECOGNIZE_ERROR = f"服务器 HTTP {exc.code}：{str(msg)[:240]}"
        return None
    except Exception as exc:
        LAST_RECOGNIZE_ERROR = f"{type(exc).__name__}：{str(exc)[:240]}"
        return None
    if not isinstance(resp, dict):
        LAST_RECOGNIZE_ERROR = "服务器返回不是 JSON 对象"
        return None
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    content = data.get("content") if isinstance(data, dict) else None
    if isinstance(content, str):
        parsed = docintel.parse_ai_json(content)
        if parsed is None:
            LAST_RECOGNIZE_ERROR = "AI 返回的不是有效 JSON：" + content[:160]
        return parsed
    return data if isinstance(data, dict) else None


def _doc_row_for_analyze(conn: sqlite3.Connection, doc_id: int):
    return conn.execute(
        "SELECT id, original_path, managed_path, file_name, extension, page_count FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()


def _mark_duplicate_by_cert(conn: sqlite3.Connection, doc_id: int, cert_no: str) -> int | None:
    """同证件号查重：命中更早的同号资料则标记为重复（checksum 重复在扫描导入时已挡）。"""
    cert_no = (cert_no or "").strip()
    if len(cert_no) < 4:
        return None
    row = conn.execute(
        "SELECT id FROM documents WHERE certificate_no = ? AND id <> ? ORDER BY id ASC LIMIT 1",
        (cert_no, doc_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE documents SET duplicate_of_id = ?, duplicate_reason = 'certificate' WHERE id = ?",
            (int(row[0]), doc_id),
        )
        return int(row[0])
    return None


def command_analyze_document(args: dict[str, Any]) -> dict[str, Any]:
    """对一份已导入资料做 AI 识别归类，结果进「待确认」。
    args: {id} 资料库里的文档 id。"""
    require_unlocked()
    doc_id = int(args.get("id") or 0)
    if doc_id <= 0:
        raise RuntimeError("缺少资料 id。")

    root = library_dir()
    conn = connect_db(root)
    ensure_recognition_columns(conn)
    row = _doc_row_for_analyze(conn, doc_id)
    if not row:
        conn.close()
        raise RuntimeError("资料不存在。")

    managed, original = str(row[2] or ""), str(row[1] or "")
    path = Path(managed) if managed and Path(managed).exists() else Path(original)
    if not path.exists():
        conn.close()
        raise RuntimeError("源文件已不在原位置，无法识别。")

    page_count = int(row[5] or 1)
    text = docintel.extract_text(path)
    use_vision = docintel.needs_vision(path, text)
    rule = docintel.rule_suggestion(text)

    ai = None
    source = "rule"
    if use_vision:
        images = docintel.render_pages_png(path, max_pages=min(2, page_count))
        if images:
            ai = recognize_via_server("vision", "", images, page_count, path.name)
            if ai is not None:
                source = "vision_ai"
    elif len(text) >= 30:
        ai = recognize_via_server("text", text, [], page_count, path.name)
        if ai is not None:
            source = "text_ai"

    suggestion = docintel.merge_rule_and_ai(rule, ai)
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE documents SET
          document_type = ?, document_type_label = ?, company_name = ?, brand = ?,
          certificate_no = ?, issuer = ?, issued_at = ?, expires_at = ?, applicable_scope = ?,
          extra_fields = ?, tags = ?, ai_summary = ?, ai_confidence = ?,
          review_status = 'pending_review', recognized_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            suggestion["document_type"], suggestion["document_type_label"],
            suggestion["company_name"], suggestion["brand"], suggestion["certificate_no"],
            suggestion["issuer"], suggestion["issued_at"], suggestion["expires_at"],
            suggestion["applicable_scope"], json.dumps(suggestion["extra_fields"], ensure_ascii=False),
            json.dumps(suggestion["tags"], ensure_ascii=False), suggestion["ai_summary"],
            suggestion["ai_confidence"], now, now, doc_id,
        ),
    )
    conn.commit()
    duplicate_of = _mark_duplicate_by_cert(conn, doc_id, suggestion["certificate_no"])
    conn.commit()
    conn.close()

    return {
        "id": doc_id,
        "source": source,
        "used_vision": use_vision,
        "ai_available": ai is not None,
        "suggestion": suggestion,
        "duplicate_of_id": duplicate_of,
        "review_status": "pending_review",
    }


def _row_to_suggestion(r: sqlite3.Row) -> dict[str, Any]:
    """DB 行 → 统一 suggestion 结构（给 project_to_profile 用）。"""
    try:
        extra = json.loads(r["extra_fields"]) if r["extra_fields"] else {}
    except Exception:
        extra = {}
    dtype = r["document_type"] or "other"
    return {
        "document_type": dtype,
        "document_type_label": r["document_type_label"] or docintel.DOCUMENT_TYPES.get(dtype, "其他资料"),
        "company_name": r["company_name"] or "",
        "brand": r["brand"] or "",
        "certificate_no": r["certificate_no"] or "",
        "issuer": r["issuer"] or "",
        "issued_at": r["issued_at"] or "",
        "expires_at": r["expires_at"] or "",
        "applicable_scope": r["applicable_scope"] or "",
        "extra_fields": extra if isinstance(extra, dict) else {},
        "ai_summary": r["ai_summary"] or "",
        "ai_confidence": int(r["ai_confidence"] or 0),
    }


def command_document_meta(_: dict[str, Any]) -> dict[str, Any]:
    """证件类型、主列表列、各类型版面字段——前端动态渲染用（对齐 版面样式.xlsx）。"""
    return {
        "types": [{"key": k, "label": v} for k, v in docintel.DOCUMENT_TYPES.items()],
        "list_columns": docintel.LIST_COLUMNS,
        "profiles": docintel.FIELD_PROFILES,
        "default_profile": docintel.DEFAULT_PROFILE,
    }


def command_list_documents(args: dict[str, Any]) -> dict[str, Any]:
    """资料库列表：按主列表列返回，支持按 review_status / document_type 过滤。"""
    require_unlocked()
    root = library_dir()
    conn = connect_db(root)
    where, params = ["1=1"], []
    status = str(args.get("review_status") or "").strip()
    dtype = str(args.get("document_type") or "").strip()
    if status:
        where.append("review_status = ?")
        params.append(status)
    if dtype:
        where.append("document_type = ?")
        params.append(dtype)
    rows = conn.execute(
        f"SELECT * FROM documents WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 500", params
    ).fetchall()

    docs = []
    for r in rows:
        sug = _row_to_suggestion(r)
        list_values = {}
        for col in docintel.LIST_COLUMNS:
            key = col["key"]
            list_values[key] = sug["document_type_label"] if key == "document_type_label" else sug.get(key, "")
        docs.append({
            "id": r["id"], "file_name": r["file_name"], "extension": r["extension"],
            "page_count": r["page_count"], "review_status": r["review_status"] or "",
            "recognized": bool(r["recognized_at"]), "is_duplicate": bool(r["duplicate_of_id"]),
            "document_type": sug["document_type"], "document_type_label": sug["document_type_label"],
            "ai_confidence": sug["ai_confidence"], "list_values": list_values,
        })

    def count(sql, p=()):
        return int(conn.execute(sql, p).fetchone()[0])

    stats = {
        "total": count("SELECT COUNT(*) FROM documents"),
        "unrecognized": count("SELECT COUNT(*) FROM documents WHERE recognized_at IS NULL"),
        "pending": count("SELECT COUNT(*) FROM documents WHERE review_status='pending_review'"),
        "confirmed": count("SELECT COUNT(*) FROM documents WHERE review_status='confirmed'"),
        "duplicate": count("SELECT COUNT(*) FROM documents WHERE duplicate_of_id IS NOT NULL"),
    }
    conn.close()
    return {"documents": docs, "stats": stats}


def command_get_document(args: dict[str, Any]) -> dict[str, Any]:
    """单份资料详情：按类型版面投影出有序字段，给详情/编辑用。"""
    require_unlocked()
    doc_id = int(args.get("id") or 0)
    conn = connect_db(library_dir())
    r = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if not r:
        raise RuntimeError("资料不存在。")
    sug = _row_to_suggestion(r)
    return {
        "id": r["id"], "file_name": r["file_name"], "extension": r["extension"],
        "page_count": r["page_count"], "managed_path": r["managed_path"] or "", "original_path": r["original_path"] or "",
        "review_status": r["review_status"] or "", "recognized": bool(r["recognized_at"]),
        "document_type": sug["document_type"], "document_type_label": sug["document_type_label"],
        "ai_confidence": sug["ai_confidence"], "ai_summary": sug["ai_summary"],
        "profile": docintel.project_to_profile(sug),
    }


def command_confirm_document(args: dict[str, Any]) -> dict[str, Any]:
    """保存人工核对后的字段并改状态（确认/驳回）。
    args: {id, document_type, values:{source: value}, review_status}"""
    require_unlocked()
    doc_id = int(args.get("id") or 0)
    if doc_id <= 0:
        raise RuntimeError("缺少资料 id。")
    dtype = str(args.get("document_type") or "other")
    if dtype not in docintel.DOCUMENT_TYPES:
        dtype = "other"
    review_status = str(args.get("review_status") or "confirmed")
    values = args.get("values") if isinstance(args.get("values"), dict) else {}

    top = {"company_name": "", "brand": "", "certificate_no": "", "issuer": "",
           "issued_at": "", "expires_at": "", "applicable_scope": ""}
    extra: dict[str, Any] = {}
    for source, value in values.items():
        text = str(value or "").strip()
        if str(source).startswith("extra:"):
            key = str(source).split(":", 1)[1]
            if text:
                extra[key] = text
        elif source in top:
            top[source] = docintel.normalize_date(text) if source in ("issued_at", "expires_at") else text

    conn = connect_db(library_dir())
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE documents SET
          document_type = ?, document_type_label = ?, company_name = ?, brand = ?,
          certificate_no = ?, issuer = ?, issued_at = ?, expires_at = ?, applicable_scope = ?,
          extra_fields = ?, review_status = ?, updated_at = ?
        WHERE id = ?
        """,
        (dtype, docintel.DOCUMENT_TYPES[dtype], top["company_name"], top["brand"], top["certificate_no"],
         top["issuer"], top["issued_at"], top["expires_at"], top["applicable_scope"],
         json.dumps(extra, ensure_ascii=False), review_status, now, doc_id),
    )
    conn.commit()
    duplicate_of = _mark_duplicate_by_cert(conn, doc_id, top["certificate_no"])
    conn.commit()
    conn.close()
    return {"id": doc_id, "review_status": review_status, "duplicate_of_id": duplicate_of}


def command_library_summary(_: dict[str, Any]) -> dict[str, Any]:
    require_unlocked()
    try:
        root = library_dir()
    except RuntimeError:
        return {"configured": False, "documents": 0, "pages": 0, "library_dir": ""}
    conn = connect_db(root)
    row = conn.execute("SELECT COUNT(*), COALESCE(SUM(page_count), 0) FROM documents").fetchone()
    recent = conn.execute(
        "SELECT file_name, extension, page_count, status, created_at FROM documents ORDER BY id DESC LIMIT 12"
    ).fetchall()
    conn.close()
    return {
        "configured": True,
        "library_dir": str(root),
        "documents": int(row[0] or 0),
        "pages": int(row[1] or 0),
        "recent": [
            {
                "name": item[0],
                "extension": item[1],
                "pages": item[2],
                "status": item[3],
                "created_at": item[4],
            }
            for item in recent
        ],
    }


COMMANDS = {
    "get_serial": command_get_serial,
    "register": command_register,
    "sync_quota": command_sync_quota,
    "get_state": command_get_state,
    "set_password": command_set_password,
    "verify_password": command_verify_password,
    "set_library_dir": command_set_library_dir,
    "scan_folder": command_scan_folder,
    "analyze_document": command_analyze_document,
    "document_meta": command_document_meta,
    "list_documents": command_list_documents,
    "get_document": command_get_document,
    "confirm_document": command_confirm_document,
    "library_summary": command_library_summary,
}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            request_id = message.get("id")
            cmd = str(message.get("cmd") or "")
            args = message.get("args") or {}
            if cmd not in COMMANDS:
                raise RuntimeError(f"未知命令：{cmd}")
            data = COMMANDS[cmd](args)
            emit({"id": request_id, "ok": True, "data": data})
        except Exception as exc:
            emit({"id": locals().get("request_id"), "ok": False, "error": str(exc)})


if __name__ == "__main__":
    main()
