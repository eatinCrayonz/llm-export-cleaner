"""Pure display formatting for the desktop interface.

Everything here is tkinter-free so row text, sort behavior, and status
messages stay unit-testable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable


COLUMNS = ("date", "provider", "turns", "project", "title", "match")
COLUMN_LABELS = {
    "date": "Date (UTC)", "provider": "Provider", "turns": "User turns",
    "project": "Project", "title": "Conversation", "match": "Match / filter reason",
}
COLUMN_WIDTHS = {"date": 125, "provider": 70, "turns": 70, "project": 100, "title": 280, "match": 240}


def display_date(value: str) -> str:
    return value[:16].replace("T", " ") if len(value) >= 16 else value


def format_row(row: dict[str, Any]) -> tuple[Any, ...]:
    match = row.get("snippet") or (
        ", ".join(row.get("reasons") or []) if not row.get("included", 1) else "Included"
    )
    return (
        display_date(row.get("updated_at") or row.get("created_at") or ""),
        row["provider"],
        row.get("active_user_turn_count", 0),
        row.get("project_name") or "",
        row.get("title") or "Untitled",
        match,
    )


def sort_key(column: str, raw: str) -> Any:
    if column == "turns":
        try:
            return int(raw)
        except ValueError:
            return -1
    if column == "date":
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except (ValueError, OverflowError):
            return float("-inf")
    return raw.casefold()


def toggle_sort(current: str | None, descending: bool, clicked: str) -> tuple[str, bool]:
    return clicked, not descending if current == clicked else False


def heading_labels(sort_column: str | None, *, descending: bool) -> dict[str, str]:
    labels = {}
    for name, label in COLUMN_LABELS.items():
        suffix = (" ▼" if descending else " ▲") if name == sort_column else ""
        labels[name] = label + suffix
    return labels


def provider_filter(display: str) -> str | None:
    return None if display == "All providers" else display


def project_filter(display: str) -> bool | None:
    return True if display == "In a Project" else False if display == "Not in a Project" else None


def selected_keys(
    ordered_iids: Iterable[str], rows: dict[str, dict[str, Any]], selected: set[str],
) -> list[tuple[str, str]]:
    keys = []
    for iid in ordered_iids:
        row = rows.get(iid) or {}
        if iid in selected and row.get("provider") and row.get("conversation_id"):
            keys.append((row["provider"], row["conversation_id"]))
    return keys


def history_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "provider": record["provider"],
        "title": record["source_file"],
        "updated_at": record["imported_at_utc"],
        "active_user_turn_count": "import",
        "project_id": None,
        "included": 1,
        "conversation_id": "",
        "snippet": (
            f"{record['new_conversations']} new; {record['changed_conversations']} changed; "
            f"{record['unchanged_conversations']} unchanged"
        ),
    } for record in records]


def progress_text(current: int, total: int) -> str:
    return f"Scanning {current:,}/{total:,}"


def import_status_text(payload: dict[str, Any]) -> str:
    if payload["duplicate_export"]:
        return "Already imported"
    return (
        f"{payload['new_conversations']} new; {payload['changed_conversations']} changed; "
        f"{payload['unchanged_conversations']} unchanged"
    )


def stats_text(payload: dict[str, Any]) -> str:
    return f"{payload['conversations']:,} conversations | {payload['messages']:,} messages | {payload['imports']:,} imports"


def profile_status_text(payload: dict[str, Any]) -> str:
    return f"{payload['included']:,} included | {payload['filtered']:,} filtered out"


def export_status_text(payload: dict[str, Any]) -> str:
    return f"Exported {payload['conversations_exported']:,} conversations ({payload['output_bytes']:,} bytes)"


def claude_status_text(payload: dict[str, Any]) -> str:
    more = f"; more at offset {payload['next_offset']}" if payload["has_more"] else ""
    if payload["kind"] == "projects":
        return f"Claude Projects: {payload['named_projects']} names saved{more}"
    return f"Claude Projects: {payload['updated']} updated, {payload['unknown']} unknown{more}"


def chatgpt_projects_status_text(payload: dict[str, Any]) -> str:
    more = "; additional cursor page exists" if payload["has_more"] else ""
    return f"ChatGPT Projects: {payload['matched']} matched, {payload['still_unnamed']} still unnamed{more}"


def transcript_block(message: dict[str, Any]) -> str:
    label = "YOU" if message["role"] == "user" else "ASSISTANT"
    return f"{label} | {message.get('created_at') or ''}\n{message['text']}\n\n"
