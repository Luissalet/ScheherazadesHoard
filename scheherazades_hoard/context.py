"""The context builder: the narrator's brief for the next scene.

This is the module the whole app exists to justify. It assembles, in a
fixed and deterministic order of importance, exactly the slice of world
state a language model needs to narrate the next beat without either
re-reading everything ever written or hallucinating continuity — and never
more than `budget_chars` of it. Every line is tagged with a stable short id
(`E1`, `F1`, `T1`, `C1`) so a narrator can cite it and a later delta can
refer back to it.

No FastAPI imports; operates purely against the store.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional

from . import store

DEFAULT_BUDGET = 3000


def _fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)
    ).lower()


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _score_fact(fact: dict, present_ids: set[str], query_terms: list[str], rank_index: int, total: int) -> float:
    score = 0.0
    if fact.get("canon"):
        score += 2.0
    mentioned = set(fact.get("entity_ids") or []) & present_ids
    score += 2.5 * len(mentioned)
    text_folded = _fold(fact.get("text", ""))
    score += sum(1.0 for t in query_terms if t and t in text_folded)
    # mild recency boost: later facts (higher seq) score slightly higher,
    # normalised so it never dominates canon/mention/match signals.
    if total > 1:
        score += 0.5 * (rank_index / (total - 1))
    return score


def world_context(
    conn,
    world_id: str,
    scene: Optional[dict] = None,
    focus: Optional[str] = None,
    include_secrets: bool = False,
    budget_chars: int = DEFAULT_BUDGET,
) -> dict:
    world = store.get_world(conn, world_id)
    budget_chars = max(200, int(budget_chars))

    # --- resolve the current scene -----------------------------------
    scene = dict(scene or {}) or store.current_scene(conn, world_id)

    location = None
    loc_ref = scene.get("location")
    if loc_ref:
        try:
            location = store.get_entity(conn, world_id, loc_ref)
        except store.NotFound:
            location = None

    present_entities: list[dict] = []
    for ref in scene.get("present") or []:
        try:
            present_entities.append(store.get_entity(conn, world_id, ref))
        except store.NotFound:
            continue
    present_ids = {e["id"] for e in present_entities}

    relations = store.list_relations(conn, world_id)
    present_relations = [
        r for r in relations if r["a_id"] in present_ids and r["b_id"] in present_ids
    ]
    by_id = {e["id"]: e for e in present_entities}

    def entity_brief(e: dict) -> dict:
        rels_here = [
            {
                "with": by_id[r["b_id"]]["name"] if r["a_id"] == e["id"] else by_id[r["a_id"]]["name"],
                "type": r["type"],
            }
            for r in present_relations
            if e["id"] in (r["a_id"], r["b_id"])
        ]
        brief = {
            "ref": e["ref"],
            "name": e["name"],
            "kind": e["kind"],
            "status": e["status"],
            "summary": _truncate(e.get("summary", ""), 160),
            "traits": e.get("fields", {}),
            "relations": rels_here,
        }
        if include_secrets and e.get("secrets"):
            brief["secrets"] = f"[GM] {e['secrets']}"
        return brief

    present_briefs = [entity_brief(e) for e in present_entities]

    # entities the fact-ranking cares about: who's present, plus where
    focus_entities = list(present_entities) + ([location] if location else [])
    focus_ids = {e["id"] for e in focus_entities}

    # --- rank relevant lore/facts --------------------------------------
    query_terms = [t for t in _fold(f"{focus or ''} " + " ".join(e["name"] for e in focus_entities)).split() if t]
    query_text = " ".join(dict.fromkeys(query_terms))  # de-duplicated, order preserved

    candidate_facts: dict[str, dict] = {}
    for e in focus_entities:
        for f in store.list_facts(conn, world_id, entity_id=e["id"], limit=20):
            candidate_facts[f["id"]] = f
    if query_text:
        for f in store.search_facts(conn, world_id, query_text, limit=20):
            candidate_facts[f["id"]] = f
    if not candidate_facts:
        # nothing scene-specific yet (e.g. very first scene): fall back to
        # the most recently established canon facts so the brief isn't empty.
        for f in store.list_facts(conn, world_id, limit=10):
            candidate_facts[f["id"]] = f

    facts_list = list(candidate_facts.values())
    total = len(facts_list)
    scored = sorted(
        enumerate(facts_list),
        key=lambda pair: _score_fact(pair[1], focus_ids, query_terms, pair[0], total),
        reverse=True,
    )
    lore_ranked = [f for _, f in scored]

    # --- threads touching present entities ------------------------------
    open_threads = store.list_threads(conn, world_id, status="open")
    if present_entities:
        names = [_fold(e["name"]) for e in present_entities]
        touching = [
            t for t in open_threads
            if any(n in _fold(t["title"]) or n in _fold(t["notes"]) for n in names)
        ]
        threads_ranked = touching or open_threads
    else:
        threads_ranked = open_threads

    # --- clocks near completion ------------------------------------------
    clocks = store.list_clocks(conn, world_id)
    clocks_ranked = sorted(
        clocks, key=lambda c: (c["filled"] / c["segments"] if c["segments"] else 0), reverse=True
    )

    # --- recent turns ------------------------------------------------------
    # read-only: never create a session just to look at it
    session = store.get_current_session(conn, world_id)
    recent_turns_all = store.list_turns(conn, session["id"], limit=12) if session else []
    recent_turns_all = [t for t in recent_turns_all if not t["undone"]]

    # --- assemble within budget, most important first ---------------------
    lines: list[str] = []
    used = 0
    truncated = False

    def add(line: str, required: bool = False) -> bool:
        nonlocal used, truncated
        cost = len(line) + 1
        if not required and used + cost > budget_chars:
            truncated = True
            return False
        lines.append(line)
        used += cost
        return True

    add(f"WORLD: {world['name']} ({world['genre']}, tone: {world['tone']})", required=True)
    if world["premise"]:
        add(_truncate(f"PREMISE: {world['premise']}", 300), required=True)
    boundaries = world["content_lines"] + [f"veil: {v}" for v in world["content_veils"]]
    if boundaries:
        add("BOUNDARIES: " + "; ".join(boundaries[:6]))

    if location:
        add(f"LOCATION [{location['ref']}]: {location['name']} — {_truncate(location.get('summary', ''), 120)}")
    if present_briefs:
        add("PRESENT:")
        kept_present = []
        for pb in present_briefs:
            traits = ", ".join(f"{k}={v}" for k, v in list(pb["traits"].items())[:4])
            rel_txt = "; ".join(f"{r['type']} {r['with']}" for r in pb["relations"][:4])
            line = f"  [{pb['ref']}] {pb['name']} ({pb['kind']}, {pb['status']}) {pb['summary']}"
            if traits:
                line += f" | traits: {traits}"
            if rel_txt:
                line += f" | rel: {rel_txt}"
            if add(line):
                kept_present.append(pb)
                if pb.get("secrets"):
                    if add(f"    {pb['secrets']}"):
                        pass
            else:
                break
    else:
        kept_present = []
    if scene.get("mood"):
        add(f"MOOD: {scene['mood']}")

    kept_lore = []
    if lore_ranked:
        add("LORE:")
        for f in lore_ranked:
            tag = "canon" if f["canon"] else "fact"
            if add(f"  [{f['ref']}] ({tag}) {_truncate(f['text'], 200)}"):
                kept_lore.append(f)
            else:
                break

    kept_threads = []
    if threads_ranked:
        add("THREADS:")
        for t in threads_ranked:
            if add(f"  [{t['ref']}] {t['title']} ({t['status']})"):
                kept_threads.append(t)
            else:
                break

    kept_clocks = []
    near = [c for c in clocks_ranked if c["segments"] and c["filled"] / c["segments"] >= 0.5]
    if near:
        add("CLOCKS NEAR FULL:")
        for c in near:
            if add(f"  [{c['ref']}] {c['name']}: {c['filled']}/{c['segments']}"):
                kept_clocks.append(c)
            else:
                break

    kept_turns = []
    if recent_turns_all:
        add("RECENT:")
        for t in recent_turns_all[-4:]:
            if add(f"  ({t['role']}/{t['author']}) {_truncate(t['text'], 140)}"):
                kept_turns.append(t)
            else:
                break

    brief = "\n".join(lines)

    return {
        "world_id": world_id,
        "brief": brief,
        "scene": {
            "location": {"ref": location["ref"], "name": location["name"]} if location else None,
            "present": kept_present,
            "mood": scene.get("mood", ""),
        },
        "lore": [
            {"ref": f["ref"], "canon": f["canon"], "text": f["text"]} for f in kept_lore
        ],
        "threads": [
            {"ref": t["ref"], "title": t["title"], "status": t["status"]} for t in kept_threads
        ],
        "clocks": [
            {"ref": c["ref"], "name": c["name"], "filled": c["filled"], "segments": c["segments"]}
            for c in kept_clocks
        ],
        "recent_turns": [
            {"role": t["role"], "author": t["author"], "text": _truncate(t["text"], 140)}
            for t in kept_turns
        ],
        "budget_chars": budget_chars,
        "used_chars": used,
        "truncated": truncated,
    }
