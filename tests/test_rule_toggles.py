from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_export_cleaner.library import import_export, list_profiles, stats  # noqa: E402


def seed(path: Path) -> None:
    conversations = [
        {"uuid": "long", "name": "Long chat", "chat_messages": [
            {"uuid": "l1", "sender": "human", "text": "One"}, {"uuid": "l2", "sender": "assistant", "text": "A"},
            {"uuid": "l3", "sender": "human", "text": "Two"}, {"uuid": "l4", "sender": "assistant", "text": "B"},
        ]},
        {"uuid": "short", "name": "Single exchange", "chat_messages": [
            {"uuid": "s1", "sender": "human", "text": "Hi"}, {"uuid": "s2", "sender": "assistant", "text": "Hello"},
        ]},
        {"uuid": "proj", "name": "Short project chat", "project_uuid": "p1", "chat_messages": [
            {"uuid": "p1m", "sender": "human", "text": "Hi"}, {"uuid": "p2m", "sender": "assistant", "text": "Hello"},
        ]},
    ]
    path.write_text(json.dumps(conversations), encoding="utf-8")


class RuleToggleTests(unittest.TestCase):
    """Every panel-4 toggle must persist, and filter rules must change the counts."""

    def setUp(self) -> None:
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk unavailable: {error}")
        self.root.withdraw()
        self._temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database = Path(self._temporary.name) / "cleaner.sqlite3"
        export = Path(self._temporary.name) / "seed.json"
        seed(export)
        import_export(provider="claude", input_path=export, database_path=self.database)
        from llm_export_cleaner.ui.app import CleanerApp
        self.app = CleanerApp(self.root, database_path=self.database)
        self.root.update()

    def tearDown(self) -> None:
        self.root.destroy()
        self._temporary.cleanup()

    def _saved(self, key: str):
        profiles = {p["name"]: p for p in list_profiles(self.database)}
        return profiles["Default"][key]

    def test_every_toggle_persists_both_directions(self) -> None:
        for key, toggle in self.app.profile_toggles.items():
            before = bool(toggle._variable.get())
            toggle.invoke()
            self.assertEqual(bool(self._saved(key)), not before, key)
            toggle.invoke()
            self.assertEqual(bool(self._saved(key)), before, key)

    def test_toggling_reports_saved_in_status_bar(self) -> None:
        self.app.profile_toggles["remove_generated_code"].invoke()
        self.assertEqual(self.app.status_bar.right.cget("text"),
                         "profile saved · applies to exports and transcript view")
        self.app.profile_toggles["exclude_single_exchange"].invoke()
        self.assertEqual(self.app.status_bar.right.cget("text"), "profile saved")

    def test_filter_rules_change_included_counts(self) -> None:
        # Default: single-exchange dropped, short project kept -> long + proj included.
        self.assertEqual(stats(self.database)["included"], 2)
        self.app.profile_toggles["exclude_single_exchange"].invoke()  # allow singles
        self.app.min_turns.set(0)
        self.app._save_min_turns()
        self.assertEqual(stats(self.database)["included"], 3)
        self.app.profile_toggles["project_only"].invoke()  # projects only
        self.assertEqual(stats(self.database)["included"], 1)
        self.app.profile_toggles["project_only"].invoke()
        self.app.profile_toggles["keep_short_projects"].invoke()  # drop short project grace
        self.app.profile_toggles["exclude_single_exchange"].invoke()
        self.app.min_turns.set(2)
        self.app._save_min_turns()
        self.assertEqual(stats(self.database)["included"], 1)


if __name__ == "__main__":
    unittest.main()
