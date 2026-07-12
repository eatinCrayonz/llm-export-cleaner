"""Saved, reversible conversation cleaning rules."""

from __future__ import annotations

from typing import Any


DEFAULT_PROFILE = {
    "name": "Default",
    "minimum_user_turns": 2,
    "project_only": False,
    "keep_short_projects": True,
    "provider": None,
    "after": None,
    "before": None,
    "include_attachment_counts": False,
    "remove_generated_code": False,
}


def evaluate_conversation(record: dict[str, Any], profile: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    user_turns = int(record.get("active_user_turn_count") or 0)
    project_id = record.get("project_id")
    short_project_exception = bool(profile.get("keep_short_projects") and project_id)
    if profile.get("project_only") and not project_id:
        reasons.append("not_in_project")
    if not short_project_exception:
        minimum = int(profile.get("minimum_user_turns") or 0)
        if user_turns < minimum:
            reasons.append("below_minimum_user_turns")
    provider = profile.get("provider")
    if provider and record.get("provider") != provider:
        reasons.append("provider_filtered")
    created = record.get("created_epoch")
    after = profile.get("after_epoch")
    before = profile.get("before_epoch")
    if after is not None and (created is None or float(created) < float(after)):
        reasons.append("before_date_range")
    if before is not None and (created is None or float(created) >= float(before)):
        reasons.append("after_date_range")
    return not reasons, reasons
