"""Provider exports to the minimal canonical conversation schema."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from llm_export_cleaner.timestamps import timestamp_utc
from llm_export_cleaner.text_cleaning import clean_text


@dataclass
class Audit:
    conversations_seen: int = 0
    conversations_written: int = 0
    messages_seen: int = 0
    messages_written: int = 0
    exclusion_reasons: Counter[str] = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversations_seen": self.conversations_seen,
            "conversations_written": self.conversations_written,
            "messages_seen": self.messages_seen,
            "messages_written": self.messages_written,
            "exclusion_reasons": dict(sorted(self.exclusion_reasons.items())),
            "warnings": self.warnings,
        }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return clean_text(value)
    return None


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return _text(content)
    if not isinstance(content, dict):
        return None
    parts = content.get("parts")
    if isinstance(parts, list):
        values: list[str] = []
        for part in parts:
            if isinstance(part, str) and part.strip():
                values.append(part.strip())
            elif isinstance(part, dict):
                candidate = _text(part.get("text"))
                if candidate:
                    values.append(candidate)
        return clean_text("\n\n".join(values)) if values else None
    return _text(content.get("text"))


def _message(
    *, provider: str, conversation_id: str, message_id: str, parent_id: str | None,
    role: str, text: str, created_at: Any, active: bool, alternative: bool,
    attachment_count: int = 0,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "parent_message_id": parent_id,
        "role": role,
        "text": text,
        "created_at": timestamp_utc(created_at),
        "is_active_path": active,
        "is_alternative": alternative,
        "attachment_count": attachment_count,
    }


def _conversation(
    *, provider: str, conversation_id: str, title: str | None, created_at: Any,
    updated_at: Any, project_id: str | None, active_leaf_id: str | None,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "conversation_id": conversation_id,
        "title": title,
        "created_at": timestamp_utc(created_at),
        "updated_at": timestamp_utc(updated_at),
        "project_id": project_id,
        "active_leaf_message_id": active_leaf_id,
        "messages": messages,
    }


def normalize_chatgpt(data: Any, audit: Audit) -> Iterable[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError("ChatGPT export must be a top-level array")
    for ci, raw in enumerate(data):
        audit.conversations_seen += 1
        mapping = raw.get("mapping") or {}
        if not isinstance(mapping, dict):
            audit.exclusion_reasons["invalid_mapping"] += 1
            continue
        conversation_id = str(raw.get("conversation_id") or raw.get("id") or f"chatgpt-{ci}")
        current = raw.get("current_node")
        active_nodes: set[str] = set()
        visited: set[str] = set()
        cursor = str(current) if current else None
        while cursor and cursor in mapping and cursor not in visited:
            visited.add(cursor)
            active_nodes.add(cursor)
            parent = mapping[cursor].get("parent")
            cursor = str(parent) if parent else None
        retained: dict[str, str] = {}
        candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for ni, (node_id, node) in enumerate(mapping.items()):
            message = node.get("message")
            if not isinstance(message, dict):
                continue
            audit.messages_seen += 1
            if current and str(node_id) not in active_nodes:
                audit.exclusion_reasons["alternative_branch"] += 1
                continue
            role = str((message.get("author") or {}).get("role") or "").lower()
            if role not in {"user", "assistant"}:
                audit.exclusion_reasons["non_conversation_role"] += 1
                continue
            text = _content_text(message.get("content"))
            if not text:
                audit.exclusion_reasons["no_readable_text"] += 1
                continue
            message_id = str(message.get("id") or node_id or f"{conversation_id}-{ni}")
            retained[str(node_id)] = message_id
            candidates.append((str(node_id), node, {"id": message_id, "role": role, "text": text, "raw": message}))
        messages: list[dict[str, Any]] = []
        for node_id, node, item in candidates:
            parent_node = str(node.get("parent")) if node.get("parent") else None
            seen: set[str] = set()
            while parent_node and parent_node not in retained and parent_node in mapping and parent_node not in seen:
                seen.add(parent_node)
                parent = mapping[parent_node].get("parent")
                parent_node = str(parent) if parent else None
            messages.append(_message(
                provider="chatgpt", conversation_id=conversation_id,
                message_id=item["id"], parent_id=retained.get(parent_node),
                role=item["role"], text=item["text"],
                created_at=item["raw"].get("create_time"), active=True,
                alternative=False,
                attachment_count=sum(isinstance(p, dict) for p in ((item["raw"].get("content") or {}).get("parts") or [])),
            ))
        if not messages:
            audit.exclusion_reasons["conversation_without_readable_messages"] += 1
            continue
        gizmo_id = _text(raw.get("gizmo_id"))
        project_id = gizmo_id if raw.get("gizmo_type") == "snorlax" and gizmo_id and gizmo_id.startswith("g-p-") else None
        active_leaf = retained.get(str(current)) if current else messages[-1]["message_id"]
        audit.conversations_written += 1
        audit.messages_written += len(messages)
        yield _conversation(
            provider="chatgpt", conversation_id=conversation_id,
            title=_text(raw.get("title")), created_at=raw.get("create_time"),
            updated_at=raw.get("update_time"), project_id=project_id,
            active_leaf_id=active_leaf, messages=messages,
        )


def normalize_claude(data: Any, audit: Audit) -> Iterable[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError("Claude export must be a top-level array")
    for ci, raw in enumerate(data):
        audit.conversations_seen += 1
        conversation_id = str(raw.get("uuid") or f"claude-{ci}")
        messages: list[dict[str, Any]] = []
        previous: str | None = None
        for mi, item in enumerate(raw.get("chat_messages") or []):
            audit.messages_seen += 1
            role = {"human": "user", "user": "user", "assistant": "assistant"}.get(str(item.get("sender") or "").lower())
            if not role:
                audit.exclusion_reasons["non_conversation_role"] += 1
                continue
            text = _text(item.get("text"))
            if not text:
                audit.exclusion_reasons["no_readable_text"] += 1
                continue
            message_id = str(item.get("uuid") or f"{conversation_id}-{mi}")
            messages.append(_message(
                provider="claude", conversation_id=conversation_id,
                message_id=message_id,
                parent_id=_text(item.get("parent_message_uuid")) or previous,
                role=role, text=text, created_at=item.get("created_at"),
                active=True, alternative=False,
                attachment_count=len(item.get("attachments") or []) + len(item.get("files") or []),
            ))
            previous = message_id
        if not messages:
            audit.exclusion_reasons["conversation_without_readable_messages"] += 1
            continue
        audit.conversations_written += 1
        audit.messages_written += len(messages)
        yield _conversation(
            provider="claude", conversation_id=conversation_id,
            title=_text(raw.get("name")), created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"), project_id=_text(raw.get("project_uuid")),
            active_leaf_id=messages[-1]["message_id"], messages=messages,
        )


def normalize_grok(data: Any, audit: Audit) -> Iterable[dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("conversations"), list):
        raise ValueError("Grok export must contain a conversations list")
    for ci, wrapper in enumerate(data["conversations"]):
        audit.conversations_seen += 1
        raw = wrapper.get("conversation") or {}
        conversation_id = str(raw.get("_id") or raw.get("id") or raw.get("conversation_id") or f"grok-{ci}")
        messages: list[dict[str, Any]] = []
        previous: str | None = None
        for mi, response_wrapper in enumerate(wrapper.get("responses") or []):
            response = response_wrapper.get("response") or {}
            audit.messages_seen += 1
            sender = str(response.get("sender") or "").lower()
            role = "user" if sender in {"human", "user"} else "assistant" if sender == "assistant" or sender.startswith("grok") else None
            if not role:
                audit.exclusion_reasons["non_conversation_role"] += 1
                continue
            text = _text(response.get("message"))
            if not text:
                audit.exclusion_reasons["no_readable_text"] += 1
                continue
            message_id = str(response.get("_id") or f"{conversation_id}-{mi}")
            messages.append(_message(
                provider="grok", conversation_id=conversation_id,
                message_id=message_id, parent_id=_text(response.get("parent_response_id")) or previous,
                role=role, text=text, created_at=response.get("create_time"),
                active=True, alternative=False,
                attachment_count=len(response.get("file_attachments") or []),
            ))
            previous = message_id
        if not messages:
            audit.exclusion_reasons["conversation_without_readable_messages"] += 1
            continue
        audit.conversations_written += 1
        audit.messages_written += len(messages)
        yield _conversation(
            provider="grok", conversation_id=conversation_id,
            title=_text(raw.get("title")), created_at=raw.get("create_time"),
            updated_at=raw.get("modify_time"), project_id=None,
            active_leaf_id=messages[-1]["message_id"], messages=messages,
        )


NORMALIZERS = {"chatgpt": normalize_chatgpt, "claude": normalize_claude, "grok": normalize_grok}
