"""Unit tests for delta validation, atomic apply, and undo."""
from __future__ import annotations

import pytest

from scheherazades_hoard import db, delta, store


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture()
def world(conn):
    return store.create_world(conn, "W")


@pytest.fixture()
def session(conn, world):
    return store.get_or_create_current_session(conn, world["id"])


def test_unknown_entity_update_is_rejected(conn, world):
    valid, rejected = delta.validate_delta(conn, world["id"], {"entity_updates": [{"ref": "E99", "summary": "x"}]})
    assert valid["entity_updates"] == []
    assert rejected[0]["category"] == "entity_updates"


def test_dead_character_cannot_be_present(conn, world):
    ghost = store.create_entity(conn, world["id"], "character", "Fantasma", status="dead")
    valid, rejected = delta.validate_delta(conn, world["id"], {"scene": {"present": [ghost["ref"]]}})
    assert valid["scene"]["present"] == []
    assert "dead" in rejected[0]["reason"]


def test_move_to_unknown_location_is_rejected(conn, world):
    valid, rejected = delta.validate_delta(conn, world["id"], {"scene": {"location": "E99", "present": []}})
    assert valid["scene"] is None
    assert rejected[0]["category"] == "scene"


def test_move_to_non_location_entity_is_rejected(conn, world):
    char = store.create_entity(conn, world["id"], "character", "Ana")
    valid, rejected = delta.validate_delta(conn, world["id"], {"scene": {"location": char["ref"]}})
    assert valid["scene"] is None
    assert rejected


def test_relation_with_unknown_entity_is_rejected(conn, world):
    ana = store.create_entity(conn, world["id"], "character", "Ana")
    valid, rejected = delta.validate_delta(
        conn, world["id"], {"relations": [{"a": ana["ref"], "b": "E99", "type": "odia a"}]}
    )
    assert valid["relations"] == []
    assert rejected[0]["category"] == "relations"


def test_new_entity_can_be_referenced_same_delta(conn, world):
    d = {
        "new_entities": [{"kind": "character", "name": "Nuevo"}],
        "new_facts": [{"text": "algo sobre Nuevo", "entity_ids": ["Nuevo"]}],
    }
    valid, rejected = delta.validate_delta(conn, world["id"], d)
    assert rejected == []
    assert len(valid["new_entities"]) == 1
    assert len(valid["new_facts"]) == 1


def test_apply_delta_is_atomic_and_returns_undo_snapshot(conn, world, session):
    d = {"new_entities": [{"kind": "character", "name": "Ana", "summary": "s"}]}
    valid, rejected = delta.validate_delta(conn, world["id"], d)
    result, undo = delta.apply_delta(conn, world["id"], session["id"], valid)
    assert len(result["created_entities"]) == 1
    assert len(undo["created_entities"]) == 1
    assert len(store.list_entities(conn, world["id"])) == 1


def test_undo_reverts_created_entities_facts_relations(conn, world, session):
    d = {
        "new_entities": [{"kind": "character", "name": "Ana"}, {"kind": "character", "name": "Beto"}],
        "relations": [{"a": "Ana", "b": "Beto", "type": "amigos"}],
        "new_facts": [{"text": "Ana conoce a Beto", "entity_ids": ["Ana", "Beto"]}],
    }
    valid, _ = delta.validate_delta(conn, world["id"], d)
    result, undo = delta.apply_delta(conn, world["id"], session["id"], valid)
    turn = store.append_turn(
        conn, world["id"], session["id"], "narration", "narrator",
        text="x", delta=result, applied=True, undo_snapshot=undo,
    )
    assert len(store.list_entities(conn, world["id"])) == 2
    delta.undo_last(conn, world["id"], turn)
    assert store.list_entities(conn, world["id"]) == []
    assert store.list_facts(conn, world["id"]) == []
    assert store.list_relations(conn, world["id"]) == []
    assert store.get_turn_raw(conn, turn["id"])["undone"] == 1


def test_undo_reverts_entity_update_to_previous_values(conn, world, session):
    e = store.create_entity(conn, world["id"], "character", "Ana", summary="original", status="alive")
    d = {"entity_updates": [{"ref": e["ref"], "summary": "cambiado", "status": "missing"}]}
    valid, _ = delta.validate_delta(conn, world["id"], d)
    result, undo = delta.apply_delta(conn, world["id"], session["id"], valid)
    turn = store.append_turn(
        conn, world["id"], session["id"], "narration", "narrator",
        text="x", delta=result, applied=True, undo_snapshot=undo,
    )
    changed = store.get_entity(conn, world["id"], e["id"])
    assert changed["summary"] == "cambiado"
    assert changed["status"] == "missing"
    delta.undo_last(conn, world["id"], turn)
    restored = store.get_entity(conn, world["id"], e["id"])
    assert restored["summary"] == "original"
    assert restored["status"] == "alive"


def test_undo_reverts_clock_tick(conn, world, session):
    c = store.create_clock(conn, world["id"], "Tormenta", segments=4)
    d = {"clock_ticks": [{"ref": c["ref"], "ticks": 3}]}
    valid, _ = delta.validate_delta(conn, world["id"], d)
    result, undo = delta.apply_delta(conn, world["id"], session["id"], valid)
    turn = store.append_turn(
        conn, world["id"], session["id"], "narration", "narrator",
        text="x", delta=result, applied=True, undo_snapshot=undo,
    )
    assert store.get_clock(conn, world["id"], c["ref"])["filled"] == 3
    delta.undo_last(conn, world["id"], turn)
    assert store.get_clock(conn, world["id"], c["ref"])["filled"] == 0


def test_undo_reverts_thread_status_change(conn, world, session):
    th = store.create_thread(conn, world["id"], "Un misterio", status="open")
    d = {"thread_changes": [{"ref": th["ref"], "status": "resolved"}]}
    valid, _ = delta.validate_delta(conn, world["id"], d)
    result, undo = delta.apply_delta(conn, world["id"], session["id"], valid)
    turn = store.append_turn(
        conn, world["id"], session["id"], "narration", "narrator",
        text="x", delta=result, applied=True, undo_snapshot=undo,
    )
    assert store.get_thread(conn, world["id"], th["ref"])["status"] == "resolved"
    delta.undo_last(conn, world["id"], turn)
    assert store.get_thread(conn, world["id"], th["ref"])["status"] == "open"


def test_thread_changes_can_create_new_thread(conn, world, session):
    d = {"thread_changes": [{"ref": "no-existe", "create": True, "title": "Hilo nuevo"}]}
    valid, rejected = delta.validate_delta(conn, world["id"], d)
    assert rejected == []
    result, _ = delta.apply_delta(conn, world["id"], session["id"], valid)
    assert result["thread_changes"][0]["title"] == "Hilo nuevo"


def test_empty_delta_applies_cleanly(conn, world, session):
    valid, rejected = delta.validate_delta(conn, world["id"], {})
    result, undo = delta.apply_delta(conn, world["id"], session["id"], valid)
    assert rejected == []
    assert result["created_entities"] == []
