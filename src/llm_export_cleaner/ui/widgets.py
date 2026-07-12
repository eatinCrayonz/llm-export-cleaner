"""Reusable terminal-style widget primitives built on the theme tokens."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Iterable

from llm_export_cleaner.ui.theme import COLORS, GAP, SIZE_SMALL, font


class Panel(tk.Frame):
    """Bordered region with a floating title that interrupts the border line."""

    def __init__(self, parent: tk.Misc, *, title: str, number: int | None = None) -> None:
        super().__init__(parent, background=COLORS["bg"])
        self._prefix = f"{number} · " if number is not None else ""
        self.border = tk.Frame(
            self, background=COLORS["bg"], highlightthickness=1,
            highlightbackground=COLORS["line"], highlightcolor=COLORS["line"],
        )
        self.border.pack(fill="both", expand=True, pady=(7, 0))
        self.body = tk.Frame(self.border, background=COLORS["bg"])
        self.body.pack(fill="both", expand=True, padx=12, pady=(10, 8))
        self.title_label = tk.Label(
            self, background=COLORS["bg"], foreground=COLORS["dim"],
            font=font(SIZE_SMALL), text=self._prefix + title, padx=6,
        )
        self.title_label.place(x=10, y=0)
        self.title_label.lift()

    def set_title(self, title: str) -> None:
        self.title_label.configure(text=self._prefix + title)

    def set_focus(self, focused: bool) -> None:
        color = COLORS["cyan"] if focused else COLORS["line"]
        self.border.configure(highlightbackground=color, highlightcolor=color)
        self.title_label.configure(foreground=COLORS["cyan"] if focused else COLORS["dim"])


class ToggleRow(tk.Frame):
    """A `[x] label` checkbox row in the TUI idiom."""

    def __init__(self, parent: tk.Misc, *, text: str, variable: tk.BooleanVar,
                 command: Any = None) -> None:
        super().__init__(parent, background=COLORS["bg"])
        self._text = text
        self._variable = variable
        self._command = command
        self.label = tk.Label(
            self, background=COLORS["bg"], font=font(), anchor="w",
            takefocus=1, highlightthickness=1,
            highlightbackground=COLORS["bg"], highlightcolor=COLORS["cyan"],
        )
        self.label.pack(fill="x")
        self.label.bind("<Button-1>", lambda _e: self.invoke())
        self.label.bind("<space>", lambda _e: self.invoke())
        self.label.bind("<Return>", lambda _e: self.invoke())
        self._trace = variable.trace_add("write", lambda *_a: self._render())
        self.bind("<Destroy>", self._untrace, add=True)
        self._render()

    def _untrace(self, _event: Any = None) -> None:
        try:
            self._variable.trace_remove("write", self._trace)
        except Exception:
            pass

    def _render(self) -> None:
        on = self._variable.get()
        self.label.configure(
            text=f"[{'x' if on else ' '}] {self._text}",
            foreground=COLORS["txt"] if on else COLORS["dim"],
        )

    def invoke(self) -> None:
        self._variable.set(not self._variable.get())
        if self._command:
            self._command()


class KeyValueGrid(tk.Frame):
    """Aligned key/value rows: dim keys, bright (or accented) values."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, background=COLORS["bg"])
        self.values: dict[str, tk.Label] = {}
        self._keys: dict[str, tk.Label] = {}
        self.columnconfigure(1, weight=1)

    def set(self, key: str, value: str, *, accent: bool = False) -> None:
        if key not in self.values:
            row = len(self.values)
            self._keys[key] = tk.Label(
                self, text=key, background=COLORS["bg"], foreground=COLORS["dim"],
                font=font(), anchor="w",
            )
            self._keys[key].grid(row=row, column=0, sticky="w", padx=(0, 16))
            self.values[key] = tk.Label(
                self, background=COLORS["bg"], font=font(), anchor="w",
            )
            self.values[key].grid(row=row, column=1, sticky="w")
        self.values[key].configure(
            text=value, foreground=COLORS["cyan"] if accent else COLORS["txt"],
        )

    def value(self, key: str) -> str:
        return self.values[key].cget("text")


class StatusBar(tk.Frame):
    """Bottom strip: cyan key letters with dim labels, status text on the right."""

    def __init__(self, parent: tk.Misc, *, keys: Iterable[tuple[str, str]]) -> None:
        super().__init__(
            parent, background=COLORS["bg_raise"], highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        self.key_labels: list[tk.Label] = []
        inner = tk.Frame(self, background=COLORS["bg_raise"])
        inner.pack(fill="x", padx=10, pady=4)
        for index, (key, label) in enumerate(keys):
            if index:
                tk.Label(inner, text="│", background=COLORS["bg_raise"],
                         foreground=COLORS["faint"], font=font(SIZE_SMALL)).pack(side="left", padx=GAP)
            key_label = tk.Label(inner, text=key, background=COLORS["bg_raise"],
                                 foreground=COLORS["cyan"], font=font(SIZE_SMALL, bold=True))
            key_label.pack(side="left")
            tk.Label(inner, text=label, background=COLORS["bg_raise"],
                     foreground=COLORS["dim"], font=font(SIZE_SMALL)).pack(side="left", padx=(3, 0))
            self.key_labels.append(key_label)
        self.right = tk.Label(inner, text="", background=COLORS["bg_raise"],
                              foreground=COLORS["faint"], font=font(SIZE_SMALL))
        self.right.pack(side="right")

    def set_right(self, text: str) -> None:
        self.right.configure(text=text)
