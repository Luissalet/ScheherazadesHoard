"""hoard.world/1: a world's cast, places, factions, relations and timeline as neutral JSON.

Another app (Writer's codex, for one) can read it and write it. Export never carries
secrets, images, facts, threads, clocks, sessions or dice. Import is idempotent and
never deletes: every record is keyed by its `ref` and its `revision`, a record that
was edited here after it was imported is never overwritten, and a name that already
exists is linked, not duplicated. The format is described in docs/WORLD_SCHEMA.md.

Pure data logic: no FastAPI here.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Optional

from . import db, store

SCHEMA = "hoard.world/1"
OWN = "hoard://scheherazade/"

MAX_ITEMS = 5000
CLIP = {"name": 200, "summary": 2000, "description": 20000, "type": 120, "note": 2000, "since": 200, "date": 200,
        "alias": 200, "tag": 80, "field_key": 120, "field_value": 4000}
SECTION_KIND = {"characters": "character", "places": "location", "factions": "faction"}
THING_KINDS = ("item", "lore", "creature")
# What other apps call things that Scheherazade files as lore.
THING_ALIASES = {"concept": "lore", "magic": "lore", "custom": "lore", "object": "item", "monster": "creature"}


def ref_world(world_id: str) -> str:
    return f"{OWN}world/{world_id}"


def ref_entity(entity_id: str) -> str:
    return f"{OWN}entity/{entity_id}"


def ref_relation(relation_id: str) -> str:
    return f"{OWN}relation/{relation_id}"


def ref_event(event_id: str) -> str:
    return f"{OWN}event/{event_id}"


def digest(value: Any) -> str:
    """A stable `sha256:` revision of any JSON-able value (keys sorted, UTF-8)."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _clip(value: Any, key: str) -> str:
    return str(value if value is not None else "").strip()[: CLIP[key]]


def _text_fields(raw: Any) -> dict[str, str]:
    """Free-form fields as a flat string map: scalars as text, nested values as compact JSON."""
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            name = _clip(key, "field_key")
            if not name or value is None:
                continue
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":")) \
                if isinstance(value, (dict, list)) else str(value)
            out[name] = text[: CLIP["field_value"]]
    return out


def _strings(raw: Any, key: str) -> list[str]:
    items = raw if isinstance(raw, list) else []
    out: list[str] = []
    for item in items:
        text = _clip(item, key)
        if text and text not in out:
            out.append(text)
    return out


def entity_content(e: dict[str, Any]) -> dict[str, Any]:
    """The part of an entity that is exchanged (and hashed): never the secrets, never the images."""
    return {"kind": e["kind"], "name": e["name"], "aliases": list(e.get("aliases") or []), "summary": e.get("summary") or "",
            "description": e.get("description") or "", "status": e.get("status") or "unknown",
            "tags": list(e.get("tags") or []), "fields": _text_fields(e.get("fields"))}


def local_entity_hash(e: dict[str, Any]) -> str:
    return digest(entity_content(e))


def local_relation_hash(r: dict[str, Any]) -> str:
    return digest({"type": r.get("type") or "", "note": r.get("note") or "", "since": r.get("since") or ""})


def local_event_hash(ev: dict[str, Any]) -> str:
    return digest({"date": ev.get("in_world_date") or "", "summary": ev.get("summary") or "", "entity_ids": sorted(ev.get("entity_ids") or [])})


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _same_as(conn: sqlite3.Connection, world_id: str, kind: str, local_id: str) -> list[str]:
    return [link["ref"] for link in store.links_for_local(conn, world_id, kind, local_id) if not link["ref"].startswith(OWN)]


