"""`world_check`: does a proposed statement contradict what is established?

Two layers, both cited so a human (or the narrator) can verify:

1. Lexical retrieval of candidate facts/entities (FTS, accent-insensitive)
   plus three concrete rules: a dead/missing/destroyed character acting, an
   entity placed somewhere other than where it was last seen, and a stated
   relation that contradicts a tracked opposite relation (loves/hates,
   ally/enemy, trusts/betrays).
2. Optionally, when an LLM is available, a judge pass over the top
   candidates that must cite fact ids — never invents a contradiction
   without pointing at one. The judge is a plain async callable
   `chat_fn(prompt: str) -> str` so tests can supply a scripted fake; the
   API layer wires in the real backend.

These are heuristics over plain text, not real NLP — false negatives (a
missed contradiction) are expected and documented as a boundary.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Awaitable, Callable, Optional

from . import jsonx, store

DEAD_STATUSES = {"dead", "destroyed", "missing"}

# Keyword -> canonical relation type, and each type's contradicting type(s).
_RELATION_KEYWORDS = {
    "ama a": "ama a", "odia a": "odia a", "aliado de": "aliado de",
    "enemigo de": "enemigo de", "confia en": "confia en", "traiciona a": "traiciona a",
    "loves": "ama a", "hates": "odia a", "allied with": "aliado de",
    "enemy of": "enemigo de", "trusts": "confia en", "betrays": "traiciona a",
}
_OPPOSITES = {
    "ama a": {"odia a"}, "odia a": {"ama a"},
    "aliado de": {"enemigo de"}, "enemigo de": {"aliado de"},
    "confia en": {"traiciona a"}, "traiciona a": {"confia en"},
}


def _fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)
    ).lower()


def _mentions(statement_folded: str, name: str) -> bool:
    """Whole-word match: "Ana" must not match "ventana", nor "Sal" "salta"."""
    name_folded = _fold(name).strip()
    if not name_folded:
        return False
    return re.search(rf"(?<!\w){re.escape(name_folded)}(?!\w)", statement_folded) is not None


def _mentions_entity(statement_folded: str, e: dict) -> bool:
    names = [e["name"], *(e.get("aliases") or []), *e.get("_short_names", [])]
    return any(_mentions(statement_folded, n) for n in names)


def _add_short_names(entities: list[dict]) -> None:
    """Characters are usually called by their first name ("Marisol" for
    "Marisol Vega"): accept it when no other entity starts with the same
    word, so the rules do not only fire on full names."""
    firsts: dict[str, int] = {}
    for e in entities:
        first = _fold(e["name"]).split()[0] if e["name"].split() else ""
        firsts[first] = firsts.get(first, 0) + 1
    for e in entities:
        words = e["name"].split()
        if e["kind"] == "character" and len(words) > 1 and len(words[0]) >= 3 and firsts.get(_fold(words[0])) == 1:
            e["_short_names"] = [words[0]]


# Talking *about* the dead is not the dead acting: a grave, a memory, a
# ghost, the body, the news of the death.
_DEATH_CONTEXT = re.compile(
    r"(?<!\w)(tumba|entierro|funeral|funerales|cadaver|recuerd\w*|memoria|fantasma|espectro|"
    r"murio|muerte|difunt\w*|luto|velatorio|grave|burial|corpse|remember\w*|memory|ghost|"
    r"died|death|mourn\w*)(?!\w)"
)


# Rule messages in the world's language (worlds are often played in Spanish).
_MSG = {
    "en": {
        "dead_text": "{name} is {status}",
        "dead_why": "{name} is {status} and the statement implies they are active",
        "loc_text": "{name} was last placed at {last}",
        "loc_why": "the statement places {name} at {here}, but they were last seen at {last}",
        "rel_why": "the statement implies '{stated}', which contradicts the tracked relation '{tracked}'",
    },
    "es": {
        "dead_text": "{name} está {status}",
        "dead_why": "{name} está {status} y la afirmación le hace actuar",
        "loc_text": "{name} estaba por última vez en {last}",
        "loc_why": "la afirmación sitúa a {name} en {here}, pero se le vio por última vez en {last}",
        "rel_why": "la afirmación implica «{stated}», que contradice la relación registrada «{tracked}»",
    },
}
_STATUS_ES = {"dead": "muerto/a", "missing": "desaparecido/a", "destroyed": "destruido/a"}


def _msg(lang: str, key: str, **kw: str) -> str:
    table = _MSG.get(lang, _MSG["en"])
    if lang == "es" and "status" in kw:
        kw["status"] = _STATUS_ES.get(kw["status"], kw["status"])
    return table[key].format(**kw)


def _rule_dead_acting(conn, world_id: str, statement: str, entities: list[dict], lang: str = "en") -> list[dict]:
    folded = _fold(statement)
    if _DEATH_CONTEXT.search(folded):
        return []
    conflicts = []
    for e in entities:
        if e["status"] in DEAD_STATUSES and _mentions_entity(folded, e):
            conflicts.append({
                "fact_id": e["ref"],
                "text": _msg(lang, "dead_text", name=e["name"], status=e["status"]),
                "why": _msg(lang, "dead_why", name=e["name"], status=e["status"]),
            })
    return conflicts


def _last_known_location(conn, world_id: str, entity_id: str) -> Optional[dict]:
    for sess in reversed(store.list_sessions(conn, world_id)):
        for turn in reversed(store.list_turns(conn, sess["id"])):
            if turn["undone"]:
                continue  # an undone turn never happened
            scene = turn.get("scene") or {}
            if entity_id in (scene.get("present") or []) and scene.get("location"):
                try:
                    return store.get_entity(conn, world_id, scene["location"])
                except store.NotFound:
                    continue
    return None


def _rule_location_mismatch(conn, world_id: str, statement: str, entities: list[dict], locations: list[dict], lang: str = "en") -> list[dict]:
    folded = _fold(statement)
    conflicts = []
    mentioned_locations = [loc for loc in locations if _mentions_entity(folded, loc)]
    if not mentioned_locations:
        return conflicts
    for e in entities:
        if e["kind"] != "character" or not _mentions_entity(folded, e):
            continue
        last_loc = _last_known_location(conn, world_id, e["id"])
        if not last_loc:
            continue
        for mentioned in mentioned_locations:
            if mentioned["id"] != last_loc["id"]:
                conflicts.append({
                    "fact_id": last_loc["ref"],
                    "text": _msg(lang, "loc_text", name=e["name"], last=last_loc["name"]),
                    "why": _msg(lang, "loc_why", name=e["name"], here=mentioned["name"], last=last_loc["name"]),
                })
    return conflicts


def _rule_relation_contradiction(conn, world_id: str, statement: str, entities: list[dict], lang: str = "en") -> list[dict]:
    folded = _fold(statement)
    conflicts = []
    stated_type = None
    for kw, canon in _RELATION_KEYWORDS.items():
        if _fold(kw) in folded:
            stated_type = canon
            break
    if not stated_type:
        return conflicts
    mentioned = [e for e in entities if _mentions_entity(folded, e)]
    if len(mentioned) < 2:
        return conflicts
    relations = store.list_relations(conn, world_id)
    by_id = {e["id"]: e for e in mentioned}
    for rel in relations:
        if rel["a_id"] not in by_id or rel["b_id"] not in by_id:
            continue
        if stated_type in _OPPOSITES.get(rel["type"], set()):
            a, b = by_id[rel["a_id"]], by_id[rel["b_id"]]
            conflicts.append({
                "fact_id": rel["id"],
                "text": f"{a['name']} {rel['type']} {b['name']}",
                "why": _msg(lang, "rel_why", stated=stated_type, tracked=rel["type"]),
            })
    return conflicts


_JUDGE_PROMPT = """You check a tabletop/story statement against established facts.
Established facts (cite by id, never invent an id):
{facts}

