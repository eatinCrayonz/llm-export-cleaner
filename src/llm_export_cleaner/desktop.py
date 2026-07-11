"""Focused native desktop interface for LLM Export Cleaner."""

from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Callable

if getattr(sys, "frozen", False):
    runtime = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ.setdefault("TCL_LIBRARY", str(runtime / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(runtime / "_tk_data"))

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from llm_export_cleaner.claude_projects import apply_page
from llm_export_cleaner.exporter import export_cleaned
from llm_export_cleaner.filters import DEFAULT_PROFILE
from llm_export_cleaner.library import (
    default_database_path, get_conversation, import_export, import_history,
    list_conversations, list_profiles, save_profile, search, stats,
)


class CleanerApp:
    def __init__(self, root: tk.Tk, database_path: Path | None = None) -> None:
        self.root = root
        self.database_path = database_path or default_database_path()
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.rows: dict[str, dict[str, Any]] = {}
        self.profile_name = tk.StringVar(value="Default")
        root.title("LLM Export Cleaner")
        root.geometry("1180x720")
        root.minsize(900, 560)
        self._build()
        self._refresh_profiles()
        self._refresh_stats()
        root.after(100, self._poll)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        heading = ttk.Frame(outer)
        heading.pack(fill="x")
        ttk.Label(heading, text="LLM Export Cleaner", font=("Segoe UI", 18, "bold")).pack(side="left")
        self.stats_label = ttk.Label(heading, text="")
        self.stats_label.pack(side="right")
        ttk.Label(outer, text=f"Private cleaned library: {self.database_path}", foreground="#555").pack(fill="x", pady=(2, 12))

        add = ttk.LabelFrame(outer, text="Add export", padding=10)
        add.pack(fill="x", pady=(0, 10))
        self.import_provider = ttk.Combobox(add, values=("chatgpt", "claude", "grok"), state="readonly", width=12)
        self.import_provider.set("chatgpt")
        self.import_provider.pack(side="left")
        self.import_button = ttk.Button(add, text="Choose export...", command=self._choose_import)
        self.import_button.pack(side="left", padx=(8, 0))
        ttk.Button(add, text="Claude Project page...", command=self._claude_page).pack(side="left", padx=(8, 0))
        ttk.Button(add, text="Import history", command=self._show_history).pack(side="left", padx=(8, 0))
        self.import_status = ttk.Label(add, text="")
        self.import_status.pack(side="left", padx=12)

        find = ttk.LabelFrame(outer, text="Search cleaned conversations", padding=10)
        find.pack(fill="x", pady=(0, 10))
        self.query = tk.StringVar()
        entry = ttk.Entry(find, textvariable=self.query, width=50)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda _e: self._search())
        self.provider = ttk.Combobox(find, values=("All providers", "chatgpt", "claude", "grok"), state="readonly", width=14)
        self.provider.set("All providers")
        self.provider.grid(row=0, column=1, padx=5)
        self.project = ttk.Combobox(find, values=("All conversations", "In a Project", "Not in a Project"), state="readonly", width=18)
        self.project.set("All conversations")
        self.project.grid(row=0, column=2, padx=5)
        self.include_filtered = tk.BooleanVar(value=False)
        ttk.Checkbutton(find, text="Include filtered-out", variable=self.include_filtered).grid(row=0, column=3, padx=5)
        ttk.Button(find, text="Search", command=self._search).grid(row=0, column=4, padx=5)
        ttk.Button(find, text="Browse", command=self._browse).grid(row=0, column=5)
        find.columnconfigure(0, weight=1)

        profile = ttk.LabelFrame(outer, text="Cleaning profile", padding=10)
        profile.pack(fill="x", pady=(0, 10))
        self.profile_combo = ttk.Combobox(profile, textvariable=self.profile_name, state="readonly", width=24)
        self.profile_combo.pack(side="left")
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _e: self._profile_changed())
        ttk.Button(profile, text="Edit profile...", command=self._edit_profile).pack(side="left", padx=(8, 0))
        ttk.Button(profile, text="Export cleaned corpus...", command=self._export).pack(side="left", padx=(8, 0))
        ttk.Button(profile, text="Export latest changes...", command=lambda: self._export(delta=True)).pack(side="left", padx=(8, 0))
        self.profile_status = ttk.Label(profile, text="")
        self.profile_status.pack(side="left", padx=12)

        table = ttk.Frame(outer)
        table.pack(fill="both", expand=True)
        columns = ("date", "provider", "turns", "project", "title", "match")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        labels = {"date": "Date (UTC)", "provider": "Provider", "turns": "User turns", "project": "Project", "title": "Conversation", "match": "Match / filter reason"}
        widths = {"date": 165, "provider": 80, "turns": 75, "project": 90, "title": 300, "match": 430}
        for column in columns:
            self.tree.heading(column, text=labels[column])
            self.tree.column(column, width=widths[column], minwidth=60)
        scroll = ttk.Scrollbar(table, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._open_selected)
        ttk.Label(outer, text="Double-click a conversation to open its cleaned transcript.", foreground="#555").pack(fill="x", pady=(6, 0))

    def _optional_provider(self) -> str | None:
        return None if self.provider.get() == "All providers" else self.provider.get()

    def _project_filter(self) -> bool | None:
        return True if self.project.get() == "In a Project" else False if self.project.get() == "Not in a Project" else None

    def _choose_import(self) -> None:
        path = filedialog.askopenfilename(title="Choose provider export", filetypes=(("JSON", "*.json"), ("All files", "*.*")))
        if not path:
            return
        self.import_button.configure(state="disabled")
        self.import_status.configure(text=f"Importing {Path(path).name}...")
        self._background("import", lambda: import_export(
            provider=self.import_provider.get(), input_path=Path(path), database_path=self.database_path,
            progress=lambda current, total: self.events.put(("import-progress", (current, total))),
        ))

    def _search(self) -> None:
        if not self.query.get().strip():
            messagebox.showinfo("Search", "Enter a word or phrase.")
            return
        self._background("rows", lambda: search(
            database_path=self.database_path, query=self.query.get(), profile_name=self.profile_name.get(),
            include_filtered=self.include_filtered.get(), provider=self._optional_provider(), in_project=self._project_filter(),
        ))

    def _browse(self) -> None:
        self._background("rows", lambda: list_conversations(
            database_path=self.database_path, profile_name=self.profile_name.get(), include_filtered=self.include_filtered.get(),
            provider=self._optional_provider(), in_project=self._project_filter(),
        ))

    def _show_rows(self, rows: list[dict[str, Any]]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for index, row in enumerate(rows):
            iid = f"r{index}"
            match = row.get("snippet") or (", ".join(row.get("reasons") or []) if not row.get("included", 1) else "Included")
            self.tree.insert("", "end", iid=iid, values=(
                row.get("updated_at") or row.get("created_at") or "", row["provider"], row.get("active_user_turn_count", 0),
                "Yes" if row.get("project_id") else "No", row.get("title") or "Untitled", match,
            ))
            self.rows[iid] = row

    def _open_selected(self, _event: Any = None) -> None:
        selected = self.tree.selection()
        if not selected or "conversation_id" not in self.rows[selected[0]]:
            return
        row = self.rows[selected[0]]
        conversation = get_conversation(self.database_path, row["provider"], row["conversation_id"])
        window = tk.Toplevel(self.root)
        window.title(conversation.get("title") or "Untitled")
        window.geometry("900x700")
        text = scrolledtext.ScrolledText(window, wrap="word", padx=14, pady=14)
        text.pack(fill="both", expand=True)
        for message in conversation["messages"]:
            text.insert("end", f"{'YOU' if message['role']=='user' else 'ASSISTANT'} | {message.get('created_at') or ''}\n{message['text']}\n\n")
        text.configure(state="disabled")

    def _edit_profile(self) -> None:
        profiles = {p["name"]: p for p in list_profiles(self.database_path)}
        current = {**DEFAULT_PROFILE, **profiles.get(self.profile_name.get(), {})}
        window = tk.Toplevel(self.root)
        window.title("Cleaning profile")
        window.geometry("520x480")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        name = tk.StringVar(value=current["name"])
        min_turns = tk.IntVar(value=int(current["minimum_user_turns"]))
        single = tk.BooleanVar(value=bool(current["exclude_single_exchange"]))
        project_only = tk.BooleanVar(value=bool(current["project_only"]))
        keep_projects = tk.BooleanVar(value=bool(current["keep_short_projects"]))
        attachments = tk.BooleanVar(value=bool(current["include_attachment_counts"]))
        ttk.Label(frame, text="Profile name").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=name, width=30).grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text="Minimum user turns").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Spinbox(frame, from_=0, to=1000, textvariable=min_turns, width=8).grid(row=1, column=1, sticky="w")
        options = [("Exclude single-question/single-answer conversations", single), ("Project conversations only", project_only), ("Keep short Project conversations", keep_projects), ("Include attachment counts in exports", attachments)]
        for row_index, (label, variable) in enumerate(options, 2):
            ttk.Checkbutton(frame, text=label, variable=variable).grid(row=row_index, column=0, columnspan=2, sticky="w", pady=5)
        def save() -> None:
            profile = {**current, "name": name.get(), "minimum_user_turns": min_turns.get(), "exclude_single_exchange": single.get(), "project_only": project_only.get(), "keep_short_projects": keep_projects.get(), "include_attachment_counts": attachments.get()}
            save_profile(self.database_path, profile)
            self.profile_name.set(profile["name"])
            window.destroy()
            self._refresh_profiles()
            self._refresh_stats()
            self._browse()
        ttk.Button(frame, text="Save profile", command=save).grid(row=9, column=0, pady=18, sticky="w")
        ttk.Button(frame, text="Cancel", command=window.destroy).grid(row=9, column=1, pady=18, sticky="e")

    def _export(self, delta: bool = False) -> None:
        output = filedialog.asksaveasfilename(title="Save cleaned corpus", defaultextension=".jsonl", filetypes=(("JSON Lines", "*.jsonl"), ("JSON", "*.json")))
        if not output:
            return
        profiles = {p["name"]: p for p in list_profiles(self.database_path)}
        profile = profiles[self.profile_name.get()]
        history = import_history(self.database_path, 1)
        import_id = int(history[0]["import_id"]) if delta and history else None
        self.profile_status.configure(text="Exporting...")
        self._background("export", lambda: export_cleaned(
            database_path=self.database_path, output_path=Path(output), profile_name=self.profile_name.get(),
            included_only=True, import_id=import_id,
            include_attachment_counts=bool(profile.get("include_attachment_counts")),
        ))

    def _claude_page(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Import Claude conversation page")
        window.geometry("760x600")
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Paste the complete Claude website JSON response. Both observed response formats are supported.", wraplength=700).pack(anchor="w", pady=(0, 10))
        text = scrolledtext.ScrolledText(frame, wrap="none")
        text.pack(fill="both", expand=True)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        def paste() -> None:
            try: value = self.root.clipboard_get()
            except tk.TclError: value = ""
            text.delete("1.0", "end"); text.insert("1.0", value)
        def apply() -> None:
            value = text.get("1.0", "end").strip()
            if not value: return
            window.destroy(); self._background("claude", lambda: apply_page(database_path=self.database_path, page_text=value))
        ttk.Button(buttons, text="Paste from clipboard", command=paste).pack(side="left")
        ttk.Button(buttons, text="Import page", command=apply).pack(side="left", padx=8)
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")

    def _show_history(self) -> None:
        self._background("history", lambda: import_history(self.database_path, 100))

    def _profile_changed(self) -> None:
        self._refresh_stats(); self._browse()

    def _refresh_profiles(self) -> None:
        names = [p["name"] for p in list_profiles(self.database_path)]
        self.profile_combo.configure(values=names)
        if self.profile_name.get() not in names and names: self.profile_name.set(names[0])

    def _refresh_stats(self) -> None:
        self._background("stats", lambda: stats(self.database_path, self.profile_name.get()))

    def _background(self, kind: str, operation: Callable[[], Any]) -> None:
        def worker() -> None:
            try: self.events.put((kind, operation()))
            except Exception as error: self.events.put(("error", error))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "error":
                    self.import_button.configure(state="normal")
                    messagebox.showerror("LLM Export Cleaner", str(payload))
                elif kind == "import-progress":
                    self.import_status.configure(text=f"Scanning {payload[0]:,}/{payload[1]:,}")
                elif kind == "import":
                    self.import_button.configure(state="normal")
                    self.import_status.configure(text="Already imported" if payload["duplicate_export"] else f"{payload['new_conversations']} new; {payload['changed_conversations']} changed; {payload['unchanged_conversations']} unchanged")
                    self._refresh_stats(); self._browse()
                elif kind == "rows": self._show_rows(payload)
                elif kind == "stats":
                    self.stats_label.configure(text=f"{payload['conversations']:,} conversations | {payload['messages']:,} messages | {payload['imports']:,} imports")
                    self.profile_status.configure(text=f"{payload['included']:,} included | {payload['filtered']:,} filtered out")
                elif kind == "export":
                    self.profile_status.configure(text=f"Exported {payload['conversations_exported']:,} conversations ({payload['output_bytes']:,} bytes)")
                elif kind == "claude":
                    more = f"; more at offset {payload['next_offset']}" if payload["has_more"] else ""
                    self.import_status.configure(text=f"Claude Projects: {payload['updated']} updated, {payload['unknown']} unknown{more}")
                    self._refresh_stats(); self._browse()
                elif kind == "history":
                    rows = [{"provider": r["provider"], "title": r["source_file"], "updated_at": r["imported_at_utc"], "active_user_turn_count": "import", "project_id": None, "included": 1, "conversation_id": "", "snippet": f"{r['new_conversations']} new; {r['changed_conversations']} changed; {r['unchanged_conversations']} unchanged"} for r in payload]
                    self._show_rows(rows)
        except queue.Empty: pass
        self.root.after(100, self._poll)


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names(): style.theme_use("vista")
    CleanerApp(root)
    root.mainloop()


if __name__ == "__main__": main()