def export_world(conn: sqlite3.Connection, world_id: str) -> dict[str, Any]:
    """The world as a hoard.world/1 document (see docs/WORLD_SCHEMA.md)."""
    world = store.get_world(conn, world_id)
    entities = store.list_entities(conn, world_id, limit=100000)
    by_id = {e["id"]: e for e in entities}
    doc: dict[str, Any] = {"characters": [], "places": [], "factions": [], "things": [], "relations": [], "events": []}

    for e in entities:
        content = entity_content(e)
        item: dict[str, Any] = {"ref": ref_entity(e["id"]), "name": content["name"], "aliases": content["aliases"],
                                "summary": content["summary"], "description": content["description"], "status": content["status"],
                                "tags": content["tags"], "fields": content["fields"]}
        parent = by_id.get(e.get("parent_id") or "")
        if parent:
            item["parent_ref"] = ref_entity(parent["id"])
        same = _same_as(conn, world_id, "entity", e["id"])
        if same:
            item["same_as"] = same
        section = {"character": "characters", "location": "places", "faction": "factions"}.get(e["kind"], "things")
        if section == "things":
            item["kind"] = e["kind"]
        item["revision"] = digest({k: v for k, v in item.items() if k not in ("ref", "same_as")})
        doc[section].append(item)

    for r in store.list_relations(conn, world_id):
        if r["a_id"] not in by_id or r["b_id"] not in by_id:
            continue
        item = {"ref": ref_relation(r["id"]), "from": ref_entity(r["a_id"]), "to": ref_entity(r["b_id"]), "type": r["type"],
                "note": r.get("note") or "", "since": r.get("since") or ""}
        same = _same_as(conn, world_id, "relation", r["id"])
        if same:
            item["same_as"] = same
        item["revision"] = digest({k: v for k, v in item.items() if k not in ("ref", "same_as")})
        doc["relations"].append(item)

    for ev in store.list_timeline(conn, world_id, limit=100000):
        item = {"ref": ref_event(ev["id"]), "date": ev.get("in_world_date") or "", "summary": ev["summary"],
                "entities": [ref_entity(i) for i in ev.get("entity_ids") or [] if i in by_id]}
        same = _same_as(conn, world_id, "event", ev["id"])
        if same:
            item["same_as"] = same
        item["revision"] = digest({k: v for k, v in item.items() if k not in ("ref", "same_as")})
        doc["events"].append(item)

    body = {"world": {"name": world["name"], "genre": world["genre"], "tone": world["tone"], "premise": world["premise"],
                      "language": world["language"]}, **doc}
    source = {"app": "scheherazade", "ref": ref_world(world_id), "revision": digest(body), "exported_at": db.now()}
    return {"schema": SCHEMA, "source": source, **body}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

class WorldDocumentError(ValueError):
    """The document is not a usable hoard.world/1."""


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise WorldDocumentError(f"not a {SCHEMA} document: expected an object with schema {SCHEMA!r}")
    total = 0
    for key in ("characters", "places", "factions", "things", "relations", "events"):
        value = data.get(key, [])
        if not isinstance(value, list):
            raise WorldDocumentError(f"{key!r} must be a list")
        total += len(value)
    if total > MAX_ITEMS:
        raise WorldDocumentError(f"too many records ({total}); at most {MAX_ITEMS} per document")
    world = data.get("world")
    if world is not None and not isinstance(world, dict):
        raise WorldDocumentError("'world' must be an object")
    return data


def _ref_ok(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("hoard://") and len(value) <= 300 and value.count("/") >= 3


def _same_refs(item: dict[str, Any]) -> list[str]:
    return [r for r in (item.get("same_as") or []) if _ref_ok(r)] if isinstance(item.get("same_as"), list) else []


class _Report:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, section: str, item: dict[str, Any], state: str, local_id: Optional[str] = None, reason: str = "") -> None:
        entry: dict[str, Any] = {"section": section, "ref": item.get("ref") if isinstance(item, dict) else None,
                                 "name": (item.get("name") or item.get("summary") or item.get("type") or "")[:80] if isinstance(item, dict) else "",
                                 "state": state}
        if local_id:
            entry["id"] = local_id
        if reason:
            entry["reason"] = reason
        self.items.append(entry)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for entry in self.items:
            out[entry["state"]] = out.get(entry["state"], 0) + 1
        return out


def _own_id(ref: str, kind: str) -> Optional[str]:
    prefix = f"{OWN}{kind}/"
    return ref[len(prefix):] if ref.startswith(prefix) else None


