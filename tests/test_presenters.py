from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_export_cleaner.ui import presenters  # noqa: E402


class RowFormattingTests(unittest.TestCase):
    def test_included_row_shows_snippet_when_present(self) -> None:
        row = {
            "provider": "claude", "title": "Evolution", "updated_at": "2025-02-01T00:01:00Z",
            "created_at": "2025-01-01T00:00:00Z", "active_user_turn_count": 2,
            "project_name": "Research", "included": 1, "snippet": "inherited [variation]",
        }
        self.assertEqual(
            presenters.format_row(row),
            ("2025-02-01 00:01", "claude", 2, "Research", "Evolution", "inherited [variation]"),
        )

    def test_excluded_row_shows_joined_reasons(self) -> None:
        row = {"provider": "grok", "included": 0, "reasons": ["single_exchange", "not_in_project"]}
        values = presenters.format_row(row)
        self.assertEqual(values[5], "single_exchange, not_in_project")

    def test_row_defaults_for_missing_fields(self) -> None:
        values = presenters.format_row({"provider": "chatgpt"})
        self.assertEqual(values, ("", "chatgpt", 0, "", "Untitled", "Included"))

    def test_date_falls_back_from_updated_to_created(self) -> None:
        row = {"provider": "claude", "created_at": "2025-01-01T00:00:00Z"}
        self.assertEqual(presenters.format_row(row)[0], "2025-01-01 00:00")

    def test_display_date_passes_short_or_odd_values_through(self) -> None:
        self.assertEqual(presenters.display_date(""), "")
        self.assertEqual(presenters.display_date("2025-05-14"), "2025-05-14")


class SortingTests(unittest.TestCase):
    def test_turns_sort_key_parses_integers_and_defaults(self) -> None:
        self.assertEqual(presenters.sort_key("turns", "12"), 12)
        self.assertEqual(presenters.sort_key("turns", "import"), -1)
        self.assertEqual(presenters.sort_key("turns", ""), -1)

    def test_date_sort_key_parses_iso_and_defaults(self) -> None:
        self.assertAlmostEqual(presenters.sort_key("date", "1970-01-01T00:00:10Z"), 10.0)
        self.assertGreater(presenters.sort_key("date", "2025-05-14 10:01"), presenters.sort_key("date", "2025-05-14 10:00"))
        self.assertEqual(presenters.sort_key("date", ""), float("-inf"))
        self.assertEqual(presenters.sort_key("date", "not a date"), float("-inf"))

    def test_text_sort_key_is_case_insensitive(self) -> None:
        self.assertEqual(presenters.sort_key("title", "ABC"), "abc")

    def test_toggle_sort_starts_ascending_then_flips(self) -> None:
        self.assertEqual(presenters.toggle_sort(None, False, "date"), ("date", False))
        self.assertEqual(presenters.toggle_sort("date", False, "date"), ("date", True))
        self.assertEqual(presenters.toggle_sort("date", True, "date"), ("date", False))
        self.assertEqual(presenters.toggle_sort("date", True, "title"), ("title", False))

    def test_heading_labels_mark_only_active_column(self) -> None:
        ascending = presenters.heading_labels("turns", descending=False)
        descending = presenters.heading_labels("turns", descending=True)
        self.assertTrue(ascending["turns"].endswith("▲"))
        self.assertTrue(descending["turns"].endswith("▼"))
        self.assertEqual(ascending["date"], presenters.COLUMN_LABELS["date"])
        self.assertEqual(presenters.heading_labels(None, descending=False)["turns"], presenters.COLUMN_LABELS["turns"])


class FilterMappingTests(unittest.TestCase):
    def test_provider_filter(self) -> None:
        self.assertIsNone(presenters.provider_filter("All providers"))
        self.assertEqual(presenters.provider_filter("claude"), "claude")


