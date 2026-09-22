"""Unit tests for the --demo seed data ("El Archipiélago de Sal")."""
from __future__ import annotations

import pytest

from scheherazades_hoard import db, demo, store


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "demo.db")
    yield c
    c.close()


def test_seed_creates_expected_shape(conn):
    world = demo.seed_demo_world(conn)
    assert world["ruleset"] == "pbta_2d6"
    assert world["language"] == "es"

    entities = store.list_entities(conn, world["id"])
    assert len(entities) == 14
    characters = [e for e in entities if e["kind"] == "character"]
    assert len(characters) == 5
    assert all(e["secrets"] for e in characters)
    assert len([e for e in entities if e["kind"] == "location"]) == 4
    assert len([e for e in entities if e["kind"] == "faction"]) == 2

    assert len(store.list_threads(conn, world["id"])) == 3
    assert len(store.list_clocks(conn, world["id"])) == 2
    assert len(store.list_tables(conn, world["id"])) == 2

    sessions = store.list_sessions(conn, world["id"])
    assert len(sessions) == 1
    turns = store.list_turns(conn, sessions[0]["id"])
    assert len(turns) >= 10
    assert any(t["role"] == "roll" for t in turns)
    assert any(t["delta"] for t in turns)


def test_seed_is_idempotent(conn):
    w1 = demo.seed_demo_world(conn)
    w2 = demo.seed_demo_world(conn)
    assert w1["id"] == w2["id"]
    assert len(store.list_worlds(conn)) == 1


def test_seed_has_no_real_world_names(conn):
    world = demo.seed_demo_world(conn)
    banned = {"tolkien", "narnia", "westeros", "middle-earth", "hogwarts"}
    text = (world["premise"] + world["name"]).lower()
    assert not any(b in text for b in banned)
