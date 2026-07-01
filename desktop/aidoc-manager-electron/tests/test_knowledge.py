from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import knowledge  # noqa: E402


DOCUMENT_SCHEMA = """
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  original_path TEXT NOT NULL,
  managed_path TEXT,
  file_name TEXT NOT NULL,
  extension TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  recognized_at TEXT,
  document_type_label TEXT,
  company_name TEXT,
  brand TEXT,
  certificate_no TEXT,
  issuer TEXT,
  issued_at TEXT,
  expires_at TEXT,
  applicable_scope TEXT,
  ai_summary TEXT,
  tags TEXT
)
"""


class KnowledgeIndexTests(unittest.TestCase):
    def test_existing_recognized_document_is_backfilled_and_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "采购合同.txt"
            source.write_text(
                "格力空调采购合同。付款时间为设备验收后三个工作日内支付全部货款。",
                "utf-8",
            )
            db_file = root / "aidoc.db"
            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            conn.execute(DOCUMENT_SCHEMA)
            conn.execute(
                """
                INSERT INTO documents
                  (id, original_path, file_name, extension, sha256, recognized_at,
                   document_type_label, company_name, ai_summary, tags)
                VALUES (1, ?, ?, '.txt', ?, '2026-06-30T12:00:00', '合同/协议',
                        '西安稻叶山供应链管理有限公司', '空调采购合同', '["合同"]')
                """,
                (str(source), source.name, hashlib.sha256(source.read_bytes()).hexdigest()),
            )
            conn.commit()
            knowledge.ensure_tables(conn)
            self.assertEqual([1], knowledge.pending_document_ids(conn))
            conn.close()

            result = knowledge.index_document(db_file, 1)
            self.assertTrue(result["indexed"])
            self.assertEqual("full", result["status"])

            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            self.assertEqual([], knowledge.pending_document_ids(conn))
            hits = knowledge.search(conn, "合同付款时间是什么", limit=5)
            conn.close()
            self.assertTrue(hits)
            self.assertEqual(1, hits[0]["document_id"])
            self.assertIn("验收后三个工作日", "".join(hit["text"] for hit in hits))

    def test_file_without_text_layer_still_indexes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "营业执照.png"
            source.write_bytes(b"not-an-image-but-existing")
            db_file = root / "aidoc.db"
            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            conn.execute(DOCUMENT_SCHEMA)
            conn.execute(
                """
                INSERT INTO documents
                  (id, original_path, file_name, extension, sha256, recognized_at,
                   document_type_label, company_name, ai_summary, tags)
                VALUES (2, ?, ?, '.png', 'abc', '2026-06-30T12:00:00', '营业执照',
                        '西安鼎瑞环境设备有限公司', '供应商营业执照', '["营业执照"]')
                """,
                (str(source), source.name),
            )
            conn.commit()
            conn.close()

            result = knowledge.index_document(db_file, 2)
            self.assertEqual("metadata_only", result["status"])
            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            hits = knowledge.search(conn, "西安鼎瑞环境设备", limit=5)
            conn.close()
            self.assertTrue(hits)
            self.assertEqual("metadata", hits[0]["kind"])


if __name__ == "__main__":
    unittest.main()