def _find_record(conn: sqlite3.Connection, world_id: str, kind: str, refs: list[str]) -> tuple[Optional[dict], Optional[str]]:
    """The local row a ref (or one of its same_as refs) already stands for.

    Returns (link or None, local id or None): a stored link wins; otherwise a ref in this app's own namespace
    that names a row of this world."""
    for ref in refs:
        link = store.get_link(conn, world_id, ref)
        if link and link["kind"] == kind:
            return link, link["local_id"]
    for ref in refs:
        local_id = _own_id(ref, kind)
        if not local_id:
            continue
        if kind == "entity":
            row = conn.execute("SELECT id FROM entities WHERE id = ? AND world_id = ?", (local_id, world_id)).fetchone()
        elif kind == "relation":
            row = conn.execute("SELECT id FROM relations WHERE id = ? AND world_id = ?", (local_id, world_id)).fetchone()
        else:
            row = conn.execute("SELECT id FROM timeline_events WHERE id = ? AND world_id = ?", (local_id, world_id)).fetchone()
        if row:
            return None, row["id"]
    return None, None


def _entity_exists(conn: sqlite3.Connection, world_id: str, entity_id: str) -> bool:
    return conn.execute("SELECT 1 FROM entities WHERE id = ? AND world_id = ?", (entity_id, world_id)).fetchone() is not None


def _incoming_entity(item: dict[str, Any], kind: str) -> dict[str, Any]:
    status = _clip(item.get("status") or "alive", "type")
    try:
        status = store.normalize_status(status)
    except ValueError:
        status = "unknown"
    return {"kind": kind, "name": _clip(item.get("name"), "name"), "aliases": _strings(item.get("aliases"), "alias"),
            "summary": _clip(item.get("summary"), "summary"), "description": _clip(item.get("description"), "description"),
            "status": status, "tags": _strings(item.get("tags"), "tag"), "fields": _text_fields(item.get("fields"))}


def _thing_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "").strip().lower()
    kind = THING_ALIASES.get(kind, kind)
    return kind if kind in THING_KINDS else "lore"


def _import_entity(conn, world_id: str, section: str, item: dict[str, Any], kind: str, ref_map: dict[str, str], report: _Report) -> None:
    ref = item.get("ref")
    if not _ref_ok(ref):
        return report.add(section, item, "skipped", reason="bad_ref")
    incoming = _incoming_entity(item, kind)
    if not incoming["name"]:
        return report.add(section, item, "skipped", reason="no_name")
    revision = str(item.get("revision") or digest(incoming))[:200]
    refs = [ref, *_same_refs(item)]

    link, local_id = _find_record(conn, world_id, "entity", refs)
    if local_id and not _entity_exists(conn, world_id, local_id):
        return report.add(section, item, "skipped", reason="deleted_locally")  # deleted here: never resurrected
    if local_id:
        for r in refs:
            ref_map[r] = local_id
        local = store.get_entity(conn, world_id, local_id)
        if not link:
            return report.add(section, item, "own", local_id)  # a record of this very world coming back
        if link["source_revision"] == revision and link["ref"] == ref:
            return report.add(section, item, "unchanged", local_id)
        if local_entity_hash(local) != link["local_hash"]:
            return report.add(section, item, "local_modified", local_id,
                              "edited here after it was imported; compare before changing it")
        updated = store.update_entity(conn, world_id, local_id, commit=False, name=incoming["name"], aliases=incoming["aliases"],
                                      summary=incoming["summary"], description=incoming["description"], status=incoming["status"],
                                      tags=incoming["tags"], fields=incoming["fields"])
        for r in refs:
            store.put_link(conn, world_id, r, "entity", local_id, revision, local_entity_hash(updated), commit=False)
        return report.add(section, item, "updated", local_id)

    try:
        existing = store.get_entity(conn, world_id, incoming["name"], loose=False)
    except store.NotFound:
        existing = None
    if existing:
        if existing["kind"] != kind:
            return report.add(section, item, "name_collision", existing["id"],
                              f"{existing['name']!r} already exists here as a {existing['kind']}")
        for r in refs:
            ref_map[r] = existing["id"]
            # Hash of what the source sent, not of our row: if they differ, our version counts as edited and is never overwritten.
            store.put_link(conn, world_id, r, "entity", existing["id"], revision, digest(incoming), commit=False)
        return report.add(section, item, "linked_existing", existing["id"])

    created = store.create_entity(conn, world_id, kind, incoming["name"], aliases=incoming["aliases"], summary=incoming["summary"],
                                  description=incoming["description"], fields=incoming["fields"], status=incoming["status"],
                                  tags=incoming["tags"], commit=False)
    for r in refs:
        ref_map[r] = created["id"]
        store.put_link(conn, world_id, r, "entity", created["id"], revision, local_entity_hash(created), commit=False)
    report.add(section, item, "created", created["id"])