class SelectionTests(unittest.TestCase):
    def test_selected_keys_preserve_visible_order_and_skip_non_conversations(self) -> None:
        rows = {
            "r0": {"provider": "claude", "conversation_id": "c2"},
            "r1": {"provider": "chatgpt", "conversation_id": "c1"},
            "r2": {"provider": "claude", "conversation_id": ""},  # history row
            "r3": {},
        }
        keys = presenters.selected_keys(("r0", "r1", "r2", "r3"), rows, {"r1", "r0", "r2", "r3"})
        self.assertEqual(keys, [("claude", "c2"), ("chatgpt", "c1")])

    def test_selected_keys_only_include_selected(self) -> None:
        rows = {"r0": {"provider": "grok", "conversation_id": "g1"}}
        self.assertEqual(presenters.selected_keys(("r0",), rows, set()), [])


class HistoryTests(unittest.TestCase):
    def test_history_rows_shape(self) -> None:
        records = [{
            "provider": "claude", "source_file": "export.json", "imported_at_utc": "2025-06-01T00:00:00Z",
            "new_conversations": 3, "changed_conversations": 1, "unchanged_conversations": 7,
        }]
        row = presenters.history_rows(records)[0]
        self.assertEqual(row["title"], "export.json")
        self.assertEqual(presenters.format_row(row)[0], "2025-06-01 00:00")
        self.assertEqual(row["active_user_turn_count"], "import")
        self.assertEqual(row["conversation_id"], "")
        self.assertEqual(row["snippet"], "3 new; 1 changed; 7 unchanged")


class StatusTextTests(unittest.TestCase):
    def test_progress_text_groups_thousands(self) -> None:
        self.assertEqual(presenters.progress_text(1200, 34000), "Scanning 1,200/34,000")

    def test_import_status_duplicate_and_counts(self) -> None:
        self.assertEqual(presenters.import_status_text({"duplicate_export": True}), "Already imported")
        payload = {"duplicate_export": False, "new_conversations": 2, "changed_conversations": 0, "unchanged_conversations": 5}
        self.assertEqual(presenters.import_status_text(payload), "2 new; 0 changed; 5 unchanged")
        payload["project_names_imported"] = 17
        self.assertEqual(presenters.import_status_text(payload), "2 new; 0 changed; 5 unchanged; 17 project names")

    def test_stats_and_profile_status(self) -> None:
        payload = {"conversations": 1247, "messages": 18932, "imports": 9, "included": 1189, "filtered": 58}
        self.assertEqual(presenters.stats_text(payload), "1,247 conversations | 18,932 messages | 9 imports")
        self.assertEqual(presenters.profile_status_text(payload), "1,189 included | 58 filtered out")

    def test_export_status(self) -> None:
        payload = {"conversations_exported": 1189, "output_bytes": 52400}
        self.assertEqual(presenters.export_status_text(payload), "Exported 1,189 conversations (52,400 bytes)")

    def test_claude_status_for_both_page_kinds(self) -> None:
        projects = {"kind": "projects", "named_projects": 4, "has_more": False, "next_offset": 30}
        membership = {"kind": "conversations", "updated": 2, "unknown": 1, "has_more": True, "next_offset": 60}
        self.assertEqual(presenters.claude_status_text(projects), "Claude Projects: 4 names saved")
        self.assertEqual(
            presenters.claude_status_text(membership),
            "Claude Projects: 2 updated, 1 unknown; more at offset 60",
        )

    def test_chatgpt_projects_status(self) -> None:
        payload = {"matched": 3, "still_unnamed": 1, "has_more": False}
        self.assertEqual(presenters.chatgpt_projects_status_text(payload), "ChatGPT Projects: 3 matched, 1 still unnamed")
        payload["has_more"] = True
        self.assertTrue(presenters.chatgpt_projects_status_text(payload).endswith("; additional cursor page exists"))


class TranscriptTests(unittest.TestCase):
    def test_transcript_blocks_label_roles(self) -> None:
        user = {"role": "user", "text": "Hi", "created_at": "2025-01-01T00:00:00Z"}
        assistant = {"role": "assistant", "text": "Hello", "created_at": None}
        self.assertEqual(presenters.transcript_block(user), "YOU | 2025-01-01T00:00:00Z\nHi\n\n")
        self.assertEqual(presenters.transcript_block(assistant), "ASSISTANT | \nHello\n\n")


if __name__ == "__main__":
    unittest.main()
