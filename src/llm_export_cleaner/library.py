"""Incremental local SQLite library for cleaned LLM conversations."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from llm_export_cleaner.filters import DEFAULT_PROFILE, evaluate_conversation
from llm_export_cleaner.normalizers import Audit, NORMALIZERS
from llm_export_cleaner.timestamps import date_boundary, timestamp_epoch


SCHEMA_VERSION = 3
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports(
 import_id INTEGER PRIMARY KEY, provider TEXT NOT NULL, source_file TEXT NOT NULL,
 source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL, source_bytes INTEGER NOT NULL,
 imported_at_utc TEXT NOT NULL, new_conversations INTEGER NOT NULL DEFAULT 0,
 changed_conversations INTEGER NOT NULL DEFAULT 0, unchanged_conversations INTEGER NOT NULL DEFAULT 0,
 new_messages INTEGER NOT NULL DEFAULT 0, changed_messages INTEGER NOT NULL DEFAULT 0,
 unchanged_messages INTEGER NOT NULL DEFAULT 0, audit_json TEXT NOT NULL DEFAULT '{}',
 UNIQUE(provider,source_sha256));
CREATE TABLE IF NOT EXISTS conversations(
 provider TEXT NOT NULL, conversation_id TEXT NOT NULL, title TEXT,
 created_at TEXT, created_epoch REAL, updated_at TEXT, updated_epoch REAL,
 project_id TEXT, active_leaf_message_id TEXT, message_count INTEGER NOT NULL,
 active_message_count INTEGER NOT NULL, active_user_turn_count INTEGER NOT NULL,
 alternative_message_count INTEGER NOT NULL, record_hash TEXT NOT NULL,
 first_import_id INTEGER NOT NULL, last_import_id INTEGER NOT NULL,
 last_changed_import_id INTEGER NOT NULL,
 PRIMARY KEY(provider,conversation_id));
CREATE TABLE IF NOT EXISTS messages(
 provider TEXT NOT NULL, conversation_id TEXT NOT NULL, message_id TEXT NOT NULL,
 parent_message_id TEXT, role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT,
 created_epoch REAL, is_active_path INTEGER NOT NULL, is_alternative INTEGER NOT NULL,
 attachment_count INTEGER NOT NULL, record_hash TEXT NOT NULL,
 first_import_id INTEGER NOT NULL, last_import_id INTEGER NOT NULL,
 PRIMARY KEY(provider,conversation_id,message_id),
 FOREIGN KEY(provider,conversation_id) REFERENCES conversations(provider,conversation_id));
CREATE TABLE IF NOT EXISTS projects(
 provider TEXT NOT NULL, project_id TEXT NOT NULL, name TEXT NOT NULL,
 PRIMARY KEY(provider,project_id));
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts USING fts5(
 provider UNINDEXED, conversation_id UNINDEXED, title, text, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS cleaning_profiles(
 profile_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, profile_json TEXT NOT NULL,
 created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS filter_results(
 profile_id INTEGER NOT NULL, provider TEXT NOT NULL, conversation_id TEXT NOT NULL,
 source_hash TEXT NOT NULL, included INTEGER NOT NULL, reasons_json TEXT NOT NULL,
 evaluated_at_utc TEXT NOT NULL, PRIMARY KEY(profile_id,provider,conversation_id));
CREATE INDEX IF NOT EXISTS conversations_updated_idx ON conversations(updated_epoch);
CREATE INDEX IF NOT EXISTS filter_included_idx ON filter_results(profile_id,included);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_database_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "LLM Export Cleaner" / "cleaner.sqlite3"


def connect(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(resolved)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.execute("INSERT OR IGNORE INTO meta VALUES('schema_version','1')")
    current = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if current and int(current["value"]) == 1:
        _migrate_to_final_branches_only(db)
        db.execute("UPDATE meta SET value='2' WHERE key='schema_version'")
        current = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if current and int(current["value"]) == 2:
        db.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION),))
        current = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        current = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if not current or int(current["value"]) != SCHEMA_VERSION:
        db.close()
        raise ValueError("Unsupported cleaner database schema")
    ensure_default_profile(db)
    db.commit()
    return db


def _migrate_to_final_branches_only(db: sqlite3.Connection) -> None:
    affected = db.execute(
        "SELECT DISTINCT provider,conversation_id FROM messages WHERE is_active_path=0 OR is_alternative=1"
    ).fetchall()
    db.execute("DELETE FROM messages WHERE is_active_path=0 OR is_alternative=1")
    for row in affected:
        provider, conversation_id = row["provider"], row["conversation_id"]
        messages = db.execute(
            "SELECT text,role FROM messages WHERE provider=? AND conversation_id=? ORDER BY COALESCE(created_epoch,0),rowid",
            (provider, conversation_id),
        ).fetchall()
        count = len(messages)
        user_turns = sum(message["role"] == "user" for message in messages)
        db.execute(
            "UPDATE conversations SET message_count=?,active_message_count=?,active_user_turn_count=?,alternative_message_count=0 WHERE provider=? AND conversation_id=?",
            (count, count, user_turns, provider, conversation_id),
        )
        conversation = db.execute(
            "SELECT title FROM conversations WHERE provider=? AND conversation_id=?", (provider, conversation_id)
        ).fetchone()
        db.execute("DELETE FROM conversation_fts WHERE provider=? AND conversation_id=?", (provider, conversation_id))
        if conversation:
            db.execute(
                "INSERT INTO conversation_fts(provider,conversation_id,title,text) VALUES(?,?,?,?)",
                (provider, conversation_id, conversation["title"] or "", "\n\n".join(message["text"] for message in messages)),
            )


def ensure_default_profile(db: sqlite3.Connection) -> int:
    now = utc_now()
    db.execute(
        "INSERT OR IGNORE INTO cleaning_profiles(name,profile_json,created_at_utc,updated_at_utc) VALUES(?,?,?,?)",
        (DEFAULT_PROFILE["name"], json.dumps(DEFAULT_PROFILE, sort_keys=True), now, now),
    )
    return int(db.execute("SELECT profile_id FROM cleaning_profiles WHERE name=?", (DEFAULT_PROFILE["name"],)).fetchone()[0])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _conversation_metrics(record: dict[str, Any]) -> dict[str, int]:
    messages = record["messages"]
    active = [m for m in messages if m["is_active_path"]]
    return {
        "message_count": len(messages),
        "active_message_count": len(active),
        "active_user_turn_count": sum(m["role"] == "user" for m in active),
        "alternative_message_count": sum(m["is_alternative"] for m in messages),
    }


def import_export(
    *, provider: str, input_path: Path, database_path: Path,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    if provider not in NORMALIZERS:
        raise ValueError(f"Unsupported provider: {provider}")
    source = input_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    db = connect(database_path)
    duplicate = db.execute("SELECT import_id FROM imports WHERE provider=? AND source_sha256=?", (provider, source_hash)).fetchone()
    if duplicate:
        db.close()
        return {"duplicate_export": True, "import_id": int(duplicate[0]), "provider": provider}
    data = json.loads(source.read_text(encoding="utf-8"))
    audit = Audit()
    normalized = list(NORMALIZERS[provider](data, audit))
    stats = Counter()
    now = utc_now()
    try:
        with db:
            cursor = db.execute(
                "INSERT INTO imports(provider,source_file,source_path,source_sha256,source_bytes,imported_at_utc) VALUES(?,?,?,?,?,?)",
                (provider, source.name, str(source), source_hash, source.stat().st_size, now),
            )
            import_id = int(cursor.lastrowid)
            total = len(normalized)
            for index, record in enumerate(normalized, 1):
                _merge_conversation(db, record, import_id, stats)
                if progress:
                    progress(index, total)
            db.execute(
                "UPDATE imports SET new_conversations=?,changed_conversations=?,unchanged_conversations=?,new_messages=?,changed_messages=?,unchanged_messages=?,audit_json=? WHERE import_id=?",
                (stats["new_conversations"], stats["changed_conversations"], stats["unchanged_conversations"], stats["new_messages"], stats["changed_messages"], stats["unchanged_messages"], json.dumps(audit.as_dict(), sort_keys=True), import_id),
            )
            recompute_profiles(db, providers={provider})
    finally:
        db.close()
    return {
        "duplicate_export": False, "import_id": import_id, "provider": provider,
        **{key: int(stats[key]) for key in (
            "new_conversations", "changed_conversations", "unchanged_conversations",
            "new_messages", "changed_messages", "unchanged_messages",
        )},
        "audit": audit.as_dict(),
    }


def _merge_conversation(db: sqlite3.Connection, record: dict[str, Any], import_id: int, stats: Counter[str]) -> None:
    provider, conversation_id = record["provider"], str(record["conversation_id"])
    metrics = _conversation_metrics(record)
    conversation_payload = {k: v for k, v in record.items() if k != "messages"} | metrics
    record_hash = stable_hash(conversation_payload | {"message_hashes": [stable_hash(m) for m in record["messages"]]})
    existing = db.execute("SELECT record_hash,project_id,updated_epoch FROM conversations WHERE provider=? AND conversation_id=?", (provider, conversation_id)).fetchone()
    incoming_updated = timestamp_epoch(record.get("updated_at"))
    if existing is not None and existing["updated_epoch"] is not None and (
        incoming_updated is None or incoming_updated < float(existing["updated_epoch"])
    ):
        db.execute("UPDATE conversations SET last_import_id=? WHERE provider=? AND conversation_id=?", (import_id, provider, conversation_id))
        stats["unchanged_conversations"] += 1
        stats["unchanged_messages"] += len(record["messages"])
        return
    project_id = record.get("project_id") or (existing["project_id"] if existing else None)
    values = (
        record.get("title"), record.get("created_at"), timestamp_epoch(record.get("created_at")),
        record.get("updated_at"), timestamp_epoch(record.get("updated_at")), project_id,
        record.get("active_leaf_message_id"), metrics["message_count"], metrics["active_message_count"],
        metrics["active_user_turn_count"], metrics["alternative_message_count"], record_hash,
    )
    if existing is None:
        db.execute(
            "INSERT INTO conversations(provider,conversation_id,title,created_at,created_epoch,updated_at,updated_epoch,project_id,active_leaf_message_id,message_count,active_message_count,active_user_turn_count,alternative_message_count,record_hash,first_import_id,last_import_id,last_changed_import_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (provider, conversation_id, *values, import_id, import_id, import_id),
        )
        stats["new_conversations"] += 1
    elif existing["record_hash"] == record_hash and existing["project_id"] == project_id:
        db.execute("UPDATE conversations SET last_import_id=? WHERE provider=? AND conversation_id=?", (import_id, provider, conversation_id))
        stats["unchanged_conversations"] += 1
    else:
        db.execute(
            "UPDATE conversations SET title=?,created_at=?,created_epoch=?,updated_at=?,updated_epoch=?,project_id=?,active_leaf_message_id=?,message_count=?,active_message_count=?,active_user_turn_count=?,alternative_message_count=?,record_hash=?,last_import_id=?,last_changed_import_id=? WHERE provider=? AND conversation_id=?",
            (*values, import_id, import_id, provider, conversation_id),
        )
        stats["changed_conversations"] += 1
    changed = existing is None or existing["record_hash"] != record_hash
    for message in record["messages"]:
        _merge_message(db, message, import_id, stats)
    if changed:
        db.execute("DELETE FROM conversation_fts WHERE provider=? AND conversation_id=?", (provider, conversation_id))
        searchable = "\n\n".join(m["text"] for m in record["messages"])
        db.execute("INSERT INTO conversation_fts(provider,conversation_id,title,text) VALUES(?,?,?,?)", (provider, conversation_id, record.get("title") or "", searchable))


def _merge_message(db: sqlite3.Connection, message: dict[str, Any], import_id: int, stats: Counter[str]) -> None:
    key = (message["provider"], message["conversation_id"], message["message_id"])
    message_hash = stable_hash(message)
    existing = db.execute("SELECT record_hash FROM messages WHERE provider=? AND conversation_id=? AND message_id=?", key).fetchone()
    values = (message.get("parent_message_id"), message["role"], message["text"], message.get("created_at"), timestamp_epoch(message.get("created_at")), int(message["is_active_path"]), int(message["is_alternative"]), int(message.get("attachment_count") or 0), message_hash)
    if existing is None:
        db.execute("INSERT INTO messages(provider,conversation_id,message_id,parent_message_id,role,text,created_at,created_epoch,is_active_path,is_alternative,attachment_count,record_hash,first_import_id,last_import_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*key, *values, import_id, import_id))
        stats["new_messages"] += 1
    elif existing["record_hash"] == message_hash:
        db.execute("UPDATE messages SET last_import_id=? WHERE provider=? AND conversation_id=? AND message_id=?", (import_id, *key))
        stats["unchanged_messages"] += 1
    else:
        db.execute("UPDATE messages SET parent_message_id=?,role=?,text=?,created_at=?,created_epoch=?,is_active_path=?,is_alternative=?,attachment_count=?,record_hash=?,last_import_id=? WHERE provider=? AND conversation_id=? AND message_id=?", (*values, import_id, *key))
        stats["changed_messages"] += 1


def save_profile(database_path: Path, profile: dict[str, Any]) -> int:
    name = str(profile.get("name") or "").strip()
    if not name:
        raise ValueError("Profile name is required")
    cleaned = {**DEFAULT_PROFILE, **profile, "name": name}
    cleaned["after_epoch"] = date_boundary(cleaned.get("after"))
    cleaned["before_epoch"] = date_boundary(cleaned.get("before"), end=True)
    db = connect(database_path)
    now = utc_now()
    try:
        with db:
            db.execute(
                "INSERT INTO cleaning_profiles(name,profile_json,created_at_utc,updated_at_utc) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET profile_json=excluded.profile_json,updated_at_utc=excluded.updated_at_utc",
                (name, json.dumps(cleaned, sort_keys=True), now, now),
            )
            profile_id = int(db.execute("SELECT profile_id FROM cleaning_profiles WHERE name=?", (name,)).fetchone()[0])
            recompute_profile(db, profile_id, cleaned)
            return profile_id
    finally:
        db.close()


def list_profiles(database_path: Path) -> list[dict[str, Any]]:
    db = connect(database_path)
    try:
        return [json.loads(row["profile_json"]) | {"profile_id": row["profile_id"]} for row in db.execute("SELECT * FROM cleaning_profiles ORDER BY name")]
    finally:
        db.close()


def recompute_profiles(db: sqlite3.Connection, providers: set[str] | None = None) -> None:
    for row in db.execute("SELECT profile_id,profile_json FROM cleaning_profiles"):
        recompute_profile(db, int(row["profile_id"]), json.loads(row["profile_json"]), providers=providers)


def recompute_profile(db: sqlite3.Connection, profile_id: int, profile: dict[str, Any], providers: set[str] | None = None) -> None:
    clauses, params = [], []
    if providers:
        clauses.append("provider IN (%s)" % ",".join("?" for _ in providers))
        params.extend(sorted(providers))
    sql = "SELECT * FROM conversations" + (" WHERE " + " AND ".join(clauses) if clauses else "")
    now = utc_now()
    for row in db.execute(sql, params):
        record = dict(row)
        included, reasons = evaluate_conversation(record, profile)
        db.execute(
            "INSERT INTO filter_results(profile_id,provider,conversation_id,source_hash,included,reasons_json,evaluated_at_utc) VALUES(?,?,?,?,?,?,?) ON CONFLICT(profile_id,provider,conversation_id) DO UPDATE SET source_hash=excluded.source_hash,included=excluded.included,reasons_json=excluded.reasons_json,evaluated_at_utc=excluded.evaluated_at_utc",
            (profile_id, record["provider"], record["conversation_id"], record["record_hash"], int(included), json.dumps(reasons), now),
        )


def stats(database_path: Path, profile_name: str = "Default") -> dict[str, Any]:
    db = connect(database_path)
    try:
        row = db.execute(
            "SELECT COUNT(*) conversations,COALESCE(SUM(message_count),0) messages,(SELECT COUNT(*) FROM imports) imports FROM conversations"
        ).fetchone()
        profile = db.execute("SELECT profile_id FROM cleaning_profiles WHERE name=?", (profile_name,)).fetchone()
        included = filtered = 0
        if profile:
            counts = db.execute("SELECT included,COUNT(*) count FROM filter_results WHERE profile_id=? GROUP BY included", (profile[0],)).fetchall()
            values = {int(r["included"]): int(r["count"]) for r in counts}
            included, filtered = values.get(1, 0), values.get(0, 0)
        return {**dict(row), "included": included, "filtered": filtered, "database": str(database_path.expanduser().resolve())}
    finally:
        db.close()


def search(
    *, database_path: Path, query: str, profile_name: str = "Default",
    include_filtered: bool = False, provider: str | None = None,
    in_project: bool | None = None, after: str | None = None, before: str | None = None,
    limit: int = 250,
) -> list[dict[str, Any]]:
    tokens = [token for token in query.replace('"', " ").split() if token]
    if not tokens:
        return []
    fts = " AND ".join(f'"{token}"' for token in tokens)
    clauses = ["conversation_fts MATCH ?", "p.name=?"]
    params: list[Any] = [fts, profile_name]
    if not include_filtered:
        clauses.append("r.included=1")
    if provider:
        clauses.append("c.provider=?")
        params.append(provider)
    if in_project is True:
        clauses.append("c.project_id IS NOT NULL")
    elif in_project is False:
        clauses.append("c.project_id IS NULL")
    after_epoch, before_epoch = date_boundary(after), date_boundary(before, end=True)
    if after_epoch is not None:
        clauses.append("COALESCE(c.updated_epoch,c.created_epoch)>=?")
        params.append(after_epoch)
    if before_epoch is not None:
        clauses.append("COALESCE(c.updated_epoch,c.created_epoch)<?")
        params.append(before_epoch)
    params.append(limit)
    db = connect(database_path)
    try:
        rows = db.execute(
            f"""SELECT c.*,r.included,r.reasons_json,
                (SELECT name FROM projects x WHERE x.provider=c.provider AND x.project_id=c.project_id) project_name,
                snippet(conversation_fts,3,'[',']',' ... ',24) snippet
                FROM conversation_fts
                JOIN conversations c USING(provider,conversation_id)
                JOIN cleaning_profiles p ON p.name=?
                JOIN filter_results r ON r.profile_id=p.profile_id AND r.provider=c.provider AND r.conversation_id=c.conversation_id
                WHERE {' AND '.join([clauses[0]] + clauses[2:])}
                ORDER BY bm25(conversation_fts,0,0,1,1),COALESCE(c.updated_epoch,0) DESC LIMIT ?""",
            [profile_name, fts, *params[2:]],
        ).fetchall()
        return [dict(row) | {"reasons": json.loads(row["reasons_json"])} for row in rows]
    finally:
        db.close()


def get_conversation(database_path: Path, provider: str, conversation_id: str) -> dict[str, Any]:
    db = connect(database_path)
    try:
        conversation = db.execute("SELECT * FROM conversations WHERE provider=? AND conversation_id=?", (provider, conversation_id)).fetchone()
        if not conversation:
            raise KeyError("Conversation not found")
        clause = " AND is_active_path=1"
        messages = db.execute(f"SELECT * FROM messages WHERE provider=? AND conversation_id=?{clause} ORDER BY COALESCE(created_epoch,0),rowid", (provider, conversation_id)).fetchall()
        return dict(conversation) | {"messages": [dict(row) for row in messages]}
    finally:
        db.close()


def list_conversations(
    *, database_path: Path, profile_name: str = "Default", include_filtered: bool = False,
    provider: str | None = None, in_project: bool | None = None, limit: int = 500,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = [profile_name]
    if not include_filtered:
        clauses.append("r.included=1")
    if provider:
        clauses.append("c.provider=?")
        params.append(provider)
    if in_project is True:
        clauses.append("c.project_id IS NOT NULL")
    elif in_project is False:
        clauses.append("c.project_id IS NULL")
    params.append(limit)
    db = connect(database_path)
    try:
        rows = db.execute(
            f"""SELECT c.*,r.included,r.reasons_json,
                (SELECT name FROM projects x WHERE x.provider=c.provider AND x.project_id=c.project_id) project_name
                FROM conversations c
                JOIN cleaning_profiles p ON p.name=?
                JOIN filter_results r ON r.profile_id=p.profile_id AND r.provider=c.provider AND r.conversation_id=c.conversation_id
                WHERE {' AND '.join(clauses) if clauses else '1=1'}
                ORDER BY COALESCE(c.updated_epoch,c.created_epoch,0) DESC LIMIT ?""",
            params,
        ).fetchall()
        return [dict(row) | {"reasons": json.loads(row["reasons_json"])} for row in rows]
    finally:
        db.close()


def import_history(database_path: Path, limit: int = 100) -> list[dict[str, Any]]:
    db = connect(database_path)
    try:
        return [dict(row) for row in db.execute("SELECT * FROM imports ORDER BY import_id DESC LIMIT ?", (limit,))]
    finally:
        db.close()
