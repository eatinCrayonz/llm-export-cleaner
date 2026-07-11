from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class DesktopSmokeTests(unittest.TestCase):
    """Builds the real widget tree against a temporary library."""

    def setUp(self) -> None:
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as error:  # headless environment
            self.skipTest(f"Tk unavailable: {error}")
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()

    def test_app_builds_and_sorts(self) -> None:
        from llm_export_cleaner.desktop import CleanerApp

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            app = CleanerApp(self.root, database_path=Path(temporary) / "cleaner.sqlite3")
            self.root.update()
            app._show_rows([
                {"provider": "claude", "conversation_id": "c1", "title": "B title",
                 "active_user_turn_count": 5, "included": 1, "updated_at": "2025-02-01T00:00:00Z"},
                {"provider": "chatgpt", "conversation_id": "c2", "title": "A title",
                 "active_user_turn_count": 2, "included": 0, "reasons": ["single_exchange"]},
            ])
            self.assertEqual(len(app.tree.get_children("")), 2)
            self.assertEqual(app.tree.set("r1", "match"), "single_exchange")

            app._sort_by("turns")
            ascending = [app.tree.set(iid, "turns") for iid in app.tree.get_children("")]
            app._sort_by("turns")
            descending = [app.tree.set(iid, "turns") for iid in app.tree.get_children("")]
            self.assertEqual(ascending, ["2", "5"])
            self.assertEqual(descending, ["5", "2"])
            self.assertTrue(app.tree.heading("turns")["text"].endswith("▼"))
            self.root.update()


if __name__ == "__main__":
    unittest.main()