def _resolve_entity(conn, world_id: str, ref: Any, ref_map: dict[str, str]) -> Optional[str]:
    if not _ref_ok(ref):
        return None
    if ref in ref_map:
        return ref_map[ref]
    _, local_id = _find_record(conn, world_id, "entity", [ref])
    return local_id if local_id and _entity_exists(conn, world_id, local_id) else None


def _import_relation(conn, world_id: str, item: dict[str, Any], ref_map: dict[str, str], report: _Report) -> None:
    ref = item.get("ref")
    if not _ref_ok(ref):
        return report.add("relations", item, "skipped", reason="bad_ref")
    a = _resolve_entity(conn, world_id, item.get("from"), ref_map)
    b = _resolve_entity(conn, world_id, item.get("to"), ref_map)
    type_ = _clip(item.get("type"), "type")
    if not a or not b or a == b or not type_:
        return report.add("relations", item, "skipped", reason="endpoint_missing" if not (a and b) else "invalid")
    incoming = {"type": type_, "note": _clip(item.get("note"), "note"), "since": _clip(item.get("since"), "since")}
    revision = str(item.get("revision") or digest(incoming))[:200]
    refs = [ref, *_same_refs(item)]
    link, local_id = _find_record(conn, world_id, "relation", refs)
    if local_id and not store.get_relation(conn, local_id):
        return report.add("relations", item, "skipped", reason="deleted_locally")
    if local_id:
        local = store.get_relation(conn, local_id)
        if not link:
            return report.add("relations", item, "own", local_id)
        if link["source_revision"] == revision and link["ref"] == ref:
            return report.add("relations", item, "unchanged", local_id)
        if local_relation_hash(local) != link["local_hash"]:
            return report.add("relations", item, "local_modified", local_id, "edited here after it was imported")
        updated = store.update_relation(conn, local_id, commit=False, **incoming)
        for r in refs:
            store.put_link(conn, world_id, r, "relation", local_id, revision, local_relation_hash(updated), commit=False)
        return report.add("relations", item, "updated", local_id)
    twin = conn.execute("SELECT id FROM relations WHERE world_id = ? AND a_id = ? AND b_id = ? AND type = ?",
                        (world_id, a, b, type_)).fetchone()
    if twin:
        for r in refs:
            store.put_link(conn, world_id, r, "relation", twin["id"], revision, digest(incoming), commit=False)
        return report.add("relations", item, "linked_existing", twin["id"])
    created = store.create_relation(conn, world_id, a, b, type_, note=incoming["note"], since=incoming["since"], commit=False)
    for r in refs:
        store.put_link(conn, world_id, r, "relation", created["id"], revision, local_relation_hash(created), commit=False)
    report.add("relations", item, "created", created["id"])


def _import_event(conn, world_id: str, item: dict[str, Any], ref_map: dict[str, str], report: _Report) -> None:
    ref = item.get("ref")
    if not _ref_ok(ref):
        return report.add("events", item, "skipped", reason="bad_ref")
    summary = _clip(item.get("summary"), "summary")
    if not summary:
        return report.add("events", item, "skipped", reason="no_summary")
    entity_ids = []
    for r in item.get("entities") or []:
        local = _resolve_entity(conn, world_id, r, ref_map)
        if local and local not in entity_ids:
            entity_ids.append(local)
    incoming = {"in_world_date": _clip(item.get("date"), "date"), "summary": summary, "entity_ids": entity_ids}
    revision = str(item.get("revision") or digest(incoming))[:200]
    refs = [ref, *_same_refs(item)]
    link, local_id = _find_record(conn, world_id, "event", refs)
    if local_id and not store.get_timeline_event(conn, local_id):
        return report.add("events", item, "skipped", reason="deleted_locally")
    if local_id:
        local = store.get_timeline_event(conn, local_id)
        if not link:
            return report.add("events", item, "own", local_id)
        if link["source_revision"] == revision and link["ref"] == ref:
            return report.add("events", item, "unchanged", local_id)
        if local_event_hash(local) != link["local_hash"]:
            return report.add("events", item, "local_modified", local_id, "edited here after it was imported")
        updated = store.update_timeline_event(conn, local_id, commit=False, **incoming)
        for r in refs:
            store.put_link(conn, world_id, r, "event", local_id, revision, local_event_hash(updated), commit=False)
        return report.add("events", item, "updated", local_id)
    twin = conn.execute("SELECT id FROM timeline_events WHERE world_id = ? AND in_world_date = ? AND summary = ?",
                        (world_id, incoming["in_world_date"], summary)).fetchone()
    if twin:
        for r in refs:
            store.put_link(conn, world_id, r, "event", twin["id"], revision, digest({"date": incoming["in_world_date"], "summary": summary, "entity_ids": sorted(entity_ids)}), commit=False)
        return report.add("events", item, "linked_existing", twin["id"])
    created = store.create_timeline_event(conn, world_id, incoming["in_world_date"], summary, entity_ids=entity_ids, commit=False)
    for r in refs:
        store.put_link(conn, world_id, r, "event", created["id"], revision, local_event_hash(created), commit=False)
    report.add("events", item, "created", created["id"])


