"""Robust JSON extraction from LLM output.

Local models wrap JSON in prose, fenced code blocks, and leave trailing
commas. This module tries progressively more forgiving strategies and
never raises — callers get `None` on total failure and can fall back
gracefully (spec: "on failure keep the narration and mark the delta
`unparsed`").
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([\]}])")


def _strip_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _find_balanced_object(text: str, start: int) -> Optional[str]:
    """From an opening '{' at `start`, find the matching '}' respecting strings."""
    depth = 0
    in_string = False
    escape = False
    quote = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ("\"", "'"):
            in_string = True
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Best-effort extraction of a single JSON object from free-form text."""
    if not text or not text.strip():
        return None

    candidates: list[str] = []

    for match in _FENCE_RE.finditer(text):
        candidates.append(match.group(1).strip())

    # A bare object somewhere in the prose.
    first_brace = text.find("{")
    if first_brace != -1:
        block = _find_balanced_object(text, first_brace)
        if block:
            candidates.append(block)

    candidates.append(text.strip())

    for candidate in candidates:
        for attempt in (candidate, _strip_trailing_commas(candidate)):
            try:
                parsed = json.loads(attempt)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None
