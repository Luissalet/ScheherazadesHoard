"""Unit tests for the SQLite store layer."""
from __future__ import annotations

import pytest

from scheherazades_hoard import db, store


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture()
def world(conn):
    return store.create_world(conn, "Prueba", genre="fantasy", ruleset="pbta_2d6", language="es")


def test_create_and_resolve_world_by_name(conn, world):
    assert store.resolve_world_id(conn, world["name"]) == world["id"]
    assert store.resolve_world_id(conn, world["id"]) == world["id"]
    with pytest.raises(store.NotFound):
        store.resolve_world_id(conn, "no existe")


def test_world_rejects_unknown_ruleset(conn):
    with pytest.raises(ValueError):
        store.create_world(conn, "X", ruleset="bogus")


def test_entity_seq_refs_increment_per_world(conn, world):
    e1 = store.create_entity(conn, world["id"], "character", "Ana")
    e2 = store.create_entity(conn, world["id"], "character", "Beto")
    assert e1["ref"] == "E1"
    assert e2["ref"] == "E2"


def test_entity_resolves_by_id_ref_and_alias(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol", aliases=["La Capitana"])
    assert store.get_entity(conn, world["id"], e["id"])["id"] == e["id"]
    assert store.get_entity(conn, world["id"], e["ref"])["id"] == e["id"]
    assert store.get_entity(conn, world["id"], "marisol")["id"] == e["id"]
    assert store.get_entity(conn, world["id"], "la capitana")["id"] == e["id"]


def test_entity_rejects_unknown_kind(conn, world):
    with pytest.raises(ValueError):
        store.create_entity(conn, world["id"], "spaceship", "Nave")


def test_entity_requires_name(conn, world):
    with pytest.raises(ValueError):
        store.create_entity(conn, world["id"], "character", "  ")


def test_upsert_entity_updates_existing(conn, world):
    store.create_entity(conn, world["id"], "character", "Marisol", summary="v1")
    updated = store.upsert_entity(conn, world["id"], "character", "Marisol", summary="v2")
    all_e = store.list_entities(conn, world["id"])
    assert len(all_e) == 1
    assert updated["summary"] == "v2"


def test_update_entity_fields_patch_merges(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol", fields={"hp": 10, "str": 2})
    updated = store.update_entity(conn, world["id"], e["id"], fields_patch={"hp": 5})
    assert updated["fields"] == {"hp": 5, "str": 2}


def test_search_facts_ignores_spanish_accents(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol")
    store.create_fact(conn, world["id"], "Marisol perdio un ojo en la guerra", entity_ids=[e["id"]])
    hits_with_accent = store.search_facts(conn, world["id"], "perdió")
    hits_without = store.search_facts(conn, world["id"], "perdio")
    assert len(hits_with_accent) == 1
    assert len(hits_without) == 1


def test_search_world_returns_entities_and_facts(conn, world):
    e = store.create_entity(conn, world["id"], "location", "Puerto Salado", description="un muelle roto")
    store.create_fact(conn, world["id"], "El Puerto Salado se hunde cada invierno", entity_ids=[e["id"]])
    result = store.search_world(conn, world["id"], "puerto")
    assert len(result["entities"]) == 1
    assert len(result["facts"]) == 1


def test_thread_lifecycle(conn, world):
    th = store.create_thread(conn, world["id"], "Quien robo el mapa?")
    assert th["status"] == "open"
    updated = store.update_thread(conn, world["id"], th["ref"], status="resolved", note="fue el mayordomo")
    assert updated["status"] == "resolved"
    assert "mayordomo" in updated["notes"]
    with pytest.raises(ValueError):
        store.update_thread(conn, world["id"], th["ref"], status="bogus")


def test_clock_tick_clamps_to_segments(conn, world):
    c = store.create_clock(conn, world["id"], "Cuenta atras", segments=4)
    store.tick_clock(conn, world["id"], c["ref"], 10)
    full = store.get_clock(conn, world["id"], c["ref"])
    assert full["filled"] == 4
    assert full["full"] is True


def test_clock_rejects_bad_segments(conn, world):
    with pytest.raises(ValueError):
        store.create_clock(conn, world["id"], "Bad", segments=5)


def test_turns_increment_idx_within_session(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    t1 = store.append_turn(conn, world["id"], sess["id"], "narration", "narrator", text="uno")
    t2 = store.append_turn(conn, world["id"], sess["id"], "action", "user", text="dos")
    assert t1["idx"] == 0
    assert t2["idx"] == 1
    assert store.get_last_turn(conn, world["id"], sess["id"])["id"] == t2["id"]


def test_turn_rejects_bad_role(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    with pytest.raises(ValueError):
        store.append_turn(conn, world["id"], sess["id"], "bogus", "user")


def test_new_session_default_title_is_localized(conn, world):
    sess = store.start_session(conn, world["id"])
    assert sess["title"] == "Sesión 1"
    sess2 = store.start_session(conn, world["id"])
    assert sess2["title"] == "Sesión 2"


def test_new_session_default_title_in_english_world(conn):
    w = store.create_world(conn, "Test", language="en")
    sess = store.start_session(conn, w["id"])
    assert sess["title"] == "Session 1"


def test_start_session_accepts_an_explicit_title(conn, world):
    sess = store.start_session(conn, world["id"], title="La noche del faro")
    assert sess["title"] == "La noche del faro"
    assert store.resolve_session_id(conn, world["id"], "la noche del faro") == sess["id"]


def test_rename_session_updates_title_and_stays_findable_by_it(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    renamed = store.rename_session(conn, world["id"], sess["id"], "  Anoche en el puerto  ")
    assert renamed["title"] == "Anoche en el puerto"
    assert store.resolve_session_id(conn, world["id"], "anoche en el puerto") == sess["id"]


def test_rename_session_rejects_a_blank_title(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    with pytest.raises(ValueError):
        store.rename_session(conn, world["id"], sess["id"], "   ")


def test_dice_log_roundtrip(conn):
    entry = store.log_dice(conn, "2d6+3", 10, [{"sides": 6, "value": 4}], seed=1, reason="ataque", who="agent")
    assert entry["result"] == 10
    log = store.list_dice_log(conn)
    assert log[0]["id"] == entry["id"]


def test_list_worlds_includes_counts(conn, world):
    store.create_entity(conn, world["id"], "character", "Ana")
    worlds = store.list_worlds(conn)
    assert worlds[0]["counts"]["entities"] == 1
