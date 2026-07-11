"""Manual Claude website conversation-list enrichment."""

from __future__ import annotations

import json
from typing import Any


def parse_page(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Claude page is not valid JSON: {error.msg}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Claude page must contain a data list")
    records = payload["data"]
    pagination = payload.get("pagination")
    if pagination is None and isinstance(payload.get("has_more"), bool):
        pagination = {"offset": int(payload.get("offset") or 0), "limit": len(records), "total": None, "has_more": payload["has_more"]}
    if not isinstance(pagination, dict):
        raise ValueError("Claude page must contain pagination or has_more")
    assignments: dict[str, str | None] = {}
    projects: set[str] = set()
    names: dict[str, str] = {}
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict) or not record.get("uuid"):
            raise ValueError(f"Claude record {index} has no conversation UUID")
        conversation_id = str(record["uuid"])
        if conversation_id in assignments:
            raise ValueError(f"Duplicate conversation UUID: {conversation_id}")
        project = record.get("project") if isinstance(record.get("project"), dict) else {}
        raw_project = record.get("project_uuid") or project.get("uuid")
        project_id = str(raw_project) if raw_project else None
        assignments[conversation_id] = project_id
        if project_id:
            projects.add(project_id)
            if project.get("name"):
                names[project_id] = str(project["name"])
    offset = int(pagination.get("offset") or 0)
    return {
        "assignments": assignments, "project_names": names,
        "records": len(records), "projects": len(projects),
        "has_more": pagination.get("has_more") is True,
        "next_offset": offset + len(records),
    }


def apply_page(*, database_path: Any, page_text: str) -> dict[str, Any]:
    from llm_export_cleaner.library import connect, recompute_profiles

    parsed = parse_page(page_text)
    db = connect(database_path)
    matched = updated = unchanged = unknown = 0
    try:
        with db:
            for project_id, name in parsed["project_names"].items():
                db.execute(
                    "INSERT INTO projects(provider,project_id,name) VALUES('claude',?,?) "
                    "ON CONFLICT(provider,project_id) DO UPDATE SET name=excluded.name",
                    (project_id, name),
                )
            for conversation_id, project_id in parsed["assignments"].items():
                row = db.execute("SELECT project_id FROM conversations WHERE provider='claude' AND conversation_id=?", (conversation_id,)).fetchone()
                if row is None:
                    unknown += 1
                elif row["project_id"] == project_id:
                    matched += 1
                    unchanged += 1
                else:
                    matched += 1
                    updated += 1
                    db.execute("UPDATE conversations SET project_id=? WHERE provider='claude' AND conversation_id=?", (project_id, conversation_id))
            recompute_profiles(db, providers={"claude"})
    finally:
        db.close()
    return {**{k: parsed[k] for k in ("records", "projects", "has_more", "next_offset")}, "matched": matched, "updated": updated, "unchanged": unchanged, "unknown": unknown}