Statement to check: {statement}

Reply with ONLY a JSON object: {{"conflicts": [{{"fact_id": "<id from the list above>", "why": "<one sentence>"}}]}}
If there is no contradiction, reply {{"conflicts": []}}."""


async def world_check(
    conn,
    world_id: str,
    statement: str,
    chat_fn: Optional[Callable[[str], Awaitable[str]]] = None,
    judge_limit: int = 6,
) -> dict:
    entities = store.list_entities(conn, world_id, limit=500)
    _add_short_names(entities)
    locations = [e for e in entities if e["kind"] == "location"]

    conflicts: list[dict] = []
    lang = store.get_world(conn, world_id).get("language", "en")
    conflicts.extend(_rule_dead_acting(conn, world_id, statement, entities, lang))
    conflicts.extend(_rule_location_mismatch(conn, world_id, statement, entities, locations, lang))
    conflicts.extend(_rule_relation_contradiction(conn, world_id, statement, entities, lang))

    candidates = store.search_facts(conn, world_id, statement, limit=judge_limit)
    judge = "no_candidates" if not candidates else ("not_configured" if chat_fn is None else "unavailable")
    if chat_fn is not None and candidates:
        facts_block = "\n".join(f"- [{f['ref']}] {f['text']}" for f in candidates)
        prompt = _JUDGE_PROMPT.format(facts=facts_block, statement=statement)
        try:
            raw = await chat_fn(prompt)
            judge = "used"
        except Exception:
            raw = ""
        parsed = jsonx.extract_json(raw) if raw else None
        valid_refs = {f["ref"] for f in candidates}
        seen_refs = {c["fact_id"] for c in conflicts}
        if parsed and isinstance(parsed.get("conflicts"), list):
            for item in parsed["conflicts"]:
                ref = item.get("fact_id")
                why = item.get("why", "")
                if ref in valid_refs and ref not in seen_refs:
                    fact = next(f for f in candidates if f["ref"] == ref)
                    conflicts.append({"fact_id": ref, "text": fact["text"], "why": why})
                    seen_refs.add(ref)

    return {
        "consistent": len(conflicts) == 0,
        "conflicts": conflicts,
        "checked": statement[:300],
        # how far the check went: the rules always run; the LLM judge is
        # "used", "unavailable" (no model resolved), or skipped because no
        # established fact matched the statement ("no_candidates").
        "rules_checked": ["dead_acting", "location_mismatch", "relation_contradiction"],
        "llm_judge": judge,
    }
