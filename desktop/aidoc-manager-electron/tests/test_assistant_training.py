from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backend  # noqa: E402


class AssistantTrainingDataTests(unittest.TestCase):
    def test_ambiguous_contract_request_is_clarified_locally(self) -> None:
        result = backend._assistant_local_clarification("帮我做合同")
        self.assertIsNotNone(result)
        self.assertEqual(4, len(result["quick_options"]))
        self.assertIn("起草新合同", [item["label"] for item in result["quick_options"]])

    def test_template_text_is_only_sent_for_document_generation(self) -> None:
        self.assertFalse(backend._assistant_needs_template_context("合同付款时间是什么"))
        self.assertTrue(backend._assistant_needs_template_context("请生成一份新的采购合同"))

    def test_connection_failure_becomes_non_rateable_dialog(self) -> None:
        result = backend._assistant_fallback("查询开户资料", "remote disconnected")
        self.assertFalse(result["rateable"])
        self.assertEqual("查询开户资料", result["quick_options"][0]["message"])

    def test_conversation_title_can_be_renamed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            chat_dir = Path(temp_dir)
            conversation_id = "b" * 32
            path = chat_dir / f"{conversation_id}.json"
            path.write_text(json.dumps({
                "id": conversation_id,
                "title": "旧名称",
                "messages": [{"role": "user", "text": "测试"}],
            }, ensure_ascii=False), "utf-8")

            with (
                patch.object(backend, "require_unlocked", lambda: None),
                patch.object(backend, "_assistant_chat_dir", lambda: chat_dir),
            ):
                result = backend.command_assistant_conversation_rename({
                    "id": conversation_id,
                    "title": "新的聊天名称",
                })

            self.assertEqual("新的聊天名称", result["conversation"]["title"])
            saved = json.loads(path.read_text("utf-8"))
            self.assertEqual("新的聊天名称", saved["title"])

    def test_rating_is_saved_on_ai_message(self) -> None:
        cleaned = backend._clean_saved_message({
            "role": "ai",
            "text": "这是回答",
            "rateable": True,
            "rating": 5,
            "ratingFeedback": "答案准确，可以直接使用。",
            "ratedAt": "2026-06-30T13:00:00+08:00",
        })

        self.assertEqual(5, cleaned["rating"])
        self.assertEqual("答案准确，可以直接使用。", cleaned["rating_feedback"])
        self.assertTrue(cleaned["rateable"])

    def test_export_contains_only_rated_question_answer_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chat_dir = root / "AI秘书聊天记录"
            chat_dir.mkdir()
            conversation = {
                "id": "a" * 32,
                "title": "合同查询",
                "messages": [
                    {"role": "user", "text": "帮我找采购合同"},
                    {
                        "role": "ai",
                        "text": "找到了合同。",
                        "rating": 4,
                        "rating_feedback": "结果正确，但可以说明文件日期。",
                        "rated_at": "2026-06-30T13:10:00+08:00",
                        "materials": [{"id": 89, "file_name": "采购合同.pdf"}],
                    },
                    {"role": "user", "text": "再说一句"},
                    {"role": "ai", "text": "这条没有评分。"},
                ],
            }
            (chat_dir / ("a" * 32 + ".json")).write_text(
                json.dumps(conversation, ensure_ascii=False), "utf-8"
            )

            with (
                patch.object(backend, "require_unlocked", lambda: None),
                patch.object(backend, "_assistant_chat_dir", lambda: chat_dir),
                patch.object(backend, "library_dir", lambda: root),
            ):
                result = backend.command_assistant_training_export({})

            self.assertEqual(1, result["count"])
            lines = Path(result["file_path"]).read_text("utf-8").splitlines()
            self.assertEqual(1, len(lines))
            record = json.loads(lines[0])
            self.assertEqual("帮我找采购合同", record["question"])
            self.assertEqual("找到了合同。", record["answer"])
            self.assertEqual(4, record["rating"])
            self.assertEqual([89], record["document_refs"])


if __name__ == "__main__":
    unittest.main()
