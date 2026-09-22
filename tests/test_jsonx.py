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


# --- usability report #2: sloppy realistic 27B replies ---------------------

def test_curly_quotes_are_normalised():
    text = "“scene”: {“mood”: “tenso”}"
    assert jsonx.extract_json("{" + text + "}") == {"scene": {"mood": "tenso"}}


def test_line_comments_are_stripped_without_touching_string_content():
    text = '{"a": 1, // a comment with // inside it\n"b": "keeps // this"}'
    assert jsonx.extract_json(text) == {"a": 1, "b": "keeps // this"}


def test_block_comments_are_stripped():
    text = '{/* leading */ "a": 1 /* trailing */}'
    assert jsonx.extract_json(text) == {"a": 1}


def test_comments_and_trailing_commas_together():
    text = '{\n  "a": 1, // note\n  "b": [1, 2,], /* also */\n}'
    assert jsonx.extract_json(text) == {"a": 1, "b": [1, 2]}


def test_prefer_keys_unwraps_a_payload_nested_one_level_down():
    text = '{"delta": {"new_facts": [{"text": "x"}]}}'
    result = jsonx.extract_json(text, prefer_keys=("new_facts", "scene"))
    assert result == {"new_facts": [{"text": "x"}]}


def test_prefer_keys_skips_an_earlier_object_that_lacks_them():
    text = '{"note": "borrador"} luego {"new_facts": [{"text": "x"}]}'
    result = jsonx.extract_json(text, prefer_keys=("new_facts",))
    assert result == {"new_facts": [{"text": "x"}]}


def test_prefer_keys_falls_back_to_first_parseable_object_if_none_match():
    text = '{"note": "sin delta"}'
    result = jsonx.extract_json(text, prefer_keys=("new_facts",))
    assert result == {"note": "sin delta"}


def test_truncated_object_salvages_the_complete_items_before_the_cut():
    text = '{"new_facts": [{"text": "algo completo"}], "clock_ticks": [{"ref": "C1", "ticks": '
    result = jsonx.extract_json(text)
    assert result["new_facts"] == [{"text": "algo completo"}]


def test_truncated_mid_string_value_still_salvages_earlier_items():
    text = '{"new_facts": [{"text": "algo completo"}], "scene": {"mood": "ten'
    result = jsonx.extract_json(text)
    assert result["new_facts"] == [{"text": "algo completo"}]


def test_well_formed_json_is_not_altered_by_the_repair_path():
    # The repair path must never be reached (and never change the result)
    # when the object is already complete.
    assert jsonx._repair_truncated('{"a": 1}') is None
