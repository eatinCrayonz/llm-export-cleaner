from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path(__file__).resolve().parents[1]


class IconAssetTests(unittest.TestCase):
    def test_ico_exists_with_ico_signature_and_sizes(self) -> None:
        data = (ROOT / "assets" / "icon.ico").read_bytes()
        self.assertEqual(data[:4], b"\x00\x00\x01\x00")
        self.assertGreaterEqual(int.from_bytes(data[4:6], "little"), 4)  # entry count

    def test_window_icon_png_exists_in_package(self) -> None:
        png = ROOT / "src" / "llm_export_cleaner" / "assets" / "icon-64.png"
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


class DarkTitleBarTests(unittest.TestCase):
    def test_apply_dark_title_bar_never_raises(self) -> None:
        import tkinter as tk
        from llm_export_cleaner.ui.theme import apply_dark_title_bar
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk unavailable: {error}")
        root.withdraw()
        try:
            apply_dark_title_bar(root)  # must be safe on any platform/session
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
