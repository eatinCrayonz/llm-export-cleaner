from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_export_cleaner.claude_projects import apply_page, parse_page  # noqa: E402
from llm_export_cleaner.exporter import export_cleaned  # noqa: E402
from llm_export_cleaner.library import (  # noqa: E402
    get_conversation, import_export, import_history, list_conversations,
    save_profile, search, stats,
)
from llm_export_cleaner.normalizers import Audit, normalize_chatgpt, normalize_claude, normalize_grok  # noqa: E402


class NormalizerTests(unittest.TestCase):
    def test_chatgpt_discards_alternative_branch_and_preserves_project(self) -> None:
        payload = [{
            "conversation_id": "c1", "title": "Branched", "current_node": "a2",
            "gizmo_type": "snorlax", "gizmo_id": "g-p-project",
            "mapping": {
                "u": {"parent": None, "message": {"id": "u", "author": {"role": "user"}, "content": {"parts": ["Question"]}}},
                "a1": {"parent": "u", "message": {"id": "a1", "author": {"role": "assistant"}, "content": {"parts": ["Old answer"]}}},
                "a2": {"parent": "u", "message": {"id": "a2", "author": {"role": "assistant"}, "content": {"parts": ["Current answer"]}}},
            },
        }]
        audit = Audit()
        record = list(normalize_chatgpt(payload, audit))[0]
        self.assertEqual(record["project_id"], "g-p-project")
        self.assertEqual([m["text"] for m in record["messages"]], ["Question", "Current answer"])
        self.assertEqual(sum(m["is_alternative"] for m in record["messages"]), 0)
        self.assertEqual(audit.exclusion_reasons["alternative_branch"], 1)
        self.assertEqual(record["active_leaf_message_id"], "a2")

    def test_claude_and_grok_minimal_shapes(self) -> None:
        claude = [{"uuid": "c", "name": "Claude", "chat_messages": [{"uuid": "u", "sender": "human", "text": "Hi"}, {"uuid": "a", "sender": "assistant", "text": "Hello"}]}]
        grok = {"conversations": [{"conversation": {"_id": "g", "title": "Grok"}, "responses": [{"response": {"_id": "u", "sender": "human", "message": "Hi"}}, {"response": {"_id": "a", "sender": "grok-3", "message": "Hello"}}]}]}
        self.assertEqual(len(list(normalize_claude(claude, Audit()))[0]["messages"]), 2)
        self.assertEqual(len(list(normalize_grok(grok, Audit()))[0]["messages"]), 2)


