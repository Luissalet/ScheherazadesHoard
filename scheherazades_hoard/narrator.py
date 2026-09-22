"""The standalone narrator: builds the prompt, calls the shared LLM, and
parses narration + a proposed delta out of the response.

Used when the app itself narrates (no Faustus in the loop). When Faustus
narrates instead, none of this runs — Faustus calls `world_context` and
`story_append` over MCP directly and this module is unused for that turn.
"""
from __future__ import annotations

import re
from typing import Optional

from . import context as context_mod
from . import jsonx, store
from .backend import Link, Unavailable

DELTA_KEYS = (
    "new_entities", "entity_updates", "new_facts", "relations",
    "timeline_events", "thread_changes", "clock_ticks", "scene",
)

_LANGUAGE_NAME = {"es": "Spanish", "en": "English"}

_SYSTEM_TEMPLATE = """You are the narrator for a tabletop / interactive-fiction scene.

World: {world_name} ({genre}, tone: {tone})
Ruleset: {ruleset}
Style notes: {style_notes}
Content boundaries (never cross the lines; keep veiled things off-screen): {boundaries}

Narrate the next beat vividly in {language_name}, 2 to 5 short paragraphs,
reacting to the player's action and to any roll result given to you. Never
invent a dice result; only use the ones you are given.

After the narration, on new lines, output EXACTLY one fenced ```json block
with the scene delta using this shape (omit arrays that are empty, use []
rather than null, and cite existing things by the id shown in the brief,
e.g. E1/F1/T1/C1 — only name new things you are creating):

```json
{{"new_entities": [], "entity_updates": [], "new_facts": [], "relations": [],
 "timeline_events": [], "thread_changes": [], "clock_ticks": [],
 "scene": {{"location": null, "present": [], "mood": ""}}}}
```
"""

_FENCE_STRIP_RE = re.compile(r"```(?:json)?\s*.*?```", re.DOTALL | re.IGNORECASE)


def _strip_json_block(text: str) -> str:
    return _FENCE_STRIP_RE.sub("", text).strip()


def build_system_prompt(world: dict) -> str:
    boundaries = world["content_lines"] + [f"veil: {v}" for v in world["content_veils"]]
    return _SYSTEM_TEMPLATE.format(
        world_name=world["name"], genre=world["genre"] or "unspecified",
        tone=world["tone"] or "unspecified", ruleset=world["ruleset"],
        style_notes=world["style_notes"] or "none",
        boundaries="; ".join(boundaries) if boundaries else "none stated",
        language_name=_LANGUAGE_NAME.get(world["language"], "the world's language"),
    )


async def narrate(
    link: Link,
    conn,
    world_id: str,
    action_text: str,
    roll_result: Optional[dict] = None,
    scene: Optional[dict] = None,
    budget_chars: int = 3000,
    max_tokens: int = 900,
    temperature: float = 0.8,
) -> dict:
    """Build the prompt, call the shared LLM, and return narration + a raw delta.

    Raises `Unavailable` (from backend.py) if no LLM resolves — the caller
    (API layer) turns that into a clear error for the UI/agent.
    """
    world = store.get_world(conn, world_id)
    ctx = context_mod.world_context(
        conn, world_id, scene=scene, include_secrets=True, budget_chars=budget_chars,
    )
    system = build_system_prompt(world)
    user_lines = [f"WORLD BRIEF:\n{ctx['brief']}", f"\nPLAYER ACTION: {action_text}"]
    if roll_result:
        user_lines.append(f"ROLL RESULT: {roll_result.get('expression', '')} = {roll_result.get('total', '')}")
    user_content = "\n".join(user_lines)

    chat_result = await link.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        max_tokens=max_tokens, temperature=temperature,
    )
    raw = chat_result.text
    parsed = jsonx.extract_json(raw)

    delta_obj = None
    unparsed = True
    narration_text = raw.strip()
    if parsed and any(k in parsed for k in DELTA_KEYS):
        delta_obj = {k: parsed[k] for k in DELTA_KEYS if k in parsed}
        narration_text = _strip_json_block(raw)
        unparsed = False

    return {
        "narration": narration_text,
        "delta": delta_obj,
        "unparsed": unparsed,
        "raw": raw,
        "context": ctx,
        "model": chat_result.model,
        "provider": chat_result.provider,
        "usage": chat_result.usage.to_dict(),
        "elapsed_ms": chat_result.elapsed_ms,
    }
