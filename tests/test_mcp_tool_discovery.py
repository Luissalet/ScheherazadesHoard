"""Regression test for the "Faustus can't find the tools in Spanish" bug
(usability report #1): a picker that only ever sees the first 120
characters of a tool's description's first line must still be able to
match a Spanish request to the right tool, for every tool.

This does not spawn Faustus itself (that indexer is outside this repo);
it reproduces the exact failure mode the usability walkthrough hit — a
naive word-overlap match against a truncated first line — directly
against the descriptions `mcp_server.py` publishes, so a future edit
that moves the Spanish words back out of line one fails this test.
"""
from __future__ import annotations

import asyncio
import re

import scheherazades_hoard.mcp_server as mcp_server

# (Spanish request a Faustus user would plausibly type, expected tool name)
SPANISH_REQUESTS = [
    ("qué mundos hay creados", "story_worlds"),
    ("crea un mundo nuevo de fantasía", "story_world_create"),
    ("dame el contexto de la escena", "world_context"),
    ("busca quién es el capitán", "world_search"),
    ("dame la ficha de personaje de Iria", "entity_get"),
    ("crea un personaje nuevo llamado Nadia", "entity_upsert"),
    ("registra este turno de la partida", "story_append"),
    ("tira los dados 2d6", "dice_roll"),
    ("tira en la tabla aleatoria de rumores", "table_roll"),
    ("actualiza el hilo de la trama principal", "thread_update"),
    ("avanza el reloj de cuenta atrás", "clock_tick"),
    ("comprueba si esto es coherente", "world_check"),
    ("exporta el capítulo de la sesión", "session_export"),
    ("deshacer el último turno", "story_undo"),
]

_WORD_RE = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) > 2}


def _first_line_120(description: str) -> str:
    first_line = description.splitlines()[0]
    return first_line[:120]


def _pick_tool(request: str, tools: list) -> str:
    """The simplest possible word-overlap picker: score each tool by how
    many of the request's words appear in its (truncated) description,
    and return the best match. This mirrors the walkthrough's picker."""
    req_words = _words(request)
    best_name, best_score = "", -1
    for tool in tools:
        score = len(req_words & _words(_first_line_120(tool.description or "")))
        if score > best_score:
            best_name, best_score = tool.name, score
    return best_name


def test_every_tool_description_has_spanish_words_on_line_one():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    assert len(tools) == 14
    accented = set("áéíóúñü")
    for tool in tools:
        line_one = tool.description.splitlines()[0]
        has_spanish = any(c in accented for c in line_one.lower()) or " / " in line_one
        assert has_spanish, f"{tool.name}: line one has no Spanish cue: {line_one!r}"


def test_naive_spanish_picker_finds_the_right_tool_for_every_request():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    misses = []
    for request, expected in SPANISH_REQUESTS:
        picked = _pick_tool(request, tools)
        if picked != expected:
            misses.append((request, expected, picked))
    assert not misses, f"picker failed on: {misses}"
