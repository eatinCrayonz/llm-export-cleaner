"""Provider-neutral cleanup for readable conversation text."""

from __future__ import annotations

import json
import re
import unicodedata


_MARKER = re.compile("\ue200(?P<kind>[a-z_]+)\ue202(?P<payload>.*?)\ue201", re.DOTALL)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002300-\U000023FF]"
    "[\uFE0E\uFE0F\U0001F3FB-\U0001F3FF]*"
)
_TOOL_KEYS = {
    "search_query", "image_query", "open", "click", "find", "screenshot",
    "finance", "weather", "sports", "time", "response_length",
}


def _repair_mojibake(text: str) -> str:
    current = text
    for _ in range(2):
        if not any(marker in current for marker in ("â", "Ã", "î", "ð", "Â")):
            break
        try:
            raw = bytearray()
            for character in current:
                if ord(character) <= 255:
                    raw.append(ord(character))
                else:
                    try:
                        raw.extend(character.encode("cp1252"))
                    except UnicodeEncodeError:
                        raw.extend(character.encode("utf-8"))
            candidate = bytes(raw).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        current = candidate
    return current


def _replace_marker(match: re.Match[str]) -> str:
    kind, payload = match.group("kind"), match.group("payload")
    if kind == "entity":
        try:
            value = json.loads(payload)
            if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
                return value[1]
        except json.JSONDecodeError:
            pass
    return ""


def _is_tool_payload(text: str) -> bool:
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and bool(set(value) & _TOOL_KEYS) and set(value) <= _TOOL_KEYS


def clean_text(value: str) -> str | None:
    text = unicodedata.normalize("NFC", _repair_mojibake(value))
    if _is_tool_payload(text):
        return None
    text = _MARKER.sub(_replace_marker, text)
    text = _EMOJI.sub("", text).replace("\u200d", "").replace("\ufe0f", "")
    lines = [re.sub(r"[ \t]{2,}", " ", line).rstrip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None
