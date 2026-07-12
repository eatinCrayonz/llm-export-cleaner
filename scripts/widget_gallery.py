"""Visual gallery for the terminal-theme primitives (development aid).

Run:  python scripts/widget_gallery.py          # interactive window
      python scripts/widget_gallery.py --smoke  # build, verify, exit
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_export_cleaner.ui.theme import COLORS, apply_theme, font  # noqa: E402
from llm_export_cleaner.ui.widgets import KeyValueGrid, Panel, StatusBar, ToggleRow  # noqa: E402


def build(root: tk.Tk) -> None:
    root.title("Theme gallery")
    root.geometry("860x640")
    apply_theme(root)
    page = tk.Frame(root, background=COLORS["bg"])
    page.pack(fill="both", expand=True, padx=16, pady=(14, 0))

    top = tk.Frame(page, background=COLORS["bg"])
    top.pack(fill="x")
    library = Panel(top, title="library", number=1)
    library.pack(side="left", fill="both", expand=True, padx=(0, 12))
    grid = KeyValueGrid(library.body)
    grid.pack(anchor="w")
    grid.set("conversations", "1,247")
    grid.set("kept / filtered", "1,189 / 58")
    grid.set("database", "cleaner.sqlite3 · wal · fts5", accent=True)

    profile = Panel(top, title="profile", number=4)
    profile.pack(side="left", fill="both", expand=True)
    for text, value in (("drop single-exchange", True), ("min 2 user turns", True), ("strip generated code", False)):
        ToggleRow(profile.body, text=text, variable=tk.BooleanVar(root, value=value)).pack(fill="x")

    focused = Panel(page, title="conversations (1,189/1,247)", number=3)
    focused.pack(fill="both", expand=True, pady=(12, 0))
    focused.set_focus(True)
    tree = ttk.Treeview(focused.body, columns=("title", "provider", "msgs"), show="headings", height=6)
    for column, width in (("title", 420), ("provider", 110), ("msgs", 70)):
        tree.heading(column, text=column)
        tree.column(column, width=width)
    rows = (
        ("Evolution — selection pressure deep dive", "claude", 4),
        ("Kerf calculations for 3mm plywood", "chatgpt", 18),
        ("what's a good pizza dough ratio · single_exchange", "chatgpt", 2),
    )
    for index, values in enumerate(rows):
        tree.insert("", "end", iid=str(index), values=values, tags=("x",) if index == 2 else ())
    tree.tag_configure("x", foreground=COLORS["faint"])
    tree.selection_set("0")
    tree.pack(fill="both", expand=True)

    controls = tk.Frame(page, background=COLORS["bg"])
    controls.pack(fill="x", pady=12)
    ttk.Button(controls, text="Choose export...").pack(side="left")
    combo = ttk.Combobox(controls, values=("All providers", "chatgpt", "claude", "grok"), state="readonly", width=14)
    combo.set("All providers")
    combo.pack(side="left", padx=8)
    entry = ttk.Entry(controls, width=30)
    entry.insert(0, "selection pressure")
    entry.pack(side="left", padx=8)
    tk.Label(controls, text="· single_exchange", background=COLORS["bg"],
             foreground=COLORS["amber"], font=font()).pack(side="left", padx=8)

    bar = StatusBar(root, keys=(("i", "import"), ("e", "export"), ("/", "search"), ("p", "profile"), ("q", "quit")))
    bar.pack(fill="x", side="bottom")
    bar.set_right("library clean · 0 pending")


def main() -> None:
    root = tk.Tk()
    build(root)
    if "--smoke" in sys.argv:
        root.update()
        print("gallery ok:", root.winfo_children() and "widgets built")
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
