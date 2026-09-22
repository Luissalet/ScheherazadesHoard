"""Unit tests for robust JSON extraction from LLM output."""
from __future__ import annotations

from scheherazades_hoard import jsonx


def test_plain_json():
    assert jsonx.extract_json('{"a": 1}') == {"a": 1}


def test_json_in_fenced_block():
    text = 'Here you go:\n```json\n{"a": 1, "b": [1,2]}\n```\nHope that helps.'
    assert jsonx.extract_json(text) == {"a": 1, "b": [1, 2]}


def test_json_with_prose_around_it():
    text = 'Sure! {"narration": "the door creaks", "delta": {"new_facts": []}} — enjoy.'
    result = jsonx.extract_json(text)
    assert result["narration"] == "the door creaks"


def test_trailing_commas_are_repaired():
    text = '{"a": 1, "b": [1, 2,], "c": {"x": 1,},}'
    assert jsonx.extract_json(text) == {"a": 1, "b": [1, 2], "c": {"x": 1}}


def test_missing_json_returns_none():
    assert jsonx.extract_json("just some prose, no braces here") is None


def test_empty_input_returns_none():
    assert jsonx.extract_json("") is None
    assert jsonx.extract_json(None) is None


def test_nested_braces_in_strings_do_not_break_balance():
    text = 'prefix {"text": "a { weird } string", "n": 1} suffix'
    result = jsonx.extract_json(text)
    assert result["n"] == 1
    assert "{ weird }" in result["text"]


# --- regressions found in review ------------------------------------------

def test_stray_brace_in_prose_before_the_delta():
    text = 'Ella escribe {sic} en el margen. {"new_facts": [{"text": "x"}]}'
    assert jsonx.extract_json(text) == {"new_facts": [{"text": "x"}]}


def test_apostrophe_before_the_object_does_not_break_it():
    text = "Mara's lantern flickers. {\"scene\": {\"mood\": \"tense\"}}"
    assert jsonx.extract_json(text) == {"scene": {"mood": "tense"}}
