"""Unit tests for weighted random tables and nested references."""
from __future__ import annotations

import pytest

from scheherazades_hoard import db, store, tables


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture()
def world(conn):
    return store.create_world(conn, "W")


def test_roll_table_picks_an_entry(conn, world):
    store.create_table(conn, world["id"], "Rumores", [{"text": "algo"}, {"text": "nada"}])
    result = tables.roll_table(conn, world["id"], "Rumores", seed=1)
    assert result["text"] in ("algo", "nada")
    assert result["rolls"][0]["table"] == "Rumores"


def test_roll_table_is_seed_reproducible(conn, world):
    store.create_table(
        conn, world["id"], "Clima",
        [{"text": "lluvia", "weight": 1}, {"text": "sol", "weight": 1}, {"text": "niebla", "weight": 1}],
    )
    a = tables.roll_table(conn, world["id"], "Clima", seed=99)
    b = tables.roll_table(conn, world["id"], "Clima", seed=99)
    assert a["text"] == b["text"]


def test_weight_zero_entries_never_chosen(conn, world):
    store.create_table(conn, world["id"], "Sesgada", [{"text": "siempre", "weight": 10}, {"text": "nunca", "weight": 0}])
    for seed in range(20):
        result = tables.roll_table(conn, world["id"], "Sesgada", seed=seed)
        assert result["text"] == "siempre"


def test_nested_table_reference_resolves(conn, world):
    store.create_table(conn, world["id"], "Interior", [{"text": "un cofre"}])
    store.create_table(conn, world["id"], "Exterior", [{"text": "encuentras [[Interior]]"}])
    result = tables.roll_table(conn, world["id"], "Exterior", seed=1)
    assert result["text"] == "encuentras un cofre"
    assert [r["table"] for r in result["rolls"]] == ["Exterior", "Interior"]


def test_cyclic_table_reference_raises(conn, world):
    store.create_table(conn, world["id"], "A", [{"text": "va a [[B]]"}])
    store.create_table(conn, world["id"], "B", [{"text": "vuelve a [[A]]"}])
    with pytest.raises(tables.TableError):
        tables.roll_table(conn, world["id"], "A", seed=1)


def test_unknown_table_raises_not_found(conn, world):
    with pytest.raises(store.NotFound):
        tables.roll_table(conn, world["id"], "No existe", seed=1)


def test_empty_table_is_refused_at_creation(conn, world):
    # refused when it is written, not later in the middle of a scene
    with pytest.raises(ValueError):
        store.create_table(conn, world["id"], "Vacia", [])


def test_all_zero_weights_are_refused(conn, world):
    with pytest.raises(ValueError):
        store.create_table(conn, world["id"], "Nada", [{"text": "a", "weight": 0}])
