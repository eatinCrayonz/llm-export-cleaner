"""Terminal-style main window for LLM Export Cleaner."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Callable

from llm_export_cleaner.chatgpt_projects import apply_catalog
from llm_export_cleaner.claude_projects import apply_page
from llm_export_cleaner.exporter import export_cleaned
from llm_export_cleaner.filters import DEFAULT_PROFILE
from llm_export_cleaner.library import (
    default_database_path, get_conversation, import_export, import_history,
    list_conversations, list_profiles, save_profile, search, stats,
)
from llm_export_cleaner.ui import presenters
from llm_export_cleaner.ui.theme import COLORS, SIZE_SMALL, apply_theme, font
from llm_export_cleaner.ui.widgets import KeyValueGrid, Panel, StatusBar, ToggleRow


RULE_LABELS = {
    "exclude_single_exchange": "drop single-exchange",
    "keep_short_projects": "keep short projects",
    "project_only": "projects only",
    "remove_generated_code": "strip generated code",
    "include_attachment_counts": "attachment counts",
}
TEXT_WIDGETS = ("Entry", "TEntry", "TCombobox", "TSpinbox", "Spinbox", "Text")


class CleanerApp:
    def __init__(self, root: tk.Tk, database_path: Path | None = None) -> None:
        self.root = root
        self.database_path = database_path or default_database_path()
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.rows: dict[str, dict[str, Any]] = {}
        self.sort_column: str | None = None
        self.sort_descending = False
        self.profile_name = tk.StringVar(value="Default")
        apply_theme(root)
        root.title("llm-export-cleaner")
        root.geometry("1200x760")
        root.minsize(980, 620)
        self._build()
        self._refresh_profiles()
        self._refresh_stats()
        self._browse()
        root.after(100, self._poll)

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        page = tk.Frame(self.root, background=COLORS["bg"])
        page.pack(fill="both", expand=True, padx=14, pady=(10, 0))

        top = tk.Frame(page, background=COLORS["bg"])
        top.pack(fill="x")
        self.library_panel = Panel(top, title="library", number=1)
        self.library_panel.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self.library_grid = KeyValueGrid(self.library_panel.body)
        self.library_grid.pack(anchor="w")
        self.library_grid.set("conversations", "—")
        self.library_grid.set("messages", "—")
        self.library_grid.set("kept / filtered", "—")
        self.library_grid.set("database", str(self.database_path), accent=True)

        self.imports_panel = Panel(top, title="imports", number=2)
        self.imports_panel.pack(side="left", fill="both", expand=True)
        self.imports_grid = KeyValueGrid(self.imports_panel.body)
        self.imports_grid.pack(anchor="w")
        self.imports_grid.set("result", "no imports this session")
        actions = tk.Frame(self.imports_panel.body, background=COLORS["bg"])
        actions.pack(anchor="w", pady=(8, 0))
        self.import_provider = ttk.Combobox(actions, values=("chatgpt", "claude", "grok"), state="readonly", width=9)
        self.import_provider.grid(row=0, column=0, sticky="w")
        self.import_provider.set("chatgpt")
        self.import_button = ttk.Button(actions, text="import file…", command=self._choose_import)
        self.import_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(actions, text="history", command=self._show_history).grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Button(actions, text="claude pages…", command=self._claude_page).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(actions, text="chatgpt projects…", command=self._chatgpt_projects).grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(6, 0))

        self.searchline = searchline = tk.Frame(page, background=COLORS["bg"], highlightthickness=1,
                                                highlightbackground=COLORS["line"])
        searchline.pack(fill="x", pady=(12, 0))
        inner = tk.Frame(searchline, background=COLORS["bg"])
        inner.pack(fill="x", padx=12, pady=7)
        tk.Label(inner, text="/", background=COLORS["bg"], foreground=COLORS["cyan"],
                 font=font(bold=True)).pack(side="left", padx=(0, 8))
        self.query = tk.StringVar()
        self.search_entry = tk.Entry(
            inner, textvariable=self.query, background=COLORS["bg"], foreground=COLORS["txt"],
            insertbackground=COLORS["cyan"], borderwidth=0, highlightthickness=0, font=font(),
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", lambda _e: self._search())
        self.search_entry.bind("<Escape>", lambda _e: self._escape_search())
        self.provider = ttk.Combobox(inner, values=("All providers", "chatgpt", "claude", "grok"),
                                     state="readonly", width=12)
        self.provider.set("All providers")
        self.provider.pack(side="left", padx=(10, 0))
        self.project = ttk.Combobox(inner, values=("All conversations", "In a Project", "Not in a Project"),
                                    state="readonly", width=16)
        self.project.set("All conversations")
        self.project.pack(side="left", padx=(8, 0))
        self.include_filtered = tk.BooleanVar(value=False)
        ToggleRow(inner, text="filtered", variable=self.include_filtered,
                  command=self._browse).pack(side="left", padx=(10, 0))
        ttk.Button(inner, text="search", command=self._search).pack(side="left", padx=(10, 0))
        ttk.Button(inner, text="browse", command=self._browse).pack(side="left", padx=(6, 0))

        main = tk.Frame(page, background=COLORS["bg"])
        main.pack(fill="both", expand=True, pady=(12, 12))
        self.profile_panel = Panel(main, title="profile", number=4)
        self.profile_panel.pack(side="right", fill="y")
        self.conversations_panel = Panel(main, title="conversations", number=3)
        self.conversations_panel.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self.conversations_panel.set_focus(True)
        self.tree = ttk.Treeview(self.conversations_panel.body, columns=presenters.COLUMNS, show="headings")
        for column in presenters.COLUMNS:
            self.tree.heading(column, text=presenters.COLUMN_LABELS[column],
                              command=lambda selected=column: self._sort_by(selected))
            self.tree.column(column, width=presenters.COLUMN_WIDTHS[column], minwidth=60)
        self.tree.tag_configure("excluded", foreground=COLORS["faint"])
        scroll = ttk.Scrollbar(self.conversations_panel.body, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._open_selected)
        self.tree.bind("<Control-a>", self._select_all_visible)
        self.tree.bind("<Command-a>", self._select_all_visible)

        body = self.profile_panel.body
        self.profile_combo = ttk.Combobox(body, textvariable=self.profile_name, state="readonly", width=20)
        self.profile_combo.pack(anchor="w")
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _e: self._profile_changed())
        tk.Label(body, text="— rules", background=COLORS["bg"], foreground=COLORS["faint"],
                 font=font(SIZE_SMALL)).pack(anchor="w", pady=(10, 2))
        self.profile_vars: dict[str, tk.BooleanVar] = {}
        self.profile_toggles: dict[str, ToggleRow] = {}
        for key, label in RULE_LABELS.items():
            variable = tk.BooleanVar(self.root, value=bool(DEFAULT_PROFILE[key]))
            toggle = ToggleRow(body, text=label, variable=variable,
                               command=lambda selected=key: self._toggle_rule(selected))
            toggle.pack(fill="x")
            self.profile_vars[key] = variable
            self.profile_toggles[key] = toggle
        turns = tk.Frame(body, background=COLORS["bg"])
        turns.pack(fill="x", pady=(6, 0))
        tk.Label(turns, text="min user turns", background=COLORS["bg"], foreground=COLORS["dim"],
                 font=font()).pack(side="left")
        self.min_turns = tk.IntVar(value=int(DEFAULT_PROFILE["minimum_user_turns"]))
        spin = ttk.Spinbox(turns, from_=0, to=1000, textvariable=self.min_turns, width=5,
                           command=self._save_min_turns)
        spin.pack(side="left", padx=(8, 0))
        spin.bind("<Return>", lambda _e: self._save_min_turns())
        spin.bind("<FocusOut>", lambda _e: self._save_min_turns())
        tk.Label(body, text="— export", background=COLORS["bg"], foreground=COLORS["faint"],
                 font=font(SIZE_SMALL)).pack(anchor="w", pady=(12, 2))
        ttk.Button(body, text="export corpus…", command=self._export).pack(fill="x")
        ttk.Button(body, text="export selected…", command=self._export_selected).pack(fill="x", pady=(6, 0))
        ttk.Button(body, text="export latest changes…", command=lambda: self._export(delta=True)).pack(fill="x", pady=(6, 0))
        ttk.Button(body, text="rename / edit profile…", command=self._edit_profile).pack(fill="x", pady=(14, 0))

        self.hotkeys: dict[str, Callable[[], Any]] = {
            "i": self._choose_import, "e": self._export, "/": self._focus_search,
            "p": self._edit_profile, "x": self._toggle_filtered, "h": self._show_history,
        }
        self.status_bar = StatusBar(self.root, keys=(
            ("i", "import"), ("e", "export"), ("/", "search"),
            ("p", "profile"), ("x", "filtered"), ("h", "history"),
        ))
        self.status_bar.pack(fill="x", side="bottom")
        self.root.bind("<Key>", self._hotkey)
        self.search_entry.bind("<FocusIn>", lambda _e: self._set_region_focus("search"), add=True)
        self.tree.bind("<FocusIn>", lambda _e: self._set_region_focus("conversations"), add=True)
        self._set_region_focus("conversations")

    # ------------------------------------------------------------ helpers
    def _optional_provider(self) -> str | None:
        return presenters.provider_filter(self.provider.get())

    def _project_filter(self) -> bool | None:
        return presenters.project_filter(self.project.get())

    def _current_profile(self) -> dict[str, Any]:
        profiles = {p["name"]: p for p in list_profiles(self.database_path)}
        return {**DEFAULT_PROFILE, **profiles.get(self.profile_name.get(), {})}

    def _hotkey(self, event: tk.Event) -> None:
        widget = self.root.focus_get()
        if widget is not None and widget.winfo_class() in TEXT_WIDGETS:
            return
        action = self.hotkeys.get(event.char.lower() if event.char else "")
        if action:
            action()

    def _set_region_focus(self, region: str) -> None:
        search_focused = region == "search"
        color = COLORS["cyan"] if search_focused else COLORS["line"]
        self.searchline.configure(highlightbackground=color, highlightcolor=color)
        self.conversations_panel.set_focus(not search_focused)

    def _focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def _toggle_filtered(self) -> None:
        self.include_filtered.set(not self.include_filtered.get())
        self._browse()

    def _escape_search(self) -> None:
        self.tree.focus_set()
        self._browse()

    # ------------------------------------------------------------ actions
    def _choose_import(self) -> None:
        path = filedialog.askopenfilename(title="Choose provider export",
                                          filetypes=(("JSON", "*.json"), ("All files", "*.*")))
        if not path:
            return
        self.import_button.configure(state="disabled")
        self.imports_grid.set("result", f"importing {Path(path).name}…")
        self._background("import", lambda: import_export(
            provider=self.import_provider.get(), input_path=Path(path), database_path=self.database_path,
            progress=lambda current, total: self.events.put(("import-progress", (current, total))),
        ))

    def _search(self) -> None:
        if not self.query.get().strip():
            self._browse()
            return
        self._background("rows", lambda: search(
            database_path=self.database_path, query=self.query.get(), profile_name=self.profile_name.get(),
            include_filtered=self.include_filtered.get(), provider=self._optional_provider(),
            in_project=self._project_filter(),
        ))

    def _browse(self) -> None:
        self._background("rows", lambda: list_conversations(
            database_path=self.database_path, profile_name=self.profile_name.get(),
            include_filtered=self.include_filtered.get(), provider=self._optional_provider(),
            in_project=self._project_filter(),
        ))

    def _sort_by(self, column: str) -> None:
        self.sort_column, self.sort_descending = presenters.toggle_sort(
            self.sort_column, self.sort_descending, column)
        values = [
            (presenters.sort_key(column, self.tree.set(iid, column)), iid)
            for iid in self.tree.get_children("")
        ]
        values.sort(key=lambda item: item[0], reverse=self.sort_descending)
        for position, (_key, iid) in enumerate(values):
            self.tree.move(iid, "", position)
        for name, label in presenters.heading_labels(self.sort_column, descending=self.sort_descending).items():
            self.tree.heading(name, text=label)

    def _show_rows(self, rows: list[dict[str, Any]]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for index, row in enumerate(rows):
            iid = f"r{index}"
            tags = () if row.get("included", 1) else ("excluded",)
            self.tree.insert("", "end", iid=iid, values=presenters.format_row(row), tags=tags)
            self.rows[iid] = row

    def _open_selected(self, _event: Any = None) -> None:
        selected = self.tree.selection()
        if not selected or not (self.rows.get(selected[0]) or {}).get("conversation_id"):
            return
        row = self.rows[selected[0]]
        remove_code = bool(self._current_profile().get("remove_generated_code"))
        conversation = get_conversation(self.database_path, row["provider"], row["conversation_id"],
                                        without_generated_code=remove_code)
        window = tk.Toplevel(self.root)
        window.title(conversation.get("title") or "Untitled")
        window.geometry("900x700")
        window.configure(background=COLORS["bg"])
        text = scrolledtext.ScrolledText(
            window, wrap="word", padx=14, pady=14, background=COLORS["bg"],
            foreground=COLORS["txt"], insertbackground=COLORS["cyan"], font=font(),
            borderwidth=0, highlightthickness=0,
        )
        text.pack(fill="both", expand=True)
        for message in conversation["messages"]:
            text.insert("end", presenters.transcript_block(message))
        text.configure(state="disabled")

    def _select_all_visible(self, _event: Any = None) -> str:
        rows = self.tree.get_children("")
        if rows:
            self.tree.selection_set(rows)
        return "break"

    # ------------------------------------------------------------ profile
    def _toggle_rule(self, key: str) -> None:
        profile = self._current_profile()
        profile[key] = self.profile_vars[key].get()
        save_profile(self.database_path, profile)
        self._refresh_stats()
        self._browse()

    def _save_min_turns(self) -> None:
        try:
            value = int(self.min_turns.get())
        except (tk.TclError, ValueError):
            return
        profile = self._current_profile()
        if int(profile.get("minimum_user_turns") or 0) == value:
            return
        profile["minimum_user_turns"] = value
        save_profile(self.database_path, profile)
        self._refresh_stats()
        self._browse()

    def _load_profile_controls(self) -> None:
        profile = self._current_profile()
        for key, variable in self.profile_vars.items():
            variable.set(bool(profile.get(key)))
        self.min_turns.set(int(profile.get("minimum_user_turns") or 0))

    def _edit_profile(self) -> None:
        current = self._current_profile()
        window = tk.Toplevel(self.root)
        window.title("Cleaning profile")
        window.geometry("460x220")
        window.configure(background=COLORS["bg"])
        frame = tk.Frame(window, background=COLORS["bg"])
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(frame, text="profile name", background=COLORS["bg"], foreground=COLORS["dim"],
                 font=font()).grid(row=0, column=0, sticky="w")
        name = tk.StringVar(value=current["name"])
        ttk.Entry(frame, textvariable=name, width=28).grid(row=0, column=1, sticky="w", padx=(10, 0))
        tk.Label(frame, text="Saving under a new name creates a new profile.\nRules and turns are edited live in panel 4.",
                 background=COLORS["bg"], foreground=COLORS["faint"], font=font(SIZE_SMALL),
                 justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=12)

        def save() -> None:
            profile = {**current, "name": name.get()}
            save_profile(self.database_path, profile)
            self.profile_name.set(profile["name"].strip() or current["name"])
            window.destroy()
            self._refresh_profiles()
            self._refresh_stats()
            self._browse()

        ttk.Button(frame, text="save profile", command=save).grid(row=2, column=0, pady=10, sticky="w")
        ttk.Button(frame, text="cancel", command=window.destroy).grid(row=2, column=1, pady=10, sticky="e")

    # ------------------------------------------------------------ export
    def _export_dialog(self, title: str) -> str | None:
        return filedialog.asksaveasfilename(title=title, defaultextension=".txt", filetypes=(
            ("Plain text transcript", "*.txt"), ("Markdown transcript", "*.md"),
            ("JSON Lines", "*.jsonl"), ("JSON", "*.json"),
        ))

    def _export(self, delta: bool = False) -> None:
        output = self._export_dialog("Save cleaned corpus")
        if not output:
            return
        profile = self._current_profile()
        history = import_history(self.database_path, 1)
        import_id = int(history[0]["import_id"]) if delta and history else None
        self.status_bar.set_right("exporting…")
        self._background("export", lambda: export_cleaned(
            database_path=self.database_path, output_path=Path(output), profile_name=self.profile_name.get(),
            included_only=True, import_id=import_id,
            remove_code=bool(profile.get("remove_generated_code")),
            include_attachment_counts=bool(profile.get("include_attachment_counts")),
        ))

    def _export_selected(self) -> None:
        keys = presenters.selected_keys(self.tree.get_children(""), self.rows, set(self.tree.selection()))
        if not keys:
            messagebox.showinfo("Export selected", "Select one or more conversations first.")
            return
        output = self._export_dialog("Save selected conversations")
        if not output:
            return
        profile = self._current_profile()
        self.status_bar.set_right(f"exporting {len(keys):,} selected…")
        self._background("export", lambda: export_cleaned(
            database_path=self.database_path, output_path=Path(output), profile_name=self.profile_name.get(),
            included_only=False, selected_keys=keys,
            remove_code=bool(profile.get("remove_generated_code")),
            include_attachment_counts=bool(profile.get("include_attachment_counts")),
        ))

    # ------------------------------------------------------------ paste dialogs
    def _paste_dialog(self, *, title: str, caption: str, kind: str,
                      apply_call: Callable[[str], Any]) -> None:
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("760x600")
        window.configure(background=COLORS["bg"])
        frame = tk.Frame(window, background=COLORS["bg"])
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(frame, text=caption, wraplength=700, background=COLORS["bg"],
                 foreground=COLORS["dim"], font=font(), justify="left").pack(anchor="w", pady=(0, 10))
        text = scrolledtext.ScrolledText(frame, wrap="none", background=COLORS["bg_raise"],
                                         foreground=COLORS["txt"], insertbackground=COLORS["cyan"],
                                         font=font(), borderwidth=0, highlightthickness=1,
                                         highlightbackground=COLORS["line"])
        text.pack(fill="both", expand=True)
        buttons = tk.Frame(frame, background=COLORS["bg"])
        buttons.pack(fill="x", pady=(10, 0))

        def paste() -> None:
            try:
                value = self.root.clipboard_get()
            except tk.TclError:
                value = ""
            text.delete("1.0", "end")
            text.insert("1.0", value)

        def apply() -> None:
            value = text.get("1.0", "end").strip()
            if not value:
                return
            window.destroy()
            self._background(kind, lambda: apply_call(value))

        ttk.Button(buttons, text="paste from clipboard", command=paste).pack(side="left")
        ttk.Button(buttons, text="import", command=apply).pack(side="left", padx=8)
        ttk.Button(buttons, text="close", command=window.destroy).pack(side="right")

    def _claude_page(self) -> None:
        self._paste_dialog(
            title="Import Claude conversation page",
            caption="Paste a Claude conversation-list or Project-list JSON response. "
                    "Conversation pages assign membership; Project pages assign names.",
            kind="claude",
            apply_call=lambda value: apply_page(database_path=self.database_path, page_text=value),
        )

    def _chatgpt_projects(self) -> None:
        self._paste_dialog(
            title="Import ChatGPT Project catalog",
            caption="Paste the JSON response from /backend-api/gizmos/snorlax/sidebar. "
                    "Only Project IDs and display names are retained.",
            kind="chatgpt-projects",
            apply_call=lambda value: apply_catalog(database_path=self.database_path, catalog_text=value),
        )

    def _show_history(self) -> None:
        self._background("history", lambda: import_history(self.database_path, 100))

    # ------------------------------------------------------------ refresh + events
    def _profile_changed(self) -> None:
        self._load_profile_controls()
        self._refresh_stats()
        self._browse()

    def _refresh_profiles(self) -> None:
        names = [p["name"] for p in list_profiles(self.database_path)]
        self.profile_combo.configure(values=names)
        if self.profile_name.get() not in names and names:
            self.profile_name.set(names[0])
        self._load_profile_controls()

    def _refresh_stats(self) -> None:
        self._background("stats", lambda: stats(self.database_path, self.profile_name.get()))

    def _background(self, kind: str, operation: Callable[[], Any]) -> None:
        def worker() -> None:
            try:
                self.events.put((kind, operation()))
            except Exception as error:
                self.events.put(("error", error))
        threading.Thread(target=worker, daemon=True).start()

    def _handle_event(self, kind: str, payload: Any) -> None:
        if kind == "error":
            self.import_button.configure(state="normal")
            messagebox.showerror("LLM Export Cleaner", str(payload))
        elif kind == "import-progress":
            self.imports_grid.set("result", presenters.progress_text(*payload))
        elif kind == "import":
            self.import_button.configure(state="normal")
            self.imports_grid.set("result", presenters.import_status_text(payload))
            self._refresh_stats()
            self._browse()
        elif kind == "rows":
            self._show_rows(payload)
        elif kind == "stats":
            self.library_grid.set("conversations", f"{payload['conversations']:,}")
            self.library_grid.set("messages", f"{payload['messages']:,} in {payload['imports']:,} imports")
            self.library_grid.set("kept / filtered", f"{payload['included']:,} / {payload['filtered']:,}")
            self.conversations_panel.set_title(
                f"conversations ({payload['included']:,}/{payload['conversations']:,})")
        elif kind == "export":
            self.status_bar.set_right(presenters.export_status_text(payload))
        elif kind == "claude":
            self.imports_grid.set("result", presenters.claude_status_text(payload))
            self._refresh_stats()
            self._browse()
        elif kind == "chatgpt-projects":
            self.imports_grid.set("result", presenters.chatgpt_projects_status_text(payload))
            self._browse()
        elif kind == "history":
            self._show_rows(presenters.history_rows(payload))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


def main() -> None:
    root = tk.Tk()
    CleanerApp(root)
    root.mainloop()
