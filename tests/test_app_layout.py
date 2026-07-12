from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class AppLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk unavailable: {error}")
        self.root.withdraw()
        self._temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.database = Path(self._temporary.name) / "cleaner.sqlite3"

    def tearDown(self) -> None:
        self.root.destroy()
        self._temporary.cleanup()

    def _app(self):
        from llm_export_cleaner.ui.app import CleanerApp
        app = CleanerApp(self.root, database_path=self.database)
        self.root.update()
        return app

    def test_terminal_layout_regions_exist(self) -> None:
        app = self._app()
        self.assertEqual(app.library_panel.title_label.cget("text"), "1 · library")
        self.assertTrue(app.imports_panel.title_label.cget("text").startswith("2 ·"))
        self.assertTrue(app.conversations_panel.title_label.cget("text").startswith("3 ·"))
        self.assertTrue(app.profile_panel.title_label.cget("text").startswith("4 ·"))
        self.assertTrue(app.status_bar.winfo_exists())
        self.assertTrue(app.search_entry.winfo_exists())

    def test_excluded_rows_are_tagged(self) -> None:
        app = self._app()
        app._show_rows([
            {"provider": "claude", "conversation_id": "c1", "title": "Kept", "included": 1},
            {"provider": "grok", "conversation_id": "c2", "title": "Dropped", "included": 0,
             "reasons": ["single_exchange"]},
        ])
        self.assertEqual(app.tree.item("r0")["tags"], "")
        self.assertIn("excluded", app.tree.item("r1")["tags"])

    def test_stats_event_updates_library_grid_and_counts_title(self) -> None:
        app = self._app()
        app._handle_event("stats", {
            "conversations": 1247, "messages": 18932, "imports": 9,
            "included": 1189, "filtered": 58, "database": str(self.database),
        })
        self.assertEqual(app.library_grid.value("conversations"), "1,247")
        self.assertEqual(app.library_grid.value("kept / filtered"), "1,189 / 58")
        self.assertIn("(1,189/1,247)", app.conversations_panel.title_label.cget("text"))

    def test_profile_toggle_persists_to_database(self) -> None:
        from llm_export_cleaner.library import list_profiles
        app = self._app()
        toggle = app.profile_toggles["exclude_single_exchange"]
        self.assertTrue(toggle._variable.get())
        toggle.invoke()
        profiles = {p["name"]: p for p in list_profiles(self.database)}
        self.assertFalse(profiles["Default"]["exclude_single_exchange"])

    def test_export_event_lands_in_status_bar(self) -> None:
        app = self._app()
        app._handle_event("export", {"conversations_exported": 12, "output_bytes": 3400})
        self.assertEqual(app.status_bar.right.cget("text"), "Exported 12 conversations (3,400 bytes)")

    def test_provider_change_refreshes_and_project_dropdown_is_gone(self) -> None:
        app = self._app()
        self.assertFalse(hasattr(app, "project"))
        self.assertIn("<<ComboboxSelected>>", app.provider.bind())

    def test_excluded_toggle_is_labeled_clearly(self) -> None:
        app = self._app()
        self.assertEqual(app.filtered_toggle.label.cget("text"), "[ ] show excluded")

    def test_desktop_module_still_exposes_cleaner_app(self) -> None:
        from llm_export_cleaner import desktop
        from llm_export_cleaner.ui.app import CleanerApp
        self.assertIs(desktop.CleanerApp, CleanerApp)


if __name__ == "__main__":
    unittest.main()
