"""Design tokens and ttk style setup for the terminal-style interface.

Every color and font the UI uses is defined here; widgets and views must
reference these tokens instead of literal values.
"""

from __future__ import annotations

import sys
from typing import Iterable


COLORS = {
    "bg": "#101216",        # page
    "bg_raise": "#151821",  # status bar, field fills
    "line": "#2a2f3a",      # panel borders
    "txt": "#c7ccd6",       # primary text
    "dim": "#6b7280",       # secondary text
    "faint": "#3d4451",     # tertiary text, table headers
    "cyan": "#56c8d8",      # accent: focus, keys, selection text
    "amber": "#d8a343",     # filter reasons only
    "ok": "#7bb86f",        # healthy status
    "sel_bg": "#1d3a41",    # selected row fill
}

_FONT_PREFERENCE = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "Monaco")

SIZE_BASE = 10
SIZE_SMALL = 9
PAD = 12
GAP = 10

_family: str | None = None


def pick_font_family(available: Iterable[str]) -> str:
    lookup = {name.casefold(): name for name in available}
    for candidate in _FONT_PREFERENCE:
        found = lookup.get(candidate.casefold())
        if found:
            return found
    return "Courier"


def font_family() -> str:
    if _family is None:
        raise RuntimeError("apply_theme has not run")
    return _family


def font(size: int = SIZE_BASE, *, bold: bool = False) -> tuple:
    return (font_family(), size, "bold") if bold else (font_family(), size)


def apply_dark_title_bar(window) -> None:
    """Ask DWM for the dark window frame (Windows 10 1809+; no-op elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, pre-20H1 value
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def apply_theme(root) -> None:
    global _family
    from tkinter import font as tkfont, ttk

    _family = pick_font_family(tkfont.families(root))
    c = COLORS
    root.configure(background=c["bg"])

    style = ttk.Style(root)
    style.theme_use("clam")
    base, small = font(), font(SIZE_SMALL)

    style.configure(".", background=c["bg"], foreground=c["txt"], font=base,
                    bordercolor=c["line"], lightcolor=c["bg"], darkcolor=c["bg"],
                    troughcolor=c["bg"], fieldbackground=c["bg_raise"],
                    insertcolor=c["cyan"], selectbackground=c["sel_bg"],
                    selectforeground=c["cyan"])
    style.configure("TFrame", background=c["bg"])
    style.configure("TLabel", background=c["bg"], foreground=c["txt"])
    style.configure("Dim.TLabel", foreground=c["dim"])
    style.configure("Faint.TLabel", foreground=c["faint"])
    style.configure("Accent.TLabel", foreground=c["cyan"])
    style.configure("Amber.TLabel", foreground=c["amber"])
    style.configure("Ok.TLabel", foreground=c["ok"])

    style.configure("TButton", background=c["bg"], foreground=c["dim"],
                    bordercolor=c["line"], focuscolor=c["cyan"],
                    padding=(10, 3), relief="flat", shiftrelief=0)
    style.map("TButton",
              foreground=[("active", c["txt"]), ("pressed", c["cyan"])],
              bordercolor=[("active", c["dim"]), ("focus", c["cyan"])],
              background=[("active", c["bg_raise"])])

    style.configure("TCheckbutton", background=c["bg"], foreground=c["txt"],
                    indicatorbackground=c["bg_raise"], indicatorforeground=c["cyan"],
                    focuscolor=c["cyan"])
    style.map("TCheckbutton", background=[("active", c["bg"])])

    style.configure("TEntry", fieldbackground=c["bg_raise"], foreground=c["txt"],
                    bordercolor=c["line"], insertcolor=c["cyan"], padding=4)
    style.map("TEntry", bordercolor=[("focus", c["cyan"])])
    style.configure("TSpinbox", fieldbackground=c["bg_raise"], foreground=c["txt"],
                    bordercolor=c["line"], arrowcolor=c["dim"], insertcolor=c["cyan"])

    style.configure("TCombobox", fieldbackground=c["bg_raise"], background=c["bg_raise"],
                    foreground=c["txt"], bordercolor=c["line"], arrowcolor=c["dim"],
                    padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", c["bg_raise"])],
              foreground=[("readonly", c["txt"])],
              bordercolor=[("focus", c["cyan"])])
    root.option_add("*TCombobox*Listbox.background", c["bg_raise"])
    root.option_add("*TCombobox*Listbox.foreground", c["txt"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["sel_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["cyan"])
    root.option_add("*TCombobox*Listbox.font", base)

    style.configure("Treeview", background=c["bg"], fieldbackground=c["bg"],
                    foreground=c["txt"], bordercolor=c["line"], font=base,
                    rowheight=int(SIZE_BASE * 2.4))
    style.map("Treeview",
              background=[("selected", c["sel_bg"])],
              foreground=[("selected", c["cyan"])])
    style.configure("Treeview.Heading", background=c["bg"], foreground=c["faint"],
                    font=small, relief="flat", padding=(6, 4))
    style.map("Treeview.Heading",
              background=[("active", c["bg_raise"])],
              foreground=[("active", c["dim"])])

    style.configure("Vertical.TScrollbar", background=c["bg_raise"],
                    troughcolor=c["bg"], bordercolor=c["bg"],
                    arrowcolor=c["dim"], relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", c["line"])])
