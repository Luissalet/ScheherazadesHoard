"""Unit tests for the world_context builder — the heart of the app."""
from __future__ import annotations

import pytest

from scheherazades_hoard import context, db, store


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture()
def world(conn):
    return store.create_world(conn, "Archipielago", premise="Un reino hundido", language="es")


def test_secrets_excluded_by_default(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol", secrets="es una espia")
    ctx = context.world_context(conn, world["id"], scene={"present": [e["ref"]]})
    assert "espia" not in ctx["brief"]
    assert "secrets" not in ctx["scene"]["present"][0]


def test_secrets_included_when_requested_and_tagged_gm(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol", secrets="es una espia")
    ctx = context.world_context(conn, world["id"], scene={"present": [e["ref"]]}, include_secrets=True)
    assert "[GM]" in ctx["brief"]
    assert "espia" in ctx["brief"]


def test_budget_is_respected(conn, world):
    e1 = store.create_entity(conn, world["id"], "character", "Marisol", summary="capitana " * 20)
    e2 = store.create_entity(conn, world["id"], "character", "Tomas", summary="oficial " * 20)
    for i in range(20):
        store.create_fact(conn, world["id"], f"Hecho numero {i} sobre el mundo entero", entity_ids=[e1["id"]])
    ctx = context.world_context(conn, world["id"], scene={"present": [e1["ref"], e2["ref"]]}, budget_chars=400)
    assert ctx["used_chars"] <= 400
    assert len(ctx["brief"]) <= 400 + 50  # small slack for the always-required header lines


def test_larger_budget_includes_more_facts(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol")
    for i in range(15):
        store.create_fact(conn, world["id"], f"Hecho {i} sobre Marisol y su barco", entity_ids=[e["id"]])
    small = context.world_context(conn, world["id"], scene={"present": [e["ref"]]}, budget_chars=250)
    large = context.world_context(conn, world["id"], scene={"present": [e["ref"]]}, budget_chars=4000)
    assert len(large["lore"]) >= len(small["lore"])
    assert small["truncated"] is True


def test_canon_facts_rank_above_noncanon(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol")
    store.create_fact(conn, world["id"], "Marisol es zurda (rumor sin confirmar)", entity_ids=[e["id"]], canon=False)
    store.create_fact(conn, world["id"], "Marisol perdio un ojo (confirmado)", entity_ids=[e["id"]], canon=True)
    ctx = context.world_context(conn, world["id"], scene={"present": [e["ref"]]}, budget_chars=4000)
    refs_in_order = [f["ref"] for f in ctx["lore"]]
    canon_ref = [f["ref"] for f in ctx["lore"] if f["canon"]][0]
    assert refs_in_order.index(canon_ref) == 0


def test_ranking_is_deterministic_across_calls(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol")
    for i in range(8):
        store.create_fact(conn, world["id"], f"Hecho {i}", entity_ids=[e["id"]], canon=(i % 2 == 0))
    a = context.world_context(conn, world["id"], scene={"present": [e["ref"]]})
    b = context.world_context(conn, world["id"], scene={"present": [e["ref"]]})
    assert [f["ref"] for f in a["lore"]] == [f["ref"] for f in b["lore"]]


def test_ids_present_for_citation(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol")
    th = store.create_thread(conn, world["id"], "Un misterio")
    store.create_fact(conn, world["id"], "Un hecho cualquiera", entity_ids=[e["id"]])
    ctx = context.world_context(conn, world["id"], scene={"present": [e["ref"]]})
    assert ctx["scene"]["present"][0]["ref"] == "E1"
    assert ctx["lore"][0]["ref"] == "F1"
    assert ctx["threads"][0]["ref"] == "T1"


def test_open_threads_touching_present_entities_are_preferred(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol")
    store.create_entity(conn, world["id"], "character", "Tomas")
    store.create_thread(conn, world["id"], "El secreto de Marisol")
    store.create_thread(conn, world["id"], "Un tema sin relacion")
    ctx = context.world_context(conn, world["id"], scene={"present": [e["ref"]]})
    titles = [t["title"] for t in ctx["threads"]]
    assert titles == ["El secreto de Marisol"]


def test_clocks_near_full_are_surfaced(conn, world):
    c1 = store.create_clock(conn, world["id"], "Casi lista", segments=4)
    store.tick_clock(conn, world["id"], c1["ref"], 3)
    c2 = store.create_clock(conn, world["id"], "Recien empezada", segments=4)
    store.tick_clock(conn, world["id"], c2["ref"], 1)
    ctx = context.world_context(conn, world["id"])
    names = [c["name"] for c in ctx["clocks"]]
    assert "Casi lista" in names
    assert "Recien empezada" not in names


def test_no_scene_falls_back_gracefully(conn, world):
    ctx = context.world_context(conn, world["id"])
    assert ctx["scene"]["present"] == []
    assert "WORLD:" in ctx["brief"]


# --- regressions found in review ------------------------------------------

def test_advanced_threads_stay_in_the_brief(conn, world):
    th = store.create_thread(conn, world["id"], "La fiebre de Tomás")
    store.update_thread(conn, world["id"], th["ref"], status="advanced")
    store.create_thread(conn, world["id"], "Resuelto", status="resolved")
    ctx = context.world_context(conn, world["id"])
    assert [t["title"] for t in ctx["threads"]] == ["La fiebre de Tomás"]
    assert "(advanced)" in ctx["brief"]


def test_newer_fact_wins_a_tie(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Iria")
    store.create_fact(conn, world["id"], "Iria viste de gris", entity_ids=[e["id"]])
    store.create_fact(conn, world["id"], "Iria viste de rojo", entity_ids=[e["id"]])
    ctx = context.world_context(conn, world["id"], scene={"present": [e["ref"]]})
    assert ctx["lore"][0]["text"] == "Iria viste de rojo"


def test_tiny_budget_is_respected_even_with_a_long_premise(conn):
    w = store.create_world(conn, "Mundo con un nombre bastante largo", premise="p " * 400,
                           content_lines=["linea " * 30], content_veils=["velo " * 30])
    ctx = context.world_context(conn, w["id"], budget_chars=200)
    assert len(ctx["brief"]) <= 200
    assert ctx["used_chars"] <= 200
    assert "BOUNDARIES" in ctx["brief"]  # safety lines are clipped, never dropped


def test_world_context_is_read_only(conn, world):
    context.world_context(conn, world["id"])
    assert store.list_sessions(conn, world["id"]) == []


def test_structured_present_has_no_trait_dump(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Iria", fields={f"k{i}": i for i in range(30)})
    ctx = context.world_context(conn, world["id"], scene={"present": [e["ref"]]})
    assert set(ctx["scene"]["present"][0]) == {"ref", "name", "kind", "status", "summary"}


def test_no_empty_section_headers_when_the_budget_runs_out(conn, world):
    for i in range(30):
        store.create_fact(conn, world["id"], f"hecho número {i} " + "x" * 80, canon=True)
    store.create_thread(conn, world["id"], "Un hilo")
    ctx = context.world_context(conn, world["id"], budget_chars=600)
    lines = ctx["brief"].splitlines()
    for i, line in enumerate(lines):
        if line.endswith(":") and line.isupper():
            assert i + 1 < len(lines) and lines[i + 1].startswith("  "), ctx["brief"]
    assert ctx["truncated"] is True
