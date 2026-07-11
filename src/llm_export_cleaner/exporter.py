"""Portable cleaned JSON and JSONL exports with audit manifests."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from llm_export_cleaner.library import connect, utc_now


def export_cleaned(
    *, database_path: Path, output_path: Path, profile_name: str = "Default",
    included_only: bool = True, import_id: int | None = None,
    include_attachment_counts: bool = False,
) -> dict[str, Any]:
    output = output_path.expanduser().resolve()
    if output.suffix.lower() not in {".json", ".jsonl"}:
        raise ValueError("Output must end in .json or .jsonl")
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
        rows = db.execute(
            f"""SELECT c.*,r.included,r.reasons_json FROM conversations c
                JOIN cleaning_profiles p ON p.name=?
                JOIN filter_results r ON r.profile_id=p.profile_id AND r.provider=c.provider AND r.conversation_id=c.conversation_id
                WHERE {' AND '.join(clauses[1:]) if len(clauses)>1 else '1=1'}
                ORDER BY c.provider,COALESCE(c.created_epoch,0),c.conversation_id""",
            params,
        ).fetchall()
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
                    "role": message["role"], "text": message["text"],
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
                "messages": clean_messages,
            }
            records.append(record)
            message_total += len(clean_messages)
        if output.suffix.lower() == ".jsonl":
            with output.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
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
        "mode": "delta" if import_id is not None else "complete",
        "since_import_id": import_id, "included_only": included_only,
        "source_imports": int(import_stats["count"]), "source_bytes_seen": int(import_stats["bytes"]),
        "conversations_available": total, "conversations_exported": len(records),
        "messages_exported": message_total,
        "excluded_by_reason": dict(sorted(excluded_reasons.items())),
        "output": str(output), "output_bytes": output.stat().st_size,
    }
    manifest_path = output.with_name(output.stem + "-manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest | {"manifest": str(manifest_path)}
