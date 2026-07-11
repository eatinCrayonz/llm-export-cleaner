"""Portable cleaned JSON and JSONL exports with audit manifests."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from llm_export_cleaner.library import connect, utc_now
from llm_export_cleaner.text_cleaning import remove_generated_code


def export_cleaned(
    *, database_path: Path, output_path: Path, profile_name: str = "Default",
    included_only: bool = True, import_id: int | None = None,
    include_attachment_counts: bool = False,
    remove_code: bool | None = None,
    selected_keys: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    output = output_path.expanduser().resolve()
    if output.suffix.lower() not in {".json", ".jsonl", ".md"}:
        raise ValueError("Output must end in .json, .jsonl, or .md")
    output.parent.mkdir(parents=True, exist_ok=True)
    db = connect(database_path)
    clauses = ["p.name=?"]
    params: list[Any] = [profile_name]
    if included_only:
        clauses.append("r.included=1")
    if import_id is not None:
        clauses.append("c.last_changed_import_id>=?")
        params.append(import_id)
    try:
        profile_row = db.execute("SELECT profile_json FROM cleaning_profiles WHERE name=?", (profile_name,)).fetchone()
        if profile_row is None:
            raise ValueError(f"Unknown cleaning profile: {profile_name}")
        profile = json.loads(profile_row["profile_json"])
        remove_code = bool(profile.get("remove_generated_code")) if remove_code is None else remove_code
        rows = db.execute(
            f"""SELECT c.*,r.included,r.reasons_json,
                (SELECT name FROM projects x WHERE x.provider=c.provider AND x.project_id=c.project_id) project_name
                FROM conversations c
                JOIN cleaning_profiles p ON p.name=?
                JOIN filter_results r ON r.profile_id=p.profile_id AND r.provider=c.provider AND r.conversation_id=c.conversation_id
                WHERE {' AND '.join(clauses[1:]) if len(clauses)>1 else '1=1'}
                ORDER BY c.provider,COALESCE(c.created_epoch,0),c.conversation_id""",
            params,
        ).fetchall()
        if selected_keys is not None:
            by_key = {(row["provider"], row["conversation_id"]): row for row in rows}
            rows = [by_key[key] for key in selected_keys if key in by_key]
        records: list[dict[str, Any]] = []
        message_total = 0
        for row in rows:
            message_clause = " AND is_active_path=1"
            messages = db.execute(
                f"SELECT * FROM messages WHERE provider=? AND conversation_id=?{message_clause} ORDER BY COALESCE(created_epoch,0),rowid",
                (row["provider"], row["conversation_id"]),
            ).fetchall()
            clean_messages = []
            for message in messages:
                item = {
                    "message_id": message["message_id"],
                    "parent_message_id": message["parent_message_id"],
                    "role": message["role"],
                    "text": remove_generated_code(message["text"]) if remove_code and message["role"] == "assistant" else message["text"],
                    "created_at": message["created_at"],
                    "is_active_path": bool(message["is_active_path"]),
                    "is_alternative": bool(message["is_alternative"]),
                }
                if include_attachment_counts:
                    item["attachment_count"] = int(message["attachment_count"])
                clean_messages.append(item)
            record = {
                "provider": row["provider"], "conversation_id": row["conversation_id"],
                "title": row["title"], "created_at": row["created_at"],
                "updated_at": row["updated_at"], "project_id": row["project_id"],
                "active_leaf_message_id": row["active_leaf_message_id"],
                "_project_name": row["project_name"],
                "messages": clean_messages,
            }
            records.append(record)
            message_total += len(clean_messages)
        if output.suffix.lower() == ".md":
            with output.open("w", encoding="utf-8", newline="\n") as handle:
                for index, record in enumerate(records, 1):
                    handle.write(f"--- CONVERSATION {index} ---\n")
                    handle.write(f"Title: {record['title'] or 'Untitled'}\n")
                    handle.write(f"Provider: {record['provider']}\n")
                    handle.write(f"Date: {record['created_at'] or ''}\n")
                    if record.get("_project_name"):
                        handle.write(f"Project: {record['_project_name']}\n")
                    handle.write("\n")
                    for message in record["messages"]:
                        label = "USER" if message["role"] == "user" else "ASSISTANT"
                        timestamp = f" | {message['created_at']}" if message.get("created_at") else ""
                        handle.write(f"[{label}{timestamp}]\n{message['text']}\n\n")
                    handle.write("--- END CONVERSATION ---\n\n")
        elif output.suffix.lower() == ".jsonl":
            with output.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    portable = {key: value for key, value in record.items() if not key.startswith("_")}
                    handle.write(json.dumps(portable, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            portable = [{key: value for key, value in record.items() if not key.startswith("_")} for record in records]
            output.write_text(json.dumps(portable, ensure_ascii=False, indent=2), encoding="utf-8")
        reason_rows = db.execute(
            """SELECT r.reasons_json FROM filter_results r
               JOIN cleaning_profiles p ON p.profile_id=r.profile_id
               WHERE p.name=? AND r.included=0""",
            (profile_name,),
        ).fetchall()
        excluded_reasons = Counter()
        for reason_row in reason_rows:
            excluded_reasons.update(json.loads(reason_row["reasons_json"]))
        import_stats = db.execute("SELECT COUNT(*) count,COALESCE(SUM(source_bytes),0) bytes FROM imports").fetchone()
        total = int(db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
    finally:
        db.close()
    manifest = {
        "generated_at": utc_now(), "profile": profile_name,
        "mode": "selected" if selected_keys is not None else "delta" if import_id is not None else "complete",
        "since_import_id": import_id, "included_only": included_only,
        "source_imports": int(import_stats["count"]), "source_bytes_seen": int(import_stats["bytes"]),
        "conversations_available": total, "conversations_exported": len(records),
        "messages_exported": message_total,
        "generated_code_removed": bool(remove_code),
        "format": output.suffix.lower().lstrip("."),
        "excluded_by_reason": dict(sorted(excluded_reasons.items())),
        "output": str(output), "output_bytes": output.stat().st_size,
    }
    manifest_path = output.with_name(output.stem + "-manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest | {"manifest": str(manifest_path)}
