"""本地文书模板资源池。

模板只保存从本地资料提取的文本、变量提示和来源信息；原文件不上传。
资源池与 documents 分开，删除或移动来源文件后，已提炼的文本模板仍可使用。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import docintel


REUSABLE_TYPES = {
    "contract",
    "authorization_letter",
    "tax_certificate",
    "other",
}

PLACEHOLDER_LABELS = {
    "company_name": "甲方/归属公司",
    "issuer": "乙方/出具方",
    "certificate_no": "文书编号",
    "issued_at": "签署/出具日期",
    "expires_at": "截止日期",
    "brand": "品牌",
}


def ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_templates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_document_id INTEGER,
          name TEXT NOT NULL,
          document_type TEXT NOT NULL DEFAULT 'other',
          type_label TEXT NOT NULL DEFAULT '其他文书',
          source_file_name TEXT NOT NULL DEFAULT '',
          content_text TEXT NOT NULL,
          template_text TEXT NOT NULL,
          variables_json TEXT NOT NULL DEFAULT '[]',
          summary TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'active',
          enabled INTEGER NOT NULL DEFAULT 1,
          use_count INTEGER NOT NULL DEFAULT 0,
          last_used_at TEXT,
          content_hash TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_document_templates_source "
        "ON document_templates(source_document_id) WHERE source_document_id IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_templates_type "
        "ON document_templates(document_type, enabled, updated_at)"
    )
    conn.commit()


def _clean_text(text: str) -> str:
    text = str(text or "").replace("\x00", "").replace("\u2f8f", "行")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()[:120000]


def _extra_fields(row) -> dict[str, Any]:
    try:
        value = json.loads(str(row["extra_fields"] or "{}"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _variable_template(text: str, row) -> tuple[str, list[dict[str, str]]]:
    # 正文保留原文，变量单独列出。这样合同解析器能继续识别原条款，用户编辑资源池正文也会真正生效。
    result = text
    variables: list[dict[str, str]] = []
    known: list[tuple[str, str, str]] = []
    for key, label in PLACEHOLDER_LABELS.items():
        value = str(row[key] or "").strip()
        if len(value) >= 2:
            known.append((key, label, value))

    for key, value in _extra_fields(row).items():
        value = str(value or "").strip()
        if len(value) >= 2 and len(value) <= 200:
            known.append((f"extra_{key}", str(key), value))

    # 先替换长文本，避免短值破坏长值。
    seen: set[str] = set()
    for key, label, value in sorted(known, key=lambda item: len(item[2]), reverse=True):
        if value in seen or value not in result:
            continue
        seen.add(value)
        variables.append({"key": key, "label": label, "example": value})

    return result, variables


def _template_name(row) -> str:
    extra = _extra_fields(row)
    dtype = str(row["document_type"] or "other")
    label = str(row["document_type_label"] or docintel.DOCUMENT_TYPES.get(dtype, "其他文书"))
    subtype = str(extra.get("contract_type") or "").strip()
    company = str(row["company_name"] or "").strip()
    stem = Path(str(row["file_name"] or "文书")).stem
    if subtype:
        return f"{subtype}{label}"[:100]
    if dtype == "authorization_letter" and company:
        return f"{company}授权书模板"[:100]
    return f"{stem}模板"[:100]


def upsert_from_document(conn, document_id: int, *, active: bool = True, force: bool = False) -> dict[str, Any] | None:
    """从一份已识别资料提炼/更新模板。文字不足时跳过。"""
    ensure_table(conn)
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (int(document_id),)).fetchone()
    if not row:
        return None
    dtype = str(row["document_type"] or "other")
    if not force and dtype not in REUSABLE_TYPES:
        return None

    managed = str(row["managed_path"] or "").strip()
    original = str(row["original_path"] or "").strip()
    path = Path(managed) if managed and Path(managed).exists() else (Path(original) if original else None)
    content = _clean_text(docintel.extract_text(path)) if path is not None and path.is_file() else ""
    # 扫描件可能没有本地文字层。保留识别摘要作为候选，但不把短摘要冒充完整模板。
    if len(content) < 80:
        return None

    template_text, variables = _variable_template(content, row)
    digest = hashlib.sha256(content.encode("utf-8", "ignore")).hexdigest()
    now = datetime.now().isoformat(timespec="seconds")
    status = "active" if active else "candidate"
    summary = str(row["ai_summary"] or row["applicable_scope"] or "").strip()[:500]
    existing = conn.execute(
        "SELECT id, name, enabled FROM document_templates WHERE source_document_id = ?",
        (int(document_id),),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE document_templates SET document_type = ?, type_label = ?, source_file_name = ?,
               content_text = ?, template_text = ?, variables_json = ?, summary = ?, status = ?,
               content_hash = ?, updated_at = ? WHERE id = ?""",
            (
                dtype,
                str(row["document_type_label"] or docintel.DOCUMENT_TYPES.get(dtype, "其他文书")),
                str(row["file_name"] or ""),
                content,
                template_text,
                json.dumps(variables, ensure_ascii=False),
                summary,
                status,
                digest,
                now,
                int(existing["id"]),
            ),
        )
        template_id = int(existing["id"])
    else:
        cursor = conn.execute(
            """INSERT INTO document_templates
               (source_document_id, name, document_type, type_label, source_file_name, content_text,
                template_text, variables_json, summary, status, enabled, use_count, content_hash,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?)""",
            (
                int(document_id),
                _template_name(row),
                dtype,
                str(row["document_type_label"] or docintel.DOCUMENT_TYPES.get(dtype, "其他文书")),
                str(row["file_name"] or ""),
                content,
                template_text,
                json.dumps(variables, ensure_ascii=False),
                summary,
                status,
                digest,
                now,
                now,
            ),
        )
        template_id = int(cursor.lastrowid)
    conn.commit()
    return get_template(conn, template_id)


def payload(row, *, include_content: bool = True) -> dict[str, Any]:
    try:
        variables = json.loads(str(row["variables_json"] or "[]"))
    except Exception:
        variables = []
    item = {
        "id": int(row["id"]),
        "source_document_id": int(row["source_document_id"] or 0),
        "name": str(row["name"] or ""),
        "document_type": str(row["document_type"] or "other"),
        "type_label": str(row["type_label"] or "其他文书"),
        "source_file_name": str(row["source_file_name"] or ""),
        "variables": variables if isinstance(variables, list) else [],
        "summary": str(row["summary"] or ""),
        "status": str(row["status"] or "active"),
        "enabled": bool(row["enabled"]),
        "use_count": int(row["use_count"] or 0),
        "last_used_at": str(row["last_used_at"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }
    if include_content:
        item["content_text"] = str(row["content_text"] or "")
        item["template_text"] = str(row["template_text"] or "")
    return item


def get_template(conn, template_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM document_templates WHERE id = ?", (int(template_id),)).fetchone()
    return payload(row) if row else None


def rank_for_message(row, message: str) -> int:
    query = str(message or "").casefold()
    haystack = " ".join(
        str(row[key] or "") for key in ("name", "type_label", "source_file_name", "summary")
    ).casefold()
    score = 0
    if "合同" in query and str(row["document_type"] or "") == "contract":
        score += 20
    if "授权" in query and str(row["document_type"] or "") == "authorization_letter":
        score += 20
    for token in set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_-]{3,}", query)):
        if token in haystack:
            score += 3
    score += min(int(row["use_count"] or 0), 5)
    return score
