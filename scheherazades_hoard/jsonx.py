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
        if ch == "\"":
            in_string = True
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


MAX_BRACE_STARTS = 20  # how many '{' positions to try in free prose


def extract_json_span(text: str) -> tuple[Optional[dict[str, Any]], Optional[tuple[int, int]]]:
    """Like `extract_json`, plus the (start, end) of the text it came from,
    so a caller can cut the JSON out of the surrounding narration."""
    if not text or not text.strip():
        return None, None

    candidates: list[tuple[str, tuple[int, int]]] = []

    for match in _FENCE_RE.finditer(text):
        candidates.append((match.group(1).strip(), match.span()))

    # Bare objects in the prose. Not only the first '{': narration may
    # contain a stray brace ("{sic}") before the real delta.
    start = text.find("{")
    tried = 0
    while start != -1 and tried < MAX_BRACE_STARTS:
        block = _find_balanced_object(text, start)
        if block:
            candidates.append((block, (start, start + len(block))))
        tried += 1
        start = text.find("{", start + 1)

    candidates.append((text.strip(), (0, len(text))))

    for candidate, span in candidates:
        for attempt in (candidate, _strip_trailing_commas(candidate)):
            try:
                parsed = json.loads(attempt)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed, span
    return None, None


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Best-effort extraction of a single JSON object from free-form text."""
    return extract_json_span(text)[0]
