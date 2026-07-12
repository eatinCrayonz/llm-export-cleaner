from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_export_cleaner.ui import theme  # noqa: E402


class FocusAndKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk unavailable: {error}")
        self.root.withdraw()
        self._temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        from llm_export_cleaner.ui.app import CleanerApp
        self.app = CleanerApp(self.root, database_path=Path(self._temporary.name) / "cleaner.sqlite3")
        self.root.update()

    def tearDown(self) -> None:
        self.root.destroy()
        self._temporary.cleanup()

    def test_status_bar_advertises_only_working_hotkeys(self) -> None:
        advertised = {label.cget("text") for label in self.app.status_bar.key_labels}
        self.assertTrue(advertised.issubset(set(self.app.hotkeys)),
                        f"dead hints: {advertised - set(self.app.hotkeys)}")

    def test_region_focus_moves_cyan_border(self) -> None:
        self.app._set_region_focus("search")
        self.assertEqual(str(self.app.searchline.cget("highlightbackground")), theme.COLORS["cyan"])
        self.assertEqual(str(self.app.conversations_panel.border.cget("highlightbackground")),
                         theme.COLORS["line"])
        self.app._set_region_focus("conversations")
        self.assertEqual(str(self.app.searchline.cget("highlightbackground")), theme.COLORS["line"])
        self.assertEqual(str(self.app.conversations_panel.border.cget("highlightbackground")),
                         theme.COLORS["cyan"])


if __name__ == "__main__":
    unittest.main()