def _target_world(conn, data: dict[str, Any], world_id: Optional[str]) -> tuple[str, bool]:
    """The world to import into and whether it was just created."""
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    source_ref = source.get("ref") if _ref_ok(source.get("ref")) else None
    if world_id:
        return store.resolve_world_id(conn, world_id), False
    if source_ref:
        known = store.world_for_link(conn, source_ref)
        if known and store.find_world_id(conn, known):
            return known, False
    meta = data.get("world") if isinstance(data.get("world"), dict) else {}
    name = _clip(meta.get("name"), "name") or "Imported world"
    unique, n = name, 1
    while store.find_world_id(conn, unique):
        n += 1
        unique = f"{name} ({n})"
    language = meta.get("language") if meta.get("language") in ("es", "en") else "es"
    created = store.create_world(conn, unique, genre=_clip(meta.get("genre"), "name"), tone=_clip(meta.get("tone"), "summary"),
                                 premise=_clip(meta.get("premise"), "description"), language=language)
    return created["id"], True


def import_world(conn: sqlite3.Connection, data: Any, world_id: Optional[str] = None) -> dict[str, Any]:
    """Merge a hoard.world/1 document into a world (a new one when `world_id` is omitted and the
    document was not imported before). Never deletes; never overwrites what was edited here.

    The whole import is one transaction. Returns the world, per-state counts and one entry per record."""
    validate(data)
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    source_ref = source.get("ref") if _ref_ok(source.get("ref")) else None
    report = _Report()
    ref_map: dict[str, str] = {}
    target, created_world = "", False
    try:
        target, created_world = _target_world(conn, data, world_id)
        if source_ref and not store.get_link(conn, target, source_ref):
            store.put_link(conn, target, source_ref, "world", target, str(source.get("revision") or "")[:200], "", commit=False)
        parents: list[tuple[str, str]] = []
        for section, kind in SECTION_KIND.items():
            for item in data.get(section) or []:
                if isinstance(item, dict):
                    _import_entity(conn, target, section, item, kind, ref_map, report)
                    if item.get("parent_ref") and report.items and report.items[-1].get("state") == "created":
                        parents.append((report.items[-1]["id"], item["parent_ref"]))
        for item in data.get("things") or []:
            if isinstance(item, dict):
                _import_entity(conn, target, "things", item, _thing_kind(item), ref_map, report)
                if item.get("parent_ref") and report.items and report.items[-1].get("state") == "created":
                    parents.append((report.items[-1]["id"], item["parent_ref"]))
        for child_id, parent_ref in parents:
            parent_id = _resolve_entity(conn, target, parent_ref, ref_map)
            if parent_id and parent_id != child_id:
                store.update_entity(conn, target, child_id, commit=False, parent_id=parent_id)
        for item in data.get("relations") or []:
            if isinstance(item, dict):
                _import_relation(conn, target, item, ref_map, report)
        for item in data.get("events") or []:
            if isinstance(item, dict):
                _import_event(conn, target, item, ref_map, report)
        conn.commit()
    except Exception:
        conn.rollback()
        if created_world and target:  # create_world commits on its own: take the empty world back
            conn.execute("DELETE FROM worlds WHERE id = ?", (target,))
            conn.commit()
        raise
    world = store.get_world(conn, target)
    return {"world": {"id": world["id"], "name": world["name"]}, "world_created": created_world, "counts": report.counts(),
            "items": report.items, "source_ref": source_ref, "world_ref": ref_world(target)}
