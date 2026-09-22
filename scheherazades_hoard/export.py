"""Turn a world or a session into something a human can read or archive.

Three shapes: a session as a Markdown "chapter" (turns merged into prose),
a world bible (one Markdown section per entity kind), and a full
JSON export/import that round-trips a world exactly.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from . import db, store

_ROLE_LABEL = {
    "narration": "", "action": "> ", "dialogue": "", "ooc": "*(OOC)* ", "roll": "\U0001f3b2 ", "system": "_",
}

_POLISH_PROMPT = """Rewrite the following scene transcript as flowing prose for a reader.
Keep every fact, name, number and event exactly as given — do not invent or
remove anything, only smooth the phrasing and connect the beats.

Transcript:
{text}

Return only the rewritten prose, no commentary."""


POLISH_MAX_CHARS = 6000  # longer chapters would not fit one model reply intact


def polish_prompt(chapter_markdown: str) -> str:
    return _POLISH_PROMPT.format(text=chapter_markdown)


def session_to_markdown(conn, world_id: str, session_ref: Optional[str] = None) -> str:
    world = store.get_world(conn, world_id)
    session_id = store.resolve_session_id(conn, world_id, session_ref)
    session = next(s for s in store.list_sessions(conn, world_id) if s["id"] == session_id)
    turns = [t for t in store.list_turns(conn, session_id) if not t["undone"]]

    lines = [f"# {session['title']}", "", f"*{world['name']}*", ""]
    for t in turns:
        text = t["text"].strip()
        if not text:
            continue
        if t["role"] == "roll":
            rolls = ", ".join(f"{r.get('expression', '')} = {r.get('total', '')}" for r in t.get("rolls") or [])
            lines.append(f"\U0001f3b2 *{text}* ({rolls})" if rolls else f"\U0001f3b2 *{text}*")
        elif t["role"] == "dialogue":
            lines.append(f"“{text}”")
        elif t["role"] == "action":
            lines.append(f"> {text}")
        elif t["role"] == "ooc":
            lines.append(f"*(OOC: {text})*")
        else:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def session_to_markdown_polished(
    conn, world_id: str, session_ref: Optional[str], chat_fn: Callable[[str], Awaitable[str]],
) -> str:
    raw = session_to_markdown(conn, world_id, session_ref)
    prompt = polish_prompt(raw)
    try:
        polished = await chat_fn(prompt)
    except Exception:
        return raw
    return polished.strip() + "\n" if polished and polished.strip() else raw


_KIND_HEADINGS = {
    "character": "Characters", "location": "Locations", "faction": "Factions",
    "item": "Items", "lore": "Lore", "creature": "Creatures",
}


def world_bible_markdown(conn, world_id: str, include_secrets: bool = False) -> str:
    world = store.get_world(conn, world_id)
    lines = [f"# {world['name']}", ""]
    if world["premise"]:
        lines += [world["premise"], ""]
    meta = []
    if world["genre"]:
        meta.append(f"**Genre:** {world['genre']}")
    if world["tone"]:
        meta.append(f"**Tone:** {world['tone']}")
    meta.append(f"**Ruleset:** {world['ruleset']}")
    lines += [" · ".join(meta), ""]

    for kind, heading in _KIND_HEADINGS.items():
        entities = store.list_entities(conn, world_id, kind=kind)
        if not entities:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        for e in entities:
            lines.append(f"### {e['name']} ({e['status']})")
            if e.get("aliases"):
                lines.append(f"*Also known as: {', '.join(e['aliases'])}*")
            if e["summary"]:
                lines.append(f"\n{e['summary']}")
            if e["description"]:
                lines.append(f"\n{e['description']}")
            rels = store.list_relations(conn, world_id, entity_id=e["id"])
            if rels:
                lines.append("\n**Relations:**")
                for r in rels:
                    other_id = r["b_id"] if r["a_id"] == e["id"] else r["a_id"]
                    try:
                        other = store.get_entity(conn, world_id, other_id)
                        lines.append(f"- {r['type']} {other['name']}")
                    except store.NotFound:
                        continue
            facts = store.list_facts(conn, world_id, entity_id=e["id"], limit=20)
            if facts:
                lines.append("\n**Established facts:**")
                for f in facts:
                    tag = " (canon)" if f["canon"] else ""
                    lines.append(f"- {f['text']}{tag}")
            if include_secrets and e.get("secrets"):
                lines.append(f"\n**[GM secret]** {e['secrets']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_world_json(conn, world_id: str) -> dict[str, Any]:
    world = store.get_world(conn, world_id)
    entities = store.list_entities(conn, world_id, limit=100000)
    relations = store.list_relations(conn, world_id)
    facts = store.list_facts(conn, world_id, limit=100000)
    timeline = store.list_timeline(conn, world_id, limit=100000)
    threads = store.list_threads(conn, world_id)
    clocks = store.list_clocks(conn, world_id)
    tables = store.list_tables(conn, world_id)
    sessions = store.list_sessions(conn, world_id)
    turns = []
    for s in sessions:
        turns.extend(store.list_turns(conn, s["id"]))
    return {
        "format": "scheherazades-hoard-world-export", "version": 1,
        "world": world, "entities": entities, "relations": relations,
        "facts": facts, "timeline_events": timeline, "threads": threads,
        "clocks": clocks, "tables": tables, "sessions": sessions, "turns": turns,
    }


def import_world_json(conn, data: dict[str, Any]) -> dict:
    if data.get("format") != "scheherazades-hoard-world-export":
        raise ValueError("not a Scheherazade's Hoard world export")
    w = data["world"]
    new_world = store.create_world(
        conn, name=f"{w['name']} (imported)", genre=w.get("genre", ""), tone=w.get("tone", ""),
        premise=w.get("premise", ""), ruleset=w.get("ruleset", "freeform"),
        language=w.get("language", "es"), rules_text=w.get("rules_text", ""),
        content_lines=w.get("content_lines", []), content_veils=w.get("content_veils", []),
        calendar=w.get("calendar", {}), style_notes=w.get("style_notes", ""),
    )
    wid = new_world["id"]
    id_map: dict[str, str] = {}
    for e in data.get("entities", []):
        created = store.create_entity(
            conn, wid, e["kind"], e["name"], aliases=e.get("aliases"), summary=e.get("summary", ""),
            description=e.get("description", ""), fields=e.get("fields"), secrets=e.get("secrets", ""),
            status=e.get("status", "alive"), tags=e.get("tags"), images=e.get("images"),
        )
        id_map[e["id"]] = created["id"]
    for e in data.get("entities", []):
        if e.get("parent_id") and e["parent_id"] in id_map:
            store.update_entity(conn, wid, id_map[e["id"]], parent_id=id_map[e["parent_id"]])
    for r in data.get("relations", []):
        if r["a_id"] in id_map and r["b_id"] in id_map:
            store.create_relation(conn, wid, id_map[r["a_id"]], id_map[r["b_id"]], r["type"], note=r.get("note", ""), since=r.get("since", ""))
    for f in data.get("facts", []):
        entity_ids = [id_map[i] for i in f.get("entity_ids", []) if i in id_map]
        store.create_fact(conn, wid, f["text"], entity_ids=entity_ids, canon=f.get("canon", False))
    for ev in data.get("timeline_events", []):
        entity_ids = [id_map[i] for i in ev.get("entity_ids", []) if i in id_map]
        store.create_timeline_event(conn, wid, ev.get("in_world_date", ""), ev["summary"], entity_ids=entity_ids)
    for th in data.get("threads", []):
        store.create_thread(conn, wid, th["title"], status=th.get("status", "open"), notes=th.get("notes", ""))
    for c in data.get("clocks", []):
        created = store.create_clock(conn, wid, c["name"], segments=c.get("segments", 4), on_full=c.get("on_full", ""))
        if c.get("filled"):
            store.tick_clock(conn, wid, created["id"], c["filled"])
    for t in data.get("tables", []):
        store.create_table(conn, wid, t["name"], t.get("entries", []))
    return store.get_world(conn, wid)
