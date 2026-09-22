"""The delta schema: validated, atomic scene changes with reversal.

A delta is what a narrator proposes after a scene: new entities, patches to
existing ones, new established facts, relations, timeline events, thread
and clock changes, and an optional scene move. `validate_delta` checks it
against the current world state (unknown ids, dead characters acting,
moves to unknown locations, ...) without writing anything. `apply_delta`
applies only the valid items in one SQLite transaction and returns an undo
snapshot that `undo_delta` can use to put the world back exactly as it was.

No FastAPI imports; the API layer wraps this 1:1 for `/api/agent/story_append`
and `story_undo`, and the MCP adapter calls the same HTTP endpoints.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from . import store

DEAD_STATUSES = {"dead", "destroyed", "missing"}


class Rejected(dict):
    """A delta item that failed validation, with a human-readable reason."""


def _reject(category: str, item: Any, reason: str) -> dict:
    return {"category": category, "item": item, "reason": reason}


def _items(delta: dict, category: str, rejected: list[dict]) -> list[dict]:
    """The dict items of one delta section; anything else is rejected
    (a model will sometimes send a bare string or a single object)."""
    raw = delta.get(category) or []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        rejected.append(_reject(category, raw, f"{category} must be a list of objects"))
        return []
    out = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
        else:
            rejected.append(_reject(category, item, f"each {category} item must be an object"))
    return out


def _found(resolver, conn: sqlite3.Connection, world_id: str, ref: str) -> bool:
    try:
        resolver(conn, world_id, ref)
        return True
    except store.NotFound:
        return False


def _existing_entity(conn: sqlite3.Connection, world_id: str, names: list[str]) -> Optional[dict]:
    for n in names:
        if isinstance(n, str) and n.strip():
            try:
                return store.get_entity(conn, world_id, n)
            except store.NotFound:
                continue
    return None


def validate_delta(conn: sqlite3.Connection, world_id: str, delta: dict) -> tuple[dict, list[dict]]:
    """Split a raw delta into `{category: [valid items]}` and a rejected list.

    Resolution order matters: new_entities are validated/named first so
    later sections (relations, facts, scene) may refer to them by the name
    they will get, even though they do not exist yet.
    """
    delta = delta or {}
    valid: dict[str, list] = {
        "new_entities": [], "entity_updates": [], "new_facts": [], "relations": [],
        "timeline_events": [], "thread_changes": [], "clock_ticks": [], "scene": None,
    }
    rejected: list[dict] = []

    # Names promised by new_entities in this same delta, so relations/facts
    # in the same call can refer to them before they exist in the store.
    promised_names: set[str] = set()

    for item in _items(delta, "new_entities", rejected):
        kind = item.get("kind")
        name = (item.get("name") or "").strip()
        if kind not in store.VALID_KINDS:
            rejected.append(_reject("new_entities", item, f"unknown kind: {kind!r}"))
            continue
        if not name:
            rejected.append(_reject("new_entities", item, "missing name"))
            continue
        existing = _existing_entity(conn, world_id, [name, *(item.get("aliases") or [])])
        if existing:
            rejected.append(_reject(
                "new_entities", item,
                f"{existing['name']!r} already exists ({existing['ref']}); change it with entity_updates",
            ))
            continue
        if store._norm(name) in promised_names:
            rejected.append(_reject("new_entities", item, f"{name!r} appears twice in new_entities"))
            continue
        if item.get("status") is not None:
            try:
                item = {**item, "status": store.normalize_status(item["status"])}
            except ValueError as e:
                rejected.append(_reject("new_entities", item, str(e)))
                continue
        valid["new_entities"].append(item)
        promised_names.add(store._norm(name))

    def entity_known(ref: str) -> bool:
        if not ref or not isinstance(ref, str):
            return False
        if store._norm(ref) in promised_names:
            return True
        try:
            store.resolve_entity_id(conn, world_id, ref)
            return True
        except store.NotFound:
            return False

    for item in _items(delta, "entity_updates", rejected):
        ref = item.get("ref")
        if not entity_known(ref):
            rejected.append(_reject("entity_updates", item, f"unknown entity: {ref!r}"))
            continue
        try:
            if item.get("status") is not None:
                item = {**item, "status": store.normalize_status(item["status"])}
            if item.get("kind") is not None:
                store.validate_kind(item["kind"])
        except ValueError as e:
            rejected.append(_reject("entity_updates", item, str(e)))
            continue
        new_name = item.get("name")
        if new_name is not None:
            clash = _existing_entity(conn, world_id, [new_name]) if isinstance(new_name, str) else None
            target = _existing_entity(conn, world_id, [ref])
            if not isinstance(new_name, str) or not new_name.strip() or (clash and target and clash["id"] != target["id"]):
                rejected.append(_reject("entity_updates", item, f"cannot rename to {new_name!r}: empty or already used"))
                continue
        valid["entity_updates"].append(item)

    for item in _items(delta, "relations", rejected):
        a, b = item.get("a"), item.get("b")
        if not entity_known(a) or not entity_known(b):
            bad = a if not entity_known(a) else b
            rejected.append(_reject("relations", item, f"unknown entity: {bad!r}"))
            continue
        if not item.get("type"):
            rejected.append(_reject("relations", item, "missing relation type"))
            continue
        valid["relations"].append(item)

    for item in _items(delta, "new_facts", rejected):
        if not (item.get("text") or "").strip():
            rejected.append(_reject("new_facts", item, "missing text"))
            continue
        bad_refs = [r for r in (item.get("entity_ids") or []) if not entity_known(r)]
        if bad_refs:
            rejected.append(_reject("new_facts", item, f"unknown entity ids: {bad_refs}"))
            continue
        valid["new_facts"].append(item)

    for item in _items(delta, "timeline_events", rejected):
        if not (item.get("summary") or "").strip():
            rejected.append(_reject("timeline_events", item, "missing summary"))
            continue
        bad_refs = [r for r in (item.get("entity_ids") or []) if not entity_known(r)]
        if bad_refs:
            rejected.append(_reject("timeline_events", item, f"unknown entity ids: {bad_refs}"))
            continue
        valid["timeline_events"].append(item)

    for item in _items(delta, "thread_changes", rejected):
        ref = item.get("ref")
        status = item.get("status")
        if status is not None and status not in store.VALID_THREAD_STATUS:
            rejected.append(_reject("thread_changes", item, f"unknown thread status: {status!r}; use one of "
                                    + ", ".join(sorted(store.VALID_THREAD_STATUS))))
            continue
        if isinstance(ref, str) and _found(store.resolve_thread_id, conn, world_id, ref):
            valid["thread_changes"].append(item)
        elif item.get("create") and isinstance(item.get("title") or ref, str) and (item.get("title") or ref).strip():
            valid["thread_changes"].append({**item, "ref": ref or item["title"]})
        else:
            rejected.append(_reject("thread_changes", item, f"unknown thread: {ref!r} (to open one, pass create: true and a title)"))

    for item in _items(delta, "clock_ticks", rejected):
        ref = item.get("ref")
        ticks = item.get("ticks", 1)
        if isinstance(ticks, bool) or not isinstance(ticks, int):
            rejected.append(_reject("clock_ticks", item, f"ticks must be a whole number, got {ticks!r}"))
            continue
        if isinstance(ref, str) and _found(store.resolve_clock_id, conn, world_id, ref):
            valid["clock_ticks"].append(item)
        else:
            rejected.append(_reject("clock_ticks", item, f"unknown clock: {ref!r}"))

    scene = delta.get("scene")
    if scene and not isinstance(scene, dict):
        rejected.append(_reject("scene", scene, "scene must be an object {location, present, mood}"))
        scene = None
    if scene:
        location_ref = scene.get("location")
        location_ok = True
        if location_ref:
            try:
                loc = store.get_entity(conn, world_id, location_ref)
                if loc["kind"] != "location":
                    location_ok = False
            except store.NotFound:
                location_ok = False
        if location_ref and not location_ok:
            rejected.append(_reject("scene", scene, f"unknown or non-location: {location_ref!r}"))
        else:
            present_raw = scene.get("present") or []
            present_ok: list[str] = []
            for ref in present_raw:
                if not isinstance(ref, str):
                    rejected.append(_reject("scene.present", ref, "present entries must be entity refs or names"))
                    continue
                if store._norm(ref) in promised_names:
                    present_ok.append(ref)
                    continue
                try:
                    e = store.get_entity(conn, world_id, ref)
                except store.NotFound:
                    rejected.append(_reject("scene.present", ref, f"unknown entity: {ref!r}"))
                    continue
                if e["status"] in DEAD_STATUSES:
                    rejected.append(_reject("scene.present", ref, f"{e['name']} is {e['status']} and cannot act"))
                    continue
                present_ok.append(ref)
            # Only the keys the narrator actually sent: a scene that only
            # changes the mood must not empty the location or the cast.
            valid["scene"] = {k: v for k, v in scene.items() if k in ("location", "present", "mood")}
            if "present" in scene:
                if present_raw and not present_ok:
                    # Every name given was rejected (unknown, dead, ...): treat
                    # this as no change to `present` rather than as an explicit
                    # "nobody is here" — one bad name must not empty a scene
                    # whose existing cast was never actually mentioned.
                    valid["scene"].pop("present", None)
                else:
                    valid["scene"]["present"] = present_ok

    return valid, rejected


def apply_delta(
    conn: sqlite3.Connection, world_id: str, session_id: str, valid: dict,
) -> tuple[dict, dict]:
    """Apply an already-validated delta atomically. Returns (result_summary, undo_snapshot)."""
    try:
        conn.execute("SAVEPOINT apply_delta")
        result, undo = _apply(conn, world_id, session_id, valid)
        conn.execute("RELEASE apply_delta")
        conn.commit()
    except Exception:
        conn.execute("ROLLBACK TO apply_delta")
        conn.commit()
        raise
    return result, undo


def record_turn(
    conn: sqlite3.Connection, world_id: str, session_id: str, raw_delta: Optional[dict],
    role: str, author: str, text: str = "", rolls: Optional[list] = None,
) -> tuple[dict, dict, list[dict]]:
    """Validate a delta, apply it and append the turn that carries it, in
    ONE transaction: either the world changes and the (undoable) turn
    exists, or nothing happened. The turn's scene is the previous scene
    with this delta's changes merged in, minus anyone who is now dead.

    Returns (turn, applied_result, rejected_items).
    """
    store.validate_turn(role, author)
    valid, rejected = validate_delta(conn, world_id, raw_delta or {})
    try:
        conn.execute("SAVEPOINT record_turn")
        result, undo = _apply(conn, world_id, session_id, valid)
        scene = next_scene(conn, world_id, store.current_scene(conn, world_id), result.get("scene"))
        turn = store.append_turn(
            conn, world_id, session_id, role, author, text=text, rolls=rolls or [], scene=scene,
            delta=result, applied=True, undo_snapshot=undo, commit=False,
        )
        conn.execute("RELEASE record_turn")
        conn.commit()
    except Exception:
        conn.execute("ROLLBACK TO record_turn")
        conn.commit()
        raise
    return turn, result, rejected


def next_scene(conn: sqlite3.Connection, world_id: str, prev: Optional[dict], change: Optional[dict]) -> dict:
    scene = {"location": None, "present": [], "mood": ""}
    scene.update({k: v for k, v in (prev or {}).items() if k in scene})
    scene.update(change or {})
    alive: list[str] = []
    for ref in scene.get("present") or []:
        try:
            e = store.get_entity(conn, world_id, ref)
        except store.NotFound:
            continue
        if e["status"] not in DEAD_STATUSES and e["id"] not in alive:
            alive.append(e["id"])
    scene["present"] = alive
    return scene


def _apply(conn: sqlite3.Connection, world_id: str, session_id: str, valid: dict) -> tuple[dict, dict]:
    undo: dict[str, Any] = {
        "created_entities": [], "updated_entities": [], "created_relations": [],
        "created_facts": [], "created_timeline_events": [], "updated_threads": [],
        "created_threads": [], "updated_clocks": [],
    }
    result: dict[str, Any] = {
        "created_entities": [], "updated_entities": [], "new_facts": [],
        "relations": [], "timeline_events": [], "thread_changes": [], "clock_ticks": [],
    }
    name_to_id: dict[str, str] = {}

    for item in valid["new_entities"]:
        e = store.create_entity(
            conn, world_id, item["kind"], item["name"].strip(),
            aliases=item.get("aliases"), summary=item.get("summary", ""),
            description=item.get("description", ""), fields=item.get("fields"),
            secrets=item.get("secrets", ""), status=item.get("status", "alive"),
            tags=item.get("tags"), parent_id=item.get("parent_id"),
            commit=False,
        )
        name_to_id[store._norm(item["name"])] = e["id"]
        undo["created_entities"].append(e["id"])
        result["created_entities"].append(e)

    def resolve_ref(ref: str) -> str:
        key = store._norm(ref)
        if key in name_to_id:
            return name_to_id[key]
        return store.resolve_entity_id(conn, world_id, ref)

    for item in valid["entity_updates"]:
        entity_id = resolve_ref(item["ref"])
        prev = store.get_entity(conn, world_id, entity_id)
        patch = {k: v for k, v in item.items() if k != "ref"}
        if isinstance(patch.get("fields"), dict):
            # a delta patches stats/traits; it never wipes the ones it omits
            patch["fields_patch"] = patch.pop("fields")
        updated = store.update_entity(conn, world_id, entity_id, commit=False, **patch)
        undo["updated_entities"].append({"id": entity_id, "prev": prev})
        result["updated_entities"].append(updated)

    for item in valid["relations"]:
        rel = store.create_relation(
            conn, world_id, resolve_ref(item["a"]), resolve_ref(item["b"]),
            item["type"], note=item.get("note", ""), since=item.get("since", ""), commit=False,
        )
        undo["created_relations"].append(rel["id"])
        result["relations"].append(rel)

    for item in valid["new_facts"]:
        entity_ids = [resolve_ref(r) for r in (item.get("entity_ids") or [])]
        fact = store.create_fact(
            conn, world_id, item["text"], session_id=session_id,
            entity_ids=entity_ids, canon=bool(item.get("canon", False)), commit=False,
        )
        undo["created_facts"].append(fact["id"])
        result["new_facts"].append(fact)

    for item in valid["timeline_events"]:
        entity_ids = [resolve_ref(r) for r in (item.get("entity_ids") or [])]
        ev = store.create_timeline_event(
            conn, world_id, item.get("in_world_date", ""), item["summary"],
            entity_ids=entity_ids, session_id=session_id, commit=False,
        )
        undo["created_timeline_events"].append(ev["id"])
        result["timeline_events"].append(ev)

    for item in valid["thread_changes"]:
        try:
            thread_id = store.resolve_thread_id(conn, world_id, item["ref"])
            prev = store.get_thread(conn, world_id, thread_id)
            updated = store.update_thread(
                conn, world_id, thread_id, status=item.get("status"), note=item.get("note"), commit=False,
            )
            undo["updated_threads"].append({"id": thread_id, "prev_status": prev["status"], "prev_notes": prev["notes"]})
            result["thread_changes"].append(updated)
        except store.NotFound:
            th = store.create_thread(
                conn, world_id, item.get("title") or item["ref"],
                status=item.get("status", "open"), notes=item.get("note", ""),
                commit=False,
            )
            undo["created_threads"].append(th["id"])
            result["thread_changes"].append(th)

    for item in valid["clock_ticks"]:
        clock_id = store.resolve_clock_id(conn, world_id, item["ref"])
        prev = store.get_clock(conn, world_id, clock_id)
        updated = store.tick_clock(conn, world_id, clock_id, item.get("ticks", 1), commit=False)
        undo["updated_clocks"].append({"id": clock_id, "prev_filled": prev["filled"]})
        result["clock_ticks"].append(updated)

    if valid.get("scene"):
        given = valid["scene"]
        scene_change: dict[str, Any] = {}
        if "location" in given:
            scene_change["location"] = resolve_ref(given["location"]) if given["location"] else None
        if "present" in given:
            scene_change["present"] = [resolve_ref(r) for r in given["present"] or []]
        if "mood" in given:
            scene_change["mood"] = given["mood"] or ""
        result["scene"] = scene_change

    return result, undo


def undo_last(conn: sqlite3.Connection, world_id: str, turn: dict) -> None:
    """Reverse the effects recorded in a turn's undo snapshot, then mark it undone."""
    snapshot_row = store.get_turn_raw(conn, turn["id"])
    if snapshot_row is None:
        raise store.NotFound(f"no such turn: {turn['id']!r}")
    from . import db as _db  # local import to avoid a cycle at module load time
    snapshot = _db.loads(snapshot_row["undo_snapshot_json"], None)
    try:
        conn.execute("SAVEPOINT undo_delta")
        if snapshot:
            for entity_id in snapshot.get("created_entities", []):
                store.delete_entity(conn, entity_id, commit=False)
            # Restore newest-first: when one delta touched the same entity,
            # thread or clock twice, only the oldest snapshot is the original.
            for item in reversed(snapshot.get("updated_entities", [])):
                store.restore_entity_row(conn, item["id"], item["prev"], commit=False)
            for rel_id in snapshot.get("created_relations", []):
                store.delete_relation(conn, rel_id, commit=False)
            for fact_id in snapshot.get("created_facts", []):
                store.delete_fact(conn, fact_id, commit=False)
            for ev_id in snapshot.get("created_timeline_events", []):
                store.delete_timeline_event(conn, ev_id, commit=False)
            for th_id in snapshot.get("created_threads", []):
                conn.execute("DELETE FROM threads WHERE id = ?", (th_id,))
            for item in reversed(snapshot.get("updated_threads", [])):
                store.restore_thread_fields(conn, item["id"], item["prev_status"], item["prev_notes"], commit=False)
            for item in reversed(snapshot.get("updated_clocks", [])):
                store.restore_clock_filled(conn, item["id"], item["prev_filled"], commit=False)
        store.mark_turn_undone(conn, turn["id"], commit=False)
        conn.execute("RELEASE undo_delta")
        conn.commit()
    except Exception:
        conn.execute("ROLLBACK TO undo_delta")
        conn.commit()
        raise