class LibraryTests(unittest.TestCase):
    def _write_claude(self, path: Path, *, extended: bool = False) -> None:
        messages = [{"uuid": "u1", "sender": "human", "text": "How does evolution work?", "created_at": "2025-01-01T00:00:00Z"}, {"uuid": "a1", "sender": "assistant", "text": "Through inherited variation.", "created_at": "2025-01-01T00:01:00Z"}]
        if extended:
            messages += [{"uuid": "u2", "sender": "human", "text": "Explain selection pressure", "created_at": "2025-02-01T00:00:00Z"}, {"uuid": "a2", "sender": "assistant", "text": "It changes reproductive outcomes.", "created_at": "2025-02-01T00:01:00Z"}]
        path.write_text(json.dumps([{"uuid": "c1", "name": "Evolution", "created_at": "2025-01-01T00:00:00Z", "updated_at": "2025-02-01T00:01:00Z" if extended else "2025-01-01T00:01:00Z", "chat_messages": messages}]), encoding="utf-8")

    def test_incremental_import_filter_search_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); db = root / "cleaner.sqlite3"
            first_file = root / "first.json"; second_file = root / "second.json"
            self._write_claude(first_file)
            first = import_export(provider="claude", input_path=first_file, database_path=db)
            duplicate = import_export(provider="claude", input_path=first_file, database_path=db)
            self._write_claude(second_file, extended=True)
            second = import_export(provider="claude", input_path=second_file, database_path=db)
            matches = search(database_path=db, query="selection pressure")
            output = root / "clean.jsonl"
            manifest = export_cleaned(database_path=db, output_path=output)
            transcript = get_conversation(db, "claude", "c1")
            totals = stats(db)
        self.assertEqual(first["new_conversations"], 1)
        self.assertTrue(duplicate["duplicate_export"])
        self.assertEqual(second["changed_conversations"], 1)
        self.assertEqual(second["new_messages"], 2)
        self.assertEqual(len(matches), 1)
        self.assertEqual(len(transcript["messages"]), 4)
        self.assertEqual(totals["included"], 1)
        self.assertEqual(manifest["conversations_exported"], 1)
        self.assertGreater(manifest["output_bytes"], 0)

    def test_profile_filter_is_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); db = root / "cleaner.sqlite3"; export = root / "one.json"
            self._write_claude(export)
            import_export(provider="claude", input_path=export, database_path=db)
            self.assertEqual(stats(db)["filtered"], 1)
            save_profile(db, {"name": "Keep all", "exclude_single_exchange": False, "minimum_user_turns": 0})
            self.assertEqual(stats(db, "Keep all")["included"], 1)
            self.assertEqual(len(list_conversations(database_path=db, profile_name="Keep all")), 1)

    def test_older_overlapping_export_does_not_regress_newer_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); db = root / "cleaner.sqlite3"
            newer = root / "newer.json"; older = root / "older.json"
            self._write_claude(newer, extended=True)
            import_export(provider="claude", input_path=newer, database_path=db)
            self._write_claude(older)
            payload = json.loads(older.read_text(encoding="utf-8"))
            payload[0]["name"] = "Stale title"
            older.write_text(json.dumps(payload), encoding="utf-8")
            result = import_export(provider="claude", input_path=older, database_path=db)
            conversation = get_conversation(db, "claude", "c1")
        self.assertEqual(result["changed_conversations"], 0)
        self.assertEqual(conversation["title"], "Evolution")
        self.assertEqual(len(conversation["messages"]), 4)

    def test_claude_project_page_updates_exact_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); db = root / "cleaner.sqlite3"; export = root / "one.json"
            self._write_claude(export, extended=True)
            import_export(provider="claude", input_path=export, database_path=db)
            page = json.dumps({"data": [{"uuid": "c1", "project_uuid": "p1", "project": {"uuid": "p1", "name": "Research"}}], "has_more": False})
            parsed = parse_page(page)
            result = apply_page(database_path=db, page_text=page)
            rows = list_conversations(database_path=db, in_project=True)
        self.assertEqual(parsed["projects"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(rows[0]["project_id"], "p1")
        self.assertEqual(rows[0]["project_name"], "Research")

    def test_delta_export_uses_import_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); db = root / "cleaner.sqlite3"; first_file = root / "first.json"; second_file = root / "second.json"
            self._write_claude(first_file, extended=True)
            first = import_export(provider="claude", input_path=first_file, database_path=db)
            self._write_claude(second_file, extended=True)
            payload = json.loads(second_file.read_text(encoding="utf-8")); payload.append({"uuid": "c2", "name": "New", "chat_messages": [{"uuid": "u", "sender": "human", "text": "One"}, {"uuid": "a", "sender": "assistant", "text": "Two"}, {"uuid": "u2", "sender": "human", "text": "Three"}]}); second_file.write_text(json.dumps(payload), encoding="utf-8")
            second = import_export(provider="claude", input_path=second_file, database_path=db)
            save_profile(db, {"name": "All", "exclude_single_exchange": False, "minimum_user_turns": 0})
            result = export_cleaned(database_path=db, output_path=root / "delta.json", profile_name="All", import_id=second["import_id"])
            history = import_history(db)
        self.assertEqual(first["new_conversations"], 1)
        self.assertEqual(result["conversations_exported"], 1)
        self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
