"""SQLite storage layer (stdlib sqlite3, WAL mode, FTS5).

No FastAPI imports here — this module is pure data access so the core
engines stay testable without a running server.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    genre TEXT NOT NULL DEFAULT '',
    tone TEXT NOT NULL DEFAULT '',
    premise TEXT NOT NULL DEFAULT '',
    rules_text TEXT NOT NULL DEFAULT '',
    ruleset TEXT NOT NULL DEFAULT 'freeform',
    content_lines TEXT NOT NULL DEFAULT '[]',
    content_veils TEXT NOT NULL DEFAULT '[]',
    calendar_json TEXT NOT NULL DEFAULT '{}',
    style_notes TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'es',
    current_session_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    fields_json TEXT NOT NULL DEFAULT '{}',
    secrets TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'alive',
    tags_json TEXT NOT NULL DEFAULT '[]',
    parent_id TEXT,
    images_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_world ON entities(world_id);
CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(world_id, kind);

CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id UNINDEXED, world_id UNINDEXED,
    name, aliases, summary, description, tags,
    tokenize = "unicode61 remove_diacritics 2"
);

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    a_id TEXT NOT NULL,
    b_id TEXT NOT NULL,
    type TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    since TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relations_world ON relations(world_id);
CREATE INDEX IF NOT EXISTS idx_relations_a ON relations(a_id);
CREATE INDEX IF NOT EXISTS idx_relations_b ON relations(b_id);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    session_id TEXT,
    turn_id TEXT,
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    canon INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_world ON facts(world_id);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    id UNINDEXED, world_id UNINDEXED, text,
    tokenize = "unicode61 remove_diacritics 2"
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    in_world_date TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL,
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    session_id TEXT,
    turn_id TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_timeline_world ON timeline_events(world_id);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_world ON threads(world_id);

CREATE TABLE IF NOT EXISTS clocks (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    segments INTEGER NOT NULL DEFAULT 4,
    filled INTEGER NOT NULL DEFAULT 0,
    on_full TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clocks_world ON clocks(world_id);

CREATE TABLE IF NOT EXISTS random_tables (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    entries_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tables_world ON random_tables(world_id);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sessions_world ON sessions(world_id);

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    role TEXT NOT NULL,
    author TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    rolls_json TEXT NOT NULL DEFAULT '[]',
    scene_json TEXT NOT NULL DEFAULT '{}',
    delta_json TEXT NOT NULL DEFAULT 'null',
    applied INTEGER NOT NULL DEFAULT 0,
    undone INTEGER NOT NULL DEFAULT 0,
    undo_snapshot_json TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, idx);
CREATE INDEX IF NOT EXISTS idx_turns_world ON turns(world_id);

CREATE TABLE IF NOT EXISTS dice_log (
    id TEXT PRIMARY KEY,
    world_id TEXT,
    expression TEXT NOT NULL,
    result INTEGER NOT NULL,
    dice_json TEXT NOT NULL DEFAULT '[]',
    seed INTEGER,
    reason TEXT NOT NULL DEFAULT '',
    who TEXT NOT NULL DEFAULT 'agent',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dice_world ON dice_log(world_id);

CREATE TABLE IF NOT EXISTS agent_calls (
    id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    args_summary TEXT NOT NULL DEFAULT '',
    duration_ms REAL NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_calls_created ON agent_calls(created_at DESC);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def new_id(prefix: str = "") -> str:
    token = uuid.uuid4().hex[:12]
    return f"{prefix}{token}" if prefix else token


def now() -> float:
    return time.time()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return conn


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(text: Optional[str], default: Any = None) -> Any:
    if text is None:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]
