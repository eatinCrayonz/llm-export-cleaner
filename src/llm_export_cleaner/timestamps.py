"""Normalize provider timestamp variants without inventing missing values."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def timestamp_epoch(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        if "$date" in value:
            return timestamp_epoch(value["$date"])
        if "$numberLong" in value:
            return float(value["$numberLong"]) / 1000
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 1000 if abs(number) > 100_000_000_000 else number
    text = str(value).strip()
    if not text:
        return None
    try:
        return timestamp_epoch(float(text))
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def timestamp_utc(value: Any) -> str | None:
    epoch = timestamp_epoch(value)
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def date_boundary(value: str | None, *, end: bool = False) -> float | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 10:
        parsed = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        return parsed.timestamp() + (86_400 if end else 0)
    epoch = timestamp_epoch(text)
    if epoch is None:
        raise ValueError(f"Invalid date: {value}")
    return epoch

