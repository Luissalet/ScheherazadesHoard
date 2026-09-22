"""Robust JSON extraction from LLM output.

Local models wrap JSON in prose, fenced code blocks, leave trailing
commas, use curly "smart" quotes instead of straight ones, add `//` or
`/* */` comments, nest the payload under an extra key such as `"delta"`,
or simply get cut off mid-object at the token limit. This module tries
progressively more forgiving strategies and never raises — callers get
`None` on total failure and can fall back gracefully (spec: "on failure
keep the narration and mark the delta `unparsed`").
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional, Sequence

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")
_SMART_QUOTES = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
})


def _strip_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _normalize_smart_quotes(text: str) -> str:
    """Curly quotes used as JSON string delimiters (`{“scene”: ...}`)
    break `json.loads` outright. A small local model reaches for them out
    of habit; straightening every quote character is safe here because
    this text has already failed strict parsing."""
    return text.translate(_SMART_QUOTES)


def _strip_json_comments(text: str) -> str:
    """Remove `//line` and `/* block */` comments, leaving quoted strings
    (including ones that contain `//` or `/*`) untouched."""
    out: list[str] = []
    in_string = False
    escape = False
    quote = ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_NUMBER_OR_LITERAL_END = set(",}] \t\r\n\"")


def _repair_truncated(text: str) -> Optional[str]:
    """Best-effort repair of an object cut off mid-value (a reply stopped
    at the model's token limit): walk the text tracking nested
    objects/arrays and string state, remember the last point at which
    everything read so far forms a *complete* value, cut the incomplete
    tail there, and close whatever containers were still open. Returns
    `None` when the text was not actually truncated (no unclosed
    container) — the caller's other strategies already cover that case.
    """
    stack: list[str] = []
    in_string = False
    escape = False
    last_good = 0  # end index of the last known-complete value/container
    last_good_stack: list[str] = []  # container stack AS OF `last_good`
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
                # Safe to cut right after this string only if it is a
                # *value* (or an array element) — the next non-space
                # character, if any, is a comma or a closer. If it is a
                # ':', this string was a key still waiting for its value,
                # and if nothing follows at all we cannot tell either way:
                # in both cases dropping it is the safe choice.
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] in ",}]":
                    last_good, last_good_stack = i + 1, list(stack)
            i += 1
            continue
        if ch == '"':
            in_string = True
            escape = False
            i += 1
            continue
        if ch in "{[":
            stack.append(ch)
            i += 1
            continue
        if ch in "}]":
            if stack:
                stack.pop()
            last_good, last_good_stack = i + 1, list(stack)
            i += 1
            continue
        if ch in "-0123456789tfn":  # number literal, true, false, null
            j = i
            while j < n and text[j] not in _NUMBER_OR_LITERAL_END:
                j += 1
            if j < n:  # a full literal followed by a delimiter we can see
                last_good, last_good_stack = j, list(stack)
            i = j if j > i else i + 1
            continue
        i += 1

    if not stack:
        return None  # nothing left open: this was not a truncation

    repaired = text[:last_good].rstrip()
    repaired = repaired.rstrip(",")
    closers = "".join("}" if c == "{" else "]" for c in reversed(last_good_stack))
    return repaired + closers


def _unwrap_nested(parsed: dict, prefer_keys: Sequence[str]) -> dict:
    """A model sometimes wraps the payload one level down (e.g. under
    `{"delta": {...}}`). If the top level has none of the keys we want but
    exactly one nested dict does, use that one instead."""
    if any(k in parsed for k in prefer_keys):
        return parsed
    nested_hits = [v for v in parsed.values() if isinstance(v, dict) and any(k in v for k in prefer_keys)]
    if len(nested_hits) == 1:
        return nested_hits[0]
    return parsed


def extract_json_span(
    text: str, prefer_keys: Optional[Sequence[str]] = None,
) -> tuple[Optional[dict[str, Any]], Optional[tuple[int, int]]]:
    """Like `extract_json`, plus the (start, end) of the text it came from,
    so a caller can cut the JSON out of the surrounding narration.

    `prefer_keys`: when several candidate objects parse, the first one
    that already contains one of these keys (or has it nested one level
    down, e.g. under `"delta"`) wins over an earlier, unrelated object —
    a model that emits a stray `{}` before the real payload, or repeats
    itself with two fenced blocks, must not shadow the one we want.
    """
    if not text or not text.strip():
        return None, None

    candidates: list[tuple[str, tuple[int, int]]] = []

    for match in _FENCE_RE.finditer(text):
        candidates.append((match.group(1).strip(), match.span()))

    # Bare objects in the prose. Not only the first '{': narration may
    # contain a stray brace ("{sic}") before the real delta. When an
    # object never closes before the text ends — an unclosed fence, or a
    # reply cut off at the token limit — keep "start to end of text" as a
    # candidate too, so the truncation repair below has something to work
    # with instead of silently giving up on that object.
    start = text.find("{")
    tried = 0
    while start != -1 and tried < MAX_BRACE_STARTS:
        block = _find_balanced_object(text, start)
        if block:
            candidates.append((block, (start, start + len(block))))
        else:
            candidates.append((text[start:], (start, len(text))))
        tried += 1
        start = text.find("{", start + 1)

    candidates.append((text.strip(), (0, len(text))))

    fallback: Optional[tuple[dict[str, Any], tuple[int, int]]] = None

    for candidate, span in candidates:
        attempts = [candidate, _strip_trailing_commas(candidate)]
        no_comments = _strip_json_comments(candidate)
        attempts += [no_comments, _strip_trailing_commas(no_comments)]
        smart = _normalize_smart_quotes(candidate)
        attempts += [smart, _strip_trailing_commas(smart), _strip_json_comments(smart)]
        repaired = _repair_truncated(_strip_trailing_commas(_strip_json_comments(smart)))
        if repaired:
            attempts.append(repaired)

        for attempt in attempts:
            try:
                parsed = json.loads(attempt)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(parsed, dict):
                continue
            if prefer_keys:
                parsed = _unwrap_nested(parsed, prefer_keys)
                if any(k in parsed for k in prefer_keys):
                    return parsed, span
                if fallback is None:
                    fallback = (parsed, span)
            else:
                return parsed, span
            break  # this candidate parsed; move to the next candidate

    return fallback if fallback else (None, None)


def extract_json(text: str, prefer_keys: Optional[Sequence[str]] = None) -> Optional[dict[str, Any]]:
    """Best-effort extraction of a single JSON object from free-form text."""
    return extract_json_span(text, prefer_keys=prefer_keys)[0]


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
