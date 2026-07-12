from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_export_cleaner.ui import theme  # noqa: E402


class TokenTests(unittest.TestCase):
    def test_all_colors_are_hex(self) -> None:
        for name, value in theme.COLORS.items():
            self.assertRegex(value, re.compile(r"^#[0-9a-f]{6}$"), f"bad color {name}={value}")

    def test_core_roles_exist(self) -> None:
        for role in ("bg", "bg_raise", "line", "txt", "dim", "faint", "cyan", "amber", "ok", "sel_bg"):
            self.assertIn(role, theme.COLORS)


class FontPickerTests(unittest.TestCase):
    def test_prefers_cascadia_then_consolas(self) -> None:
        self.assertEqual(theme.pick_font_family(["Arial", "Consolas", "Cascadia Mono"]), "Cascadia Mono")
        self.assertEqual(theme.pick_font_family(["Arial", "Consolas"]), "Consolas")

    def test_mac_fallbacks(self) -> None:
        self.assertEqual(theme.pick_font_family(["Helvetica", "Menlo"]), "Menlo")
        self.assertEqual(theme.pick_font_family(["Helvetica", "SF Mono", "Menlo"]), "SF Mono")

    def test_case_insensitive_match_and_final_fallback(self) -> None:
        self.assertEqual(theme.pick_font_family(["CASCADIA MONO"]), "CASCADIA MONO")
        self.assertEqual(theme.pick_font_family(["Comic Sans MS"]), "Courier")


class TkWidgetTests(unittest.TestCase):
    def setUp(self) -> None:
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk unavailable: {error}")
        self.root.withdraw()
        theme.apply_theme(self.root)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_apply_theme_uses_clam_and_page_background(self) -> None:
        from tkinter import ttk
        self.assertEqual(ttk.Style(self.root).theme_use(), "clam")
        self.assertEqual(self.root.cget("background"), theme.COLORS["bg"])

    def test_panel_title_focus_and_body(self) -> None:
        from llm_export_cleaner.ui.widgets import Panel
        panel = Panel(self.root, title="conversations", number=3)
        self.assertEqual(panel.title_label.cget("text"), "3 · conversations")
        self.assertEqual(str(panel.border.cget("highlightbackground")), theme.COLORS["line"])
        panel.set_focus(True)
        self.assertEqual(str(panel.border.cget("highlightbackground")), theme.COLORS["cyan"])
        panel.set_focus(False)
        self.assertEqual(str(panel.border.cget("highlightbackground")), theme.COLORS["line"])
        panel.set_title("conversations (2/5)")
        self.assertEqual(panel.title_label.cget("text"), "3 · conversations (2/5)")
        self.assertTrue(panel.body.winfo_exists())

    def test_toggle_row_flips_text_and_variable(self) -> None:
        import tkinter as tk
        from llm_export_cleaner.ui.widgets import ToggleRow
        variable = tk.BooleanVar(value=True)
        toggle = ToggleRow(self.root, text="drop single-exchange", variable=variable)
        self.assertEqual(toggle.label.cget("text"), "[x] drop single-exchange")
        toggle.invoke()
        self.assertFalse(variable.get())
        self.assertEqual(toggle.label.cget("text"), "[ ] drop single-exchange")
        variable.set(True)
        self.assertEqual(toggle.label.cget("text"), "[x] drop single-exchange")

    def test_key_value_grid_updates_in_place(self) -> None:
        from llm_export_cleaner.ui.widgets import KeyValueGrid
        grid = KeyValueGrid(self.root)
        grid.set("conversations", "0")
        grid.set("conversations", "1,247")
        grid.set("database", "cleaner.sqlite3", accent=True)
        self.assertEqual(grid.value("conversations"), "1,247")
        self.assertEqual(str(grid.values["database"].cget("fg")), theme.COLORS["cyan"])
        self.assertEqual(len(grid.values), 2)

    def test_status_bar_keys_and_right_text(self) -> None:
        from llm_export_cleaner.ui.widgets import StatusBar
        bar = StatusBar(self.root, keys=(("i", "import"), ("e", "export")))
        bar.set_right("library clean · 0 pending")
        self.assertEqual(bar.right.cget("text"), "library clean · 0 pending")
        self.assertEqual(len(bar.key_labels), 2)


if __name__ == "__main__":
    unittest.main()
