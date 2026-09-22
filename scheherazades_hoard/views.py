"""Compact, secret-free shapes for what the agent tools return.

The consumer of `/api/agent/*` is a local model with a finite context, so
tool results carry the stable ids it can pass back (`E3`, `F12`, `T2`,
`C1`, internal ids) and short text, never raw database rows, timestamps
or GM secrets it did not ask for. The UI keeps using the richer REST
endpoints. No FastAPI imports.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from . import store

SUMMARY_CHARS = 200
TEXT_CHARS = 300


def clip(text: Optional[str], n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def entity_brief(e: dict) -> dict:
    return {
        "id": e["id"], "ref": e["ref"], "kind": e["kind"], "name": e["name"],
        "status": e["status"], "summary": clip(e.get("summary"), SUMMARY_CHARS),
    }


def fact_brief(f: dict) -> dict:
    return {"id": f["id"], "ref": f["ref"], "text": clip(f["text"], TEXT_CHARS), "canon": f["canon"]}


def thread_brief(t: dict) -> dict:
    return {"id": t["id"], "ref": t["ref"], "title": t["title"], "status": t["status"],
            "notes": clip(t.get("notes"), TEXT_CHARS)}


def clock_brief(c: dict) -> dict:
    return {"id": c["id"], "ref": c["ref"], "name": c["name"], "filled": c["filled"],
            "segments": c["segments"], "full": c["full"], "on_full": clip(c.get("on_full"), TEXT_CHARS)}


def relation_view(conn, world_id: str, rel: dict, entity_id: str) -> dict:
    """A relation as seen from `entity_id`: the other side by ref and name."""
    outgoing = rel["a_id"] == entity_id
    other_id = rel["b_id"] if outgoing else rel["a_id"]
    try:
        other = store.get_entity(conn, world_id, other_id)
        other_ref, other_name = other["ref"], other["name"]
    except store.NotFound:
        other_ref, other_name = None, "(deleted)"
    return {
        "id": rel["id"], "type": rel["type"], "direction": "out" if outgoing else "in",
        "other_id": other_id, "other_ref": other_ref, "other_name": other_name,
        "note": clip(rel.get("note"), SUMMARY_CHARS), "since": rel.get("since", ""),
    }


def entity_detail(conn, world_id: str, ref: str, include_secrets: bool, facts_limit: int = 10) -> dict:
    e = store.get_entity(conn, world_id, ref)
    facts = store.list_facts(conn, world_id, e["id"], limit=facts_limit + 1)
    out: dict[str, Any] = {
        "id": e["id"], "ref": e["ref"], "kind": e["kind"], "name": e["name"],
        "aliases": e["aliases"], "status": e["status"],
        "summary": clip(e.get("summary"), 400), "description": clip(e.get("description"), 800),
        "fields": e["fields"], "tags": e["tags"], "parent_id": e.get("parent_id"),
        "relations": [relation_view(conn, world_id, r, e["id"]) for r in store.list_relations(conn, world_id, e["id"])],
        "facts": [fact_brief(f) for f in facts[:facts_limit]],
        "facts_has_more": len(facts) > facts_limit,
    }
    if include_secrets:
        out["secrets"] = e.get("secrets", "")
    return out


def applied_summary(result: dict) -> dict:
    """What `apply_delta` changed, as refs and names only."""
    out: dict[str, Any] = {}
    if result.get("created_entities"):
        out["created_entities"] = [entity_brief(e) for e in result["created_entities"]]
    if result.get("updated_entities"):
        out["updated_entities"] = [entity_brief(e) for e in result["updated_entities"]]
    if result.get("new_facts"):
        out["new_facts"] = [fact_brief(f) for f in result["new_facts"]]
    if result.get("relations"):
        out["relations"] = [{"id": r["id"], "a_id": r["a_id"], "b_id": r["b_id"], "type": r["type"]}
                            for r in result["relations"]]
    if result.get("timeline_events"):
        out["timeline_events"] = [{"id": ev["id"], "in_world_date": ev["in_world_date"],
                                   "summary": clip(ev["summary"], SUMMARY_CHARS)}
                                  for ev in result["timeline_events"]]
    if result.get("thread_changes"):
        out["thread_changes"] = [{"id": t["id"], "ref": t["ref"], "title": t["title"], "status": t["status"]}
                                 for t in result["thread_changes"]]
    if result.get("clock_ticks"):
        out["clock_ticks"] = [{"id": c["id"], "ref": c["ref"], "name": c["name"], "filled": c["filled"],
                               "segments": c["segments"], "full": c["full"]} for c in result["clock_ticks"]]
    return out


def scene_view(conn, world_id: str, scene: Optional[dict]) -> dict:
    """A stored scene (internal ids) as refs and names the model can reuse."""
    scene = scene or {}

    def named(ref: Optional[str]) -> Optional[dict]:
        if not ref:
            return None
        try:
            e = store.get_entity(conn, world_id, ref)
        except store.NotFound:
            return None
        return {"ref": e["ref"], "name": e["name"]}

    present = [p for p in (named(r) for r in scene.get("present") or []) if p]
    return {"location": named(scene.get("location")), "present": present, "mood": scene.get("mood", "")}


def rejected_view(item: dict) -> dict:
    text = json.dumps(item.get("item"), ensure_ascii=False, default=str)
    return {"category": item["category"], "reason": item["reason"], "item": clip(text, SUMMARY_CHARS)}
