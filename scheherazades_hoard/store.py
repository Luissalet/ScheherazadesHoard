"""CRUD and lookup helpers over the SQLite schema in `db.py`.

Every function takes an open `sqlite3.Connection` as its first argument and
returns plain dicts (JSON columns already decoded) so the engines, the API
and the MCP adapter share one source of truth. No FastAPI imports here.
"""
from __future__ import annotations

import sqlite3
import unicodedata
from typing import Any, Optional

from . import db


class NotFound(KeyError):
    """A world/entity/thread/... reference did not resolve."""

    def __str__(self) -> str:  # KeyError would wrap the message in quotes
        return str(self.args[0]) if self.args else "not found"


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _norm(text: str) -> str:
    return _strip_accents(text).strip().lower()


def _next_seq(conn: sqlite3.Connection, table: str, world_id: str) -> int:
    row = conn.execute(
        f"SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM {table} WHERE world_id = ?",
        (world_id,),
    ).fetchone()
    return int(row["n"])


# ---------------------------------------------------------------------------
# Worlds
# ---------------------------------------------------------------------------

def create_world(
    conn: sqlite3.Connection,
    name: str,
    genre: str = "",
    tone: str = "",
    premise: str = "",
    ruleset: str = "freeform",
    language: str = "es",
    rules_text: str = "",
    content_lines: Optional[list[str]] = None,
    content_veils: Optional[list[str]] = None,
    calendar: Optional[dict] = None,
    style_notes: str = "",
) -> dict:
    if ruleset not in ("freeform", "d20", "pbta_2d6"):
        raise ValueError(f"unknown ruleset: {ruleset!r}")
    world_id = db.new_id("w_")
    ts = db.now()
    conn.execute(
        """INSERT INTO worlds
           (id, name, genre, tone, premise, rules_text, ruleset, content_lines,
            content_veils, calendar_json, style_notes, language, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            world_id, name, genre, tone, premise, rules_text, ruleset,
            db.dumps(content_lines or []), db.dumps(content_veils or []),
            db.dumps(calendar or {}), style_notes, language, ts, ts,
        ),
    )
    conn.commit()
    return get_world(conn, world_id)


def find_world_id(conn: sqlite3.Connection, ref: str) -> Optional[str]:
    row = conn.execute("SELECT id FROM worlds WHERE id = ?", (ref,)).fetchone()
    if row:
        return row["id"]
    norm = _norm(ref)
    for r in conn.execute("SELECT id, name FROM worlds"):
        if _norm(r["name"]) == norm:
            return r["id"]
    return None


def resolve_world_id(conn: sqlite3.Connection, ref: str) -> str:
    world_id = find_world_id(conn, ref)
    if world_id is None:
        names = [r["name"] for r in conn.execute("SELECT name FROM worlds ORDER BY updated_at DESC LIMIT 5")]
        hint = f"; known worlds: {', '.join(names)}" if names else "; there are no worlds yet (story_world_create)"
        raise NotFound(f"no world matches {ref!r}{hint}")
    return world_id


def _decode_world(row: dict) -> dict:
    row = dict(row)
    row["content_lines"] = db.loads(row.pop("content_lines"), [])
    row["content_veils"] = db.loads(row.pop("content_veils"), [])
    row["calendar"] = db.loads(row.pop("calendar_json"), {})
    return row


def get_world(conn: sqlite3.Connection, ref: str) -> dict:
    world_id = resolve_world_id(conn, ref)
    row = conn.execute("SELECT * FROM worlds WHERE id = ?", (world_id,)).fetchone()
    return _decode_world(dict(row))


def list_worlds(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for row in conn.execute("SELECT * FROM worlds ORDER BY updated_at DESC"):
        w = _decode_world(dict(row))
        counts = conn.execute(
            "SELECT "
            " (SELECT COUNT(*) FROM entities WHERE world_id = ?) AS entities,"
            " (SELECT COUNT(*) FROM threads WHERE world_id = ? AND status = 'open') AS open_threads,"
            " (SELECT COUNT(*) FROM sessions WHERE world_id = ?) AS sessions",
            (w["id"], w["id"], w["id"]),
        ).fetchone()
        w["counts"] = dict(counts)
        w["current_session"] = None
        if w.get("current_session_id"):
            srow = conn.execute(
                "SELECT id, title FROM sessions WHERE id = ?", (w["current_session_id"],)
            ).fetchone()
            if srow:
                w["current_session"] = dict(srow)
        out.append(w)
    return out


def update_world(conn: sqlite3.Connection, ref: str, **patch: Any) -> dict:
    world_id = resolve_world_id(conn, ref)
    allowed = {
        "name", "genre", "tone", "premise", "rules_text", "ruleset",
        "content_lines", "content_veils", "calendar", "style_notes",
        "language", "current_session_id",
    }
    sets, values = [], []
    for key, value in patch.items():
        if key not in allowed or value is None:
            continue
        column = {
            "content_lines": "content_lines", "content_veils": "content_veils",
            "calendar": "calendar_json",
        }.get(key, key)
        if key in ("content_lines", "content_veils", "calendar"):
            value = db.dumps(value)
        sets.append(f"{column} = ?")
        values.append(value)
    if sets:
        sets.append("updated_at = ?")
        values.append(db.now())
        values.append(world_id)
        conn.execute(f"UPDATE worlds SET {', '.join(sets)} WHERE id = ?", values)
        conn.commit()
    return get_world(conn, world_id)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

VALID_KINDS = {"character", "location", "faction", "item", "lore", "creature"}
VALID_STATUS = {"alive", "dead", "missing", "destroyed", "active", "unknown"}
# Spanish (and a few English) spellings a model is likely to write, folded
# to the canonical status the rest of the engine reasons about. Without
# this, "muerta" would not count as dead and the character could act again.
_STATUS_ALIASES = {
    "vivo": "alive", "viva": "alive", "deceased": "dead", "muerto": "dead", "muerta": "dead",
    "fallecido": "dead", "fallecida": "dead", "desaparecido": "missing", "desaparecida": "missing",
    "perdido": "missing", "perdida": "missing", "destruido": "destroyed", "destruida": "destroyed",
    "activo": "active", "activa": "active", "desconocido": "unknown", "desconocida": "unknown",
}


def normalize_status(value: str) -> str:
    """Canonical entity status, or ValueError listing the accepted values."""
    folded = _norm(value or "")
    folded = _STATUS_ALIASES.get(folded, folded)
    if folded not in VALID_STATUS:
        raise ValueError(
            f"unknown entity status: {value!r}; use one of {', '.join(sorted(VALID_STATUS))}"
        )
    return folded


def validate_kind(kind: str) -> str:
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown entity kind: {kind!r}; use one of {', '.join(sorted(VALID_KINDS))}")
    return kind


def _decode_entity(row: dict) -> dict:
    row = dict(row)
    row["aliases"] = db.loads(row.pop("aliases_json"), [])
    row["fields"] = db.loads(row.pop("fields_json"), {})
    row["tags"] = db.loads(row.pop("tags_json"), [])
    row["images"] = db.loads(row.pop("images_json"), [])
    row["ref"] = f"E{row['seq']}"
    return row


def _fts_upsert_entity(conn: sqlite3.Connection, e: dict) -> None:
    conn.execute("DELETE FROM entities_fts WHERE id = ?", (e["id"],))
    conn.execute(
        "INSERT INTO entities_fts (id, world_id, name, aliases, summary, description, tags)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            e["id"], e["world_id"], e["name"],
            " ".join(e.get("aliases") or []), e.get("summary", ""),
            e.get("description", ""), " ".join(e.get("tags") or []),
        ),
    )


def create_entity(
    conn: sqlite3.Connection,
    world_id: str,
    kind: str,
    name: str,
    aliases: Optional[list[str]] = None,
    summary: str = "",
    description: str = "",
    fields: Optional[dict] = None,
    secrets: str = "",
    status: str = "alive",
    tags: Optional[list[str]] = None,
    parent_id: Optional[str] = None,
    images: Optional[list[str]] = None,
    commit: bool = True,
) -> dict:
    validate_kind(kind)
    if not name or not name.strip():
        raise ValueError("entity name is required")
    status = normalize_status(status)
    entity_id = db.new_id("e_")
    seq = _next_seq(conn, "entities", world_id)
    ts = db.now()
    conn.execute(
        """INSERT INTO entities
           (id, world_id, seq, kind, name, aliases_json, summary, description,
            fields_json, secrets, status, tags_json, parent_id, images_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            entity_id, world_id, seq, kind, name.strip(), db.dumps(aliases or []),
            summary, description, db.dumps(fields or {}), secrets, status,
            db.dumps(tags or []), parent_id, db.dumps(images or []), ts, ts,
        ),
    )
    e = _decode_entity(dict(conn.execute(
        "SELECT * FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()))
    _fts_upsert_entity(conn, e)
    if commit:
        conn.commit()
    return e


def resolve_entity_id(conn: sqlite3.Connection, world_id: str, ref: str) -> str:
    """Resolve an entity by internal id, short ref (E12), or name/alias."""
    row = conn.execute(
        "SELECT id FROM entities WHERE world_id = ? AND id = ?", (world_id, ref)
    ).fetchone()
    if row:
        return row["id"]
    if ref.upper().startswith("E") and ref[1:].isdigit():
        row = conn.execute(
            "SELECT id FROM entities WHERE world_id = ? AND seq = ?",
            (world_id, int(ref[1:])),
        ).fetchone()
        if row:
            return row["id"]
    norm = _norm(ref)
    for r in conn.execute(
        "SELECT id, name, aliases_json FROM entities WHERE world_id = ?", (world_id,)
    ):
        if _norm(r["name"]) == norm:
            return r["id"]
        for alias in db.loads(r["aliases_json"], []):
            if _norm(alias) == norm:
                return r["id"]
    raise NotFound(f"no entity matches {ref!r}")


def get_entity(conn: sqlite3.Connection, world_id: str, ref: str) -> dict:
    entity_id = resolve_entity_id(conn, world_id, ref)
    row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return _decode_entity(dict(row))


def list_entities(
    conn: sqlite3.Connection,
    world_id: str,
    kind: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    q = "SELECT * FROM entities WHERE world_id = ?"
    params: list[Any] = [world_id]
    if kind:
        q += " AND kind = ?"
        params.append(kind)
    q += " ORDER BY seq LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return [_decode_entity(dict(r)) for r in conn.execute(q, params)]


def upsert_entity(
    conn: sqlite3.Connection,
    world_id: str,
    kind: str,
    name: str,
    **fields_kw: Any,
) -> dict:
    """Create the entity, or update it in place if the name/alias already exists.

    On update only the values actually passed (not None) change, and
    `fields` is merged into the existing fields instead of replacing them,
    so "add a trait" never wipes the summary, the secrets or the stats, and
    never silently resurrects a dead character. The name an alias matched
    is kept (the caller may have used the alias). A different `kind` for
    an existing name is refused rather than silently converting it.
    """
    validate_kind(kind)
    patch = {k: v for k, v in fields_kw.items() if v is not None}
    try:
        existing = get_entity(conn, world_id, name)
    except NotFound:
        return create_entity(conn, world_id, kind, name, **patch)
    if existing["kind"] != kind:
        raise ValueError(
            f"{existing['name']!r} already exists as a {existing['kind']} ({existing['ref']}); "
            f"pass kind={existing['kind']!r} to update it, or choose a different name"
        )
    if "fields" in patch:
        patch["fields_patch"] = patch.pop("fields")
    return update_entity(conn, world_id, existing["id"], **patch)


def update_entity(conn: sqlite3.Connection, world_id: str, ref: str, commit: bool = True, **patch: Any) -> dict:
    entity_id = resolve_entity_id(conn, world_id, ref)
    allowed_json = {"aliases": "aliases_json", "fields": "fields_json",
                    "tags": "tags_json", "images": "images_json"}
    allowed_plain = {"kind", "name", "summary", "description", "secrets", "status", "parent_id"}
    sets, values = [], []
    for key, value in patch.items():
        if value is None:
            continue
        if key == "kind":
            validate_kind(value)
        elif key == "status":
            value = normalize_status(value)
        elif key == "name" and not str(value).strip():
            raise ValueError("entity name cannot be empty")
        if key in allowed_json:
            sets.append(f"{allowed_json[key]} = ?")
            values.append(db.dumps(value))
        elif key == "fields_patch" and isinstance(value, dict):
            current = db.loads(
                conn.execute("SELECT fields_json FROM entities WHERE id = ?", (entity_id,)).fetchone()["fields_json"],
                {},
            )
            current.update(value)
            sets.append("fields_json = ?")
            values.append(db.dumps(current))
        elif key in allowed_plain:
            sets.append(f"{key} = ?")
            values.append(value)
    if sets:
        sets.append("updated_at = ?")
        values.append(db.now())
        values.append(entity_id)
        conn.execute(f"UPDATE entities SET {', '.join(sets)} WHERE id = ?", values)
        e = _decode_entity(dict(conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()))
        _fts_upsert_entity(conn, e)
        if commit:
            conn.commit()
        return e
    return get_entity(conn, world_id, entity_id)


def delete_entity(conn: sqlite3.Connection, entity_id: str, commit: bool = True) -> None:
    conn.execute("DELETE FROM entities_fts WHERE id = ?", (entity_id,))
    conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    delete_relations_for(conn, entity_id)
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------

def create_relation(
    conn: sqlite3.Connection, world_id: str, a_id: str, b_id: str,
    type: str, note: str = "", since: str = "", commit: bool = True,
) -> dict:
    rel_id = db.new_id("r_")
    ts = db.now()
    conn.execute(
        "INSERT INTO relations (id, world_id, a_id, b_id, type, note, since, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (rel_id, world_id, a_id, b_id, type, note, since, ts),
    )
    if commit:
        conn.commit()
    return dict(conn.execute("SELECT * FROM relations WHERE id = ?", (rel_id,)).fetchone())


def list_relations(conn: sqlite3.Connection, world_id: str, entity_id: Optional[str] = None) -> list[dict]:
    if entity_id:
        rows = conn.execute(
            "SELECT * FROM relations WHERE world_id = ? AND (a_id = ? OR b_id = ?) ORDER BY created_at",
            (world_id, entity_id, entity_id),
        )
    else:
        rows = conn.execute(
            "SELECT * FROM relations WHERE world_id = ? ORDER BY created_at", (world_id,)
        )
    return [dict(r) for r in rows]


def delete_relations_for(conn: sqlite3.Connection, entity_id: str) -> None:
    conn.execute("DELETE FROM relations WHERE a_id = ? OR b_id = ?", (entity_id, entity_id))


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

def _decode_fact(row: dict) -> dict:
    row = dict(row)
    row["entity_ids"] = db.loads(row.pop("entity_ids_json"), [])
    row["canon"] = bool(row["canon"])
    row["ref"] = f"F{row['seq']}"
    return row


def create_fact(
    conn: sqlite3.Connection, world_id: str, text: str,
    session_id: Optional[str] = None, turn_id: Optional[str] = None,
    entity_ids: Optional[list[str]] = None, canon: bool = False,
    commit: bool = True,
) -> dict:
    fact_id = db.new_id("f_")
    seq = _next_seq(conn, "facts", world_id)
    ts = db.now()
    conn.execute(
        "INSERT INTO facts (id, world_id, seq, text, session_id, turn_id, entity_ids_json, canon, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (fact_id, world_id, seq, text, session_id, turn_id, db.dumps(entity_ids or []), int(canon), ts),
    )
    conn.execute(
        "INSERT INTO facts_fts (id, world_id, text) VALUES (?,?,?)",
        (fact_id, world_id, text),
    )
    if commit:
        conn.commit()
    return _decode_fact(dict(conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()))


def resolve_fact_id(conn: sqlite3.Connection, world_id: str, ref: str) -> str:
    row = conn.execute("SELECT id FROM facts WHERE world_id = ? AND id = ?", (world_id, ref)).fetchone()
    if row:
        return row["id"]
    if ref.upper().startswith("F") and ref[1:].isdigit():
        row = conn.execute(
            "SELECT id FROM facts WHERE world_id = ? AND seq = ?", (world_id, int(ref[1:]))
        ).fetchone()
        if row:
            return row["id"]
    raise NotFound(f"no fact matches {ref!r}")


def get_fact(conn: sqlite3.Connection, world_id: str, ref: str) -> dict:
    fact_id = resolve_fact_id(conn, world_id, ref)
    return _decode_fact(dict(conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()))


def list_facts(conn: sqlite3.Connection, world_id: str, entity_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Newest first. With `entity_id`, only facts linked to that entity —
    filtered in SQL, so an entity's facts are found however many newer
    facts about other entities exist."""
    if entity_id:
        rows = conn.execute(
            "SELECT * FROM facts WHERE world_id = ? AND EXISTS ("
            " SELECT 1 FROM json_each(facts.entity_ids_json) WHERE json_each.value = ?)"
            " ORDER BY seq DESC LIMIT ?",
            (world_id, entity_id, limit),
        )
    else:
        rows = conn.execute(
            "SELECT * FROM facts WHERE world_id = ? ORDER BY seq DESC LIMIT ?", (world_id, limit),
        )
    return [_decode_fact(dict(r)) for r in rows]


def search_facts(conn: sqlite3.Connection, world_id: str, query: str, limit: int = 8) -> list[dict]:
    if not query.strip():
        return []
    try:
        rows = conn.execute(
            "SELECT facts.* FROM facts_fts JOIN facts ON facts.id = facts_fts.id"
            " WHERE facts_fts.world_id = ? AND facts_fts MATCH ?"
            " ORDER BY bm25(facts_fts) LIMIT ?",
            (world_id, _fts_query(query), limit),
        )
        return [_decode_fact(dict(r)) for r in rows]
    except sqlite3.OperationalError:
        return []


def _fts_query(text: str) -> str:
    """Build a safe FTS5 MATCH query: OR of the individual terms, quoted."""
    terms = [t for t in text.replace('"', " ").split() if t]
    if not terms:
        return '""'
    return " OR ".join(f'"{t}"' for t in terms)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def create_timeline_event(
    conn: sqlite3.Connection, world_id: str, in_world_date: str, summary: str,
    entity_ids: Optional[list[str]] = None, session_id: Optional[str] = None,
    turn_id: Optional[str] = None, commit: bool = True,
) -> dict:
    ev_id = db.new_id("t_")
    ts = db.now()
    conn.execute(
        "INSERT INTO timeline_events (id, world_id, in_world_date, summary, entity_ids_json, session_id, turn_id, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (ev_id, world_id, in_world_date, summary, db.dumps(entity_ids or []), session_id, turn_id, ts),
    )
    if commit:
        conn.commit()
    row = dict(conn.execute("SELECT * FROM timeline_events WHERE id = ?", (ev_id,)).fetchone())
    row["entity_ids"] = db.loads(row.pop("entity_ids_json"), [])
    return row


def list_timeline(conn: sqlite3.Connection, world_id: str, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM timeline_events WHERE world_id = ? ORDER BY created_at LIMIT ?",
        (world_id, limit),
    )
    out = []
    for r in rows:
        d = dict(r)
        d["entity_ids"] = db.loads(d.pop("entity_ids_json"), [])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------

VALID_THREAD_STATUS = {"open", "advanced", "resolved", "abandoned"}


def _decode_thread(row: dict) -> dict:
    row = dict(row)
    row["ref"] = f"T{row['seq']}"
    return row


def create_thread(
    conn: sqlite3.Connection, world_id: str, title: str, status: str = "open",
    notes: str = "", commit: bool = True,
) -> dict:
    if status not in VALID_THREAD_STATUS:
        raise ValueError(f"unknown thread status: {status!r}")
    thread_id = db.new_id("th_")
    seq = _next_seq(conn, "threads", world_id)
    ts = db.now()
    conn.execute(
        "INSERT INTO threads (id, world_id, seq, title, status, notes, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (thread_id, world_id, seq, title, status, notes, ts, ts),
    )
    if commit:
        conn.commit()
    return _decode_thread(dict(conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()))


def resolve_thread_id(conn: sqlite3.Connection, world_id: str, ref: str) -> str:
    row = conn.execute("SELECT id FROM threads WHERE world_id = ? AND id = ?", (world_id, ref)).fetchone()
    if row:
        return row["id"]
    if ref.upper().startswith("T") and ref[1:].isdigit():
        row = conn.execute(
            "SELECT id FROM threads WHERE world_id = ? AND seq = ?", (world_id, int(ref[1:]))
        ).fetchone()
        if row:
            return row["id"]
    norm = _norm(ref)
    for r in conn.execute("SELECT id, title FROM threads WHERE world_id = ?", (world_id,)):
        if _norm(r["title"]) == norm:
            return r["id"]
    raise NotFound(f"no thread matches {ref!r}")


def get_thread(conn: sqlite3.Connection, world_id: str, ref: str) -> dict:
    thread_id = resolve_thread_id(conn, world_id, ref)
    return _decode_thread(dict(conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()))


def list_threads(conn: sqlite3.Connection, world_id: str, status: Optional[str] = None) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT * FROM threads WHERE world_id = ? AND status = ? ORDER BY seq", (world_id, status)
        )
    else:
        rows = conn.execute("SELECT * FROM threads WHERE world_id = ? ORDER BY seq", (world_id,))
    return [_decode_thread(dict(r)) for r in rows]


def update_thread(
    conn: sqlite3.Connection, world_id: str, ref: str,
    status: Optional[str] = None, note: Optional[str] = None, commit: bool = True,
) -> dict:
    thread_id = resolve_thread_id(conn, world_id, ref)
    sets, values = [], []
    if status is not None:
        if status not in VALID_THREAD_STATUS:
            raise ValueError(f"unknown thread status: {status!r}")
        sets.append("status = ?")
        values.append(status)
    if note is not None:
        current = conn.execute("SELECT notes FROM threads WHERE id = ?", (thread_id,)).fetchone()["notes"]
        merged = f"{current}\n{note}".strip() if current else note
        sets.append("notes = ?")
        values.append(merged)
    if sets:
        sets.append("updated_at = ?")
        values.append(db.now())
        values.append(thread_id)
        conn.execute(f"UPDATE threads SET {', '.join(sets)} WHERE id = ?", values)
        if commit:
            conn.commit()
    return get_thread(conn, world_id, thread_id)


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------

def _decode_clock(row: dict) -> dict:
    row = dict(row)
    row["ref"] = f"C{row['seq']}"
    row["full"] = row["filled"] >= row["segments"]
    return row


def create_clock(conn: sqlite3.Connection, world_id: str, name: str, segments: int = 4, on_full: str = "") -> dict:
    if segments not in (4, 6, 8):
        raise ValueError("clock segments must be 4, 6 or 8")
    clock_id = db.new_id("c_")
    seq = _next_seq(conn, "clocks", world_id)
    ts = db.now()
    conn.execute(
        "INSERT INTO clocks (id, world_id, seq, name, segments, filled, on_full, created_at, updated_at)"
        " VALUES (?,?,?,?,?,0,?,?,?)",
        (clock_id, world_id, seq, name, segments, on_full, ts, ts),
    )
    conn.commit()
    return _decode_clock(dict(conn.execute("SELECT * FROM clocks WHERE id = ?", (clock_id,)).fetchone()))


def resolve_clock_id(conn: sqlite3.Connection, world_id: str, ref: str) -> str:
    row = conn.execute("SELECT id FROM clocks WHERE world_id = ? AND id = ?", (world_id, ref)).fetchone()
    if row:
        return row["id"]
    if ref.upper().startswith("C") and ref[1:].isdigit():
        row = conn.execute(
            "SELECT id FROM clocks WHERE world_id = ? AND seq = ?", (world_id, int(ref[1:]))
        ).fetchone()
        if row:
            return row["id"]
    norm = _norm(ref)
    for r in conn.execute("SELECT id, name FROM clocks WHERE world_id = ?", (world_id,)):
        if _norm(r["name"]) == norm:
            return r["id"]
    raise NotFound(f"no clock matches {ref!r}")


def list_clocks(conn: sqlite3.Connection, world_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM clocks WHERE world_id = ? ORDER BY seq", (world_id,))
    return [_decode_clock(dict(r)) for r in rows]


def get_clock(conn: sqlite3.Connection, world_id: str, ref: str) -> dict:
    clock_id = resolve_clock_id(conn, world_id, ref)
    return _decode_clock(dict(conn.execute("SELECT * FROM clocks WHERE id = ?", (clock_id,)).fetchone()))


def tick_clock(conn: sqlite3.Connection, world_id: str, ref: str, ticks: int = 1, commit: bool = True) -> dict:
    clock_id = resolve_clock_id(conn, world_id, ref)
    row = conn.execute("SELECT * FROM clocks WHERE id = ?", (clock_id,)).fetchone()
    new_filled = max(0, min(row["segments"], row["filled"] + ticks))
    conn.execute(
        "UPDATE clocks SET filled = ?, updated_at = ? WHERE id = ?", (new_filled, db.now(), clock_id)
    )
    if commit:
        conn.commit()
    return get_clock(conn, world_id, clock_id)


# ---------------------------------------------------------------------------
# Random tables
# ---------------------------------------------------------------------------

def _clean_table_entries(entries: Any) -> list[dict]:
    if not isinstance(entries, list) or not entries:
        raise ValueError("a table needs a non-empty list of entries like {\"text\": \"...\", \"weight\": 1}")
    clean = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("text"), str) or not e["text"].strip():
            raise ValueError("each table entry needs a non-empty 'text' string")
        weight = e.get("weight", 1)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
            raise ValueError(f"entry weight must be a number >= 0, got {weight!r}")
        clean.append({"text": e["text"].strip(), "weight": weight})
    if sum(e["weight"] for e in clean) <= 0:
        raise ValueError("at least one table entry needs a weight above 0")
    return clean


def create_table(conn: sqlite3.Connection, world_id: str, name: str, entries: list[dict]) -> dict:
    if not name or not name.strip():
        raise ValueError("table name is required")
    entries = _clean_table_entries(entries)
    table_id = db.new_id("tbl_")
    ts = db.now()
    conn.execute(
        "INSERT INTO random_tables (id, world_id, name, entries_json, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (table_id, world_id, name, db.dumps(entries), ts, ts),
    )
    conn.commit()
    return _decode_table(dict(conn.execute("SELECT * FROM random_tables WHERE id = ?", (table_id,)).fetchone()))


def _decode_table(row: dict) -> dict:
    row = dict(row)
    row["entries"] = db.loads(row.pop("entries_json"), [])
    return row


def resolve_table_id(conn: sqlite3.Connection, world_id: str, ref: str) -> str:
    row = conn.execute("SELECT id FROM random_tables WHERE world_id = ? AND id = ?", (world_id, ref)).fetchone()
    if row:
        return row["id"]
    norm = _norm(ref)
    for r in conn.execute("SELECT id, name FROM random_tables WHERE world_id = ?", (world_id,)):
        if _norm(r["name"]) == norm:
            return r["id"]
    raise NotFound(f"no table matches {ref!r}")


def get_table(conn: sqlite3.Connection, world_id: str, ref: str) -> dict:
    table_id = resolve_table_id(conn, world_id, ref)
    return _decode_table(dict(conn.execute("SELECT * FROM random_tables WHERE id = ?", (table_id,)).fetchone()))


def list_tables(conn: sqlite3.Connection, world_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM random_tables WHERE world_id = ? ORDER BY created_at", (world_id,))
    return [_decode_table(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Sessions & turns
# ---------------------------------------------------------------------------

def start_session(conn: sqlite3.Connection, world_id: str, title: str = "") -> dict:
    session_id = db.new_id("s_")
    ts = db.now()
    if not title:
        n = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE world_id = ?", (world_id,)).fetchone()["n"]
        title = f"Session {n + 1}"
    conn.execute(
        "INSERT INTO sessions (id, world_id, title, started_at, ended_at) VALUES (?,?,?,?,NULL)",
        (session_id, world_id, title, ts),
    )
    conn.execute("UPDATE worlds SET current_session_id = ?, updated_at = ? WHERE id = ?", (session_id, ts, world_id))
    conn.commit()
    return dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())


def get_current_session(conn: sqlite3.Connection, world_id: str) -> Optional[dict]:
    """The world's current session, or None (never creates one — safe for reads)."""
    world = conn.execute("SELECT current_session_id FROM worlds WHERE id = ?", (world_id,)).fetchone()
    if world and world["current_session_id"]:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (world["current_session_id"],)).fetchone()
        if row:
            return dict(row)
    return None


def get_or_create_current_session(conn: sqlite3.Connection, world_id: str) -> dict:
    return get_current_session(conn, world_id) or start_session(conn, world_id)


def current_scene(conn: sqlite3.Connection, world_id: str) -> dict:
    """The scene of the world's latest live (not undone) turn that has one."""
    row = conn.execute(
        "SELECT scene_json FROM turns WHERE world_id = ? AND undone = 0"
        " AND scene_json NOT IN ('{}', 'null', '') ORDER BY created_at DESC, idx DESC LIMIT 1",
        (world_id,),
    ).fetchone()
    return db.loads(row["scene_json"], {}) if row else {}


def list_sessions(conn: sqlite3.Connection, world_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM sessions WHERE world_id = ? ORDER BY started_at", (world_id,))
    return [dict(r) for r in rows]


def resolve_session_id(conn: sqlite3.Connection, world_id: str, ref: Optional[str]) -> str:
    if not ref:
        return get_or_create_current_session(conn, world_id)["id"]
    row = conn.execute("SELECT id FROM sessions WHERE world_id = ? AND id = ?", (world_id, ref)).fetchone()
    if row:
        return row["id"]
    norm = _norm(ref)
    for r in conn.execute("SELECT id, title FROM sessions WHERE world_id = ?", (world_id,)):
        if _norm(r["title"]) == norm:
            return r["id"]
    raise NotFound(f"no session matches {ref!r}")


VALID_ROLES = {"narration", "action", "dialogue", "ooc", "roll", "system"}
VALID_AUTHORS = {"user", "narrator", "agent"}


def validate_turn(role: str, author: str) -> None:
    if role not in VALID_ROLES:
        raise ValueError(f"unknown turn role: {role!r}; use one of {', '.join(sorted(VALID_ROLES))}")
    if author not in VALID_AUTHORS:
        raise ValueError(f"unknown turn author: {author!r}; use one of {', '.join(sorted(VALID_AUTHORS))}")


def _decode_turn(row: dict) -> dict:
    row = dict(row)
    row["rolls"] = db.loads(row.pop("rolls_json"), [])
    row["scene"] = db.loads(row.pop("scene_json"), {})
    row["delta"] = db.loads(row.pop("delta_json"), None)
    row["applied"] = bool(row["applied"])
    row["undone"] = bool(row["undone"])
    row.pop("undo_snapshot_json", None)
    return row


def append_turn(
    conn: sqlite3.Connection, world_id: str, session_id: str, role: str, author: str,
    text: str = "", rolls: Optional[list] = None, scene: Optional[dict] = None,
    delta: Optional[dict] = None, applied: bool = False,
    undo_snapshot: Optional[dict] = None, commit: bool = True,
) -> dict:
    validate_turn(role, author)
    row = conn.execute(
        "SELECT COALESCE(MAX(idx), -1) + 1 AS n FROM turns WHERE session_id = ?", (session_id,)
    ).fetchone()
    idx = int(row["n"])
    turn_id = db.new_id("tn_")
    ts = db.now()
    conn.execute(
        """INSERT INTO turns
           (id, world_id, session_id, idx, role, author, text, rolls_json, scene_json,
            delta_json, applied, undone, undo_snapshot_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
        (
            turn_id, world_id, session_id, idx, role, author, text,
            db.dumps(rolls or []), db.dumps(scene or {}), db.dumps(delta),
            int(applied), db.dumps(undo_snapshot) if undo_snapshot is not None else None, ts,
        ),
    )
    if commit:
        conn.commit()
    return _decode_turn(dict(conn.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()))


def list_turns(conn: sqlite3.Connection, session_id: str, limit: Optional[int] = None) -> list[dict]:
    q = "SELECT * FROM turns WHERE session_id = ? ORDER BY idx"
    params: list[Any] = [session_id]
    if limit:
        q += " DESC LIMIT ?"
        params.append(limit)
    rows = [_decode_turn(dict(r)) for r in conn.execute(q, params)]
    if limit:
        rows.reverse()
    return rows


def get_last_turn(conn: sqlite3.Connection, world_id: str, session_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM turns WHERE session_id = ? AND undone = 0 ORDER BY idx DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return _decode_turn(dict(row)) if row else None


def mark_turn_undone(conn: sqlite3.Connection, turn_id: str, commit: bool = True) -> None:
    conn.execute("UPDATE turns SET undone = 1 WHERE id = ?", (turn_id,))
    if commit:
        conn.commit()


def get_turn_raw(conn: sqlite3.Connection, turn_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone()


# ---------------------------------------------------------------------------
# Dice log
# ---------------------------------------------------------------------------

def log_dice(
    conn: sqlite3.Connection, expression: str, result: int, dice_list: list[dict],
    seed: Optional[int] = None, reason: str = "", who: str = "agent",
    world_id: Optional[str] = None,
) -> dict:
    entry_id = db.new_id("d_")
    ts = db.now()
    conn.execute(
        "INSERT INTO dice_log (id, world_id, expression, result, dice_json, seed, reason, who, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (entry_id, world_id, expression, result, db.dumps(dice_list), seed, reason, who, ts),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM dice_log WHERE id = ?", (entry_id,)).fetchone())
    row["dice"] = db.loads(row.pop("dice_json"), [])
    return row


def list_dice_log(conn: sqlite3.Connection, world_id: Optional[str] = None, limit: int = 20) -> list[dict]:
    if world_id:
        rows = conn.execute(
            "SELECT * FROM dice_log WHERE world_id = ? ORDER BY created_at DESC LIMIT ?", (world_id, limit)
        )
    else:
        rows = conn.execute("SELECT * FROM dice_log ORDER BY created_at DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        d = dict(r)
        d["dice"] = db.loads(d.pop("dice_json"), [])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Agent calls (audit trail — "what the assistant did")
# ---------------------------------------------------------------------------

def log_agent_call(
    conn: sqlite3.Connection, tool: str, args_summary: str, duration_ms: float,
    ok: bool, error: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO agent_calls (id, tool, args_summary, duration_ms, ok, error, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (db.new_id("ac_"), tool, args_summary[:500], duration_ms, int(ok), error, db.now()),
    )
    conn.commit()


def list_agent_calls(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute("SELECT * FROM agent_calls ORDER BY created_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Cross-entity search (world_search MCP tool)
# ---------------------------------------------------------------------------

def search_world(
    conn: sqlite3.Connection, world_id: str, query: str,
    kinds: Optional[list[str]] = None, limit: int = 8,
) -> dict:
    """Entities and facts matching `query`, best first.

    Returns `limit + 1` hits of each at most so the caller can tell whether
    there are more; `kinds` is applied in SQL, before the limit.
    """
    entity_hits: list[dict] = []
    for kind in kinds or []:
        validate_kind(kind)
    sql = (
        "SELECT entities.* FROM entities_fts JOIN entities ON entities.id = entities_fts.id"
        " WHERE entities_fts.world_id = ? AND entities_fts MATCH ?"
    )
    params: list[Any] = [world_id, _fts_query(query)]
    if kinds:
        sql += f" AND entities.kind IN ({','.join('?' * len(kinds))})"
        params.extend(kinds)
    sql += " ORDER BY bm25(entities_fts), entities.seq LIMIT ?"
    params.append(limit + 1)
    try:
        entity_hits = [_decode_entity(dict(r)) for r in conn.execute(sql, params)]
    except sqlite3.OperationalError:
        entity_hits = []
    fact_hits = search_facts(conn, world_id, query, limit=limit + 1)
    return {"entities": entity_hits, "facts": fact_hits}


# ---------------------------------------------------------------------------
# Low-level delete/restore helpers used by the delta engine's undo path
# ---------------------------------------------------------------------------

def delete_relation(conn: sqlite3.Connection, relation_id: str, commit: bool = True) -> None:
    conn.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
    if commit:
        conn.commit()


def delete_fact(conn: sqlite3.Connection, fact_id: str, commit: bool = True) -> None:
    conn.execute("DELETE FROM facts_fts WHERE id = ?", (fact_id,))
    conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    if commit:
        conn.commit()


def delete_timeline_event(conn: sqlite3.Connection, event_id: str, commit: bool = True) -> None:
    conn.execute("DELETE FROM timeline_events WHERE id = ?", (event_id,))
    if commit:
        conn.commit()


def restore_clock_filled(conn: sqlite3.Connection, clock_id: str, filled: int, commit: bool = True) -> None:
    conn.execute("UPDATE clocks SET filled = ? WHERE id = ?", (filled, clock_id))
    if commit:
        conn.commit()


def restore_thread_fields(conn: sqlite3.Connection, thread_id: str, status: str, notes: str, commit: bool = True) -> None:
    conn.execute("UPDATE threads SET status = ?, notes = ? WHERE id = ?", (status, notes, thread_id))
    if commit:
        conn.commit()


def restore_entity_row(conn: sqlite3.Connection, entity_id: str, prev: dict, commit: bool = True) -> None:
    """Restore an entity's mutable columns to a previously captured snapshot."""
    conn.execute(
        """UPDATE entities SET kind=?, name=?, aliases_json=?, summary=?, description=?,
           fields_json=?, secrets=?, status=?, tags_json=?, parent_id=?, images_json=?, updated_at=?
           WHERE id = ?""",
        (
            prev["kind"], prev["name"], db.dumps(prev["aliases"]), prev["summary"], prev["description"],
            db.dumps(prev["fields"]), prev["secrets"], prev["status"], db.dumps(prev["tags"]),
            prev["parent_id"], db.dumps(prev["images"]), db.now(), entity_id,
        ),
    )
    e = _decode_entity(dict(conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()))
    _fts_upsert_entity(conn, e)
    if commit:
        conn.commit()
