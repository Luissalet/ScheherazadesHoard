"""Weighted random tables with nested `[[Other Table]]` references.

Pure with respect to I/O except for reading table definitions through the
store; rolling itself uses the same seedable RNG convention as `dice.py`.
"""
from __future__ import annotations

import re
import secrets
from random import Random
from typing import Optional

from . import store

MAX_DEPTH = 10
_NESTED_RE = re.compile(r"\[\[([^\]]+)\]\]")


class TableError(ValueError):
    pass


def _weighted_pick(rng: Random, entries: list[dict]) -> dict:
    weights = [max(0, e.get("weight", 1)) for e in entries]
    if not entries or sum(weights) <= 0:
        raise TableError("table has no rollable entries")
    return rng.choices(entries, weights=weights, k=1)[0]


def roll_table(
    conn,
    world_id: str,
    table_ref: str,
    seed: Optional[int] = None,
    rng: Optional[Random] = None,
) -> dict:
    """Roll on a table, resolving any nested `[[Table Name]]` references.

    Returns {"text": <final text>, "rolls": [{"table": name, "entry": text}, ...]}
    ordered outermost-first. Raises TableError on an unknown nested table or
    a reference cycle.
    """
    if rng is None:
        rng = Random(seed) if seed is not None else secrets.SystemRandom()
    trail: list[dict] = []
    visited: set[str] = set()

    def resolve(ref: str, depth: int) -> str:
        if depth > MAX_DEPTH:
            raise TableError(f"table nesting too deep (>{MAX_DEPTH}), possible cycle at {ref!r}")
        table = store.get_table(conn, world_id, ref)
        if table["id"] in visited:
            raise TableError(f"cyclic table reference: {table['name']!r}")
        visited.add(table["id"])
        entry = _weighted_pick(rng, table["entries"])
        text = entry["text"]
        trail.append({"table": table["name"], "entry": text})

        def _sub(match: re.Match) -> str:
            return resolve(match.group(1).strip(), depth + 1)

        resolved = _NESTED_RE.sub(_sub, text)
        visited.discard(table["id"])
        return resolved

    final_text = resolve(table_ref, 0)
    return {"text": final_text, "rolls": trail, "seed": seed}
