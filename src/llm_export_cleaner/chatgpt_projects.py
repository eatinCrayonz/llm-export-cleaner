"""Manual ChatGPT Project sidebar-catalog enrichment."""

from __future__ import annotations

import json
from typing import Any


def parse_catalog(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"ChatGPT Project catalog is not valid JSON: {error.msg}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("ChatGPT Project catalog must contain an items list")
    names: dict[str, str] = {}
    for index, item in enumerate(payload["items"], 1):
        if not isinstance(item, dict) or not isinstance(item.get("gizmo"), dict):
            raise ValueError(f"ChatGPT Project item {index} has no gizmo object")
        gizmo = item["gizmo"]
        if isinstance(gizmo.get("gizmo"), dict):
            gizmo = gizmo["gizmo"]
        project_id = str(gizmo.get("id") or "").strip()
        display = gizmo.get("display") if isinstance(gizmo.get("display"), dict) else {}
        name = str(display.get("name") or "").strip()
        if not project_id.startswith("g-p-") or not name:
            raise ValueError(f"ChatGPT Project item {index} has no usable id and display name")
        names[project_id] = name
    cursor = payload.get("cursor")
    return {"project_names": names, "records": len(payload["items"]), "cursor": cursor, "has_more": cursor is not None}


def apply_catalog(*, database_path: Any, catalog_text: str) -> dict[str, Any]:
    from llm_export_cleaner.library import connect

    parsed = parse_catalog(catalog_text)
    db = connect(database_path)
    try:
        stored_ids = {
            row["project_id"] for row in db.execute(
                "SELECT DISTINCT project_id FROM conversations WHERE provider='chatgpt' AND project_id IS NOT NULL"
            )
        }
        with db:
            for project_id, name in parsed["project_names"].items():
                db.execute(
                    "INSERT INTO projects(provider,project_id,name) VALUES('chatgpt',?,?) "
                    "ON CONFLICT(provider,project_id) DO UPDATE SET name=excluded.name",
                    (project_id, name),
                )
        catalog_ids = set(parsed["project_names"])
        named_stored = {
            row["project_id"] for row in db.execute(
                "SELECT project_id FROM projects WHERE provider='chatgpt'"
            )
        }
    finally:
        db.close()
    return {
        **parsed,
        "matched": len(stored_ids & catalog_ids),
        "catalog_only": len(catalog_ids - stored_ids),
        "still_unnamed": len(stored_ids - named_stored),
    }
