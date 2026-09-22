"""Unit tests for world_check's rule-based and LLM-judge conflict detection."""
from __future__ import annotations

import pytest

from scheherazades_hoard import consistency, db, store


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture()
def world(conn):
    return store.create_world(conn, "W")


async def test_dead_character_acting_is_flagged(conn, world):
    store.create_entity(conn, world["id"], "character", "Marisol", status="dead")
    result = await consistency.world_check(conn, world["id"], "Marisol camina hacia el barco")
    assert result["consistent"] is False
    assert result["conflicts"][0]["fact_id"] == "E1"


async def test_location_mismatch_is_flagged(conn, world):
    tomas = store.create_entity(conn, world["id"], "character", "Tomas")
    puerto = store.create_entity(conn, world["id"], "location", "Puerto Salado")
    faro = store.create_entity(conn, world["id"], "location", "El Faro")
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(
        conn, world["id"], sess["id"], "narration", "narrator", text="x",
        scene={"location": puerto["ref"], "present": [tomas["id"]]},
    )
    result = await consistency.world_check(conn, world["id"], "Tomas esta en El Faro")
    assert result["consistent"] is False
    assert "Puerto Salado" in result["conflicts"][0]["why"]


async def test_relation_contradiction_is_flagged(conn, world):
    a = store.create_entity(conn, world["id"], "character", "Ana")
    b = store.create_entity(conn, world["id"], "character", "Beto")
    store.create_relation(conn, world["id"], a["id"], b["id"], "ama a")
    result = await consistency.world_check(conn, world["id"], "Ana odia a Beto")
    assert result["consistent"] is False
    assert any("odia a" in c["why"] for c in result["conflicts"])


async def test_consistent_statement_has_no_conflicts(conn, world):
    store.create_entity(conn, world["id"], "character", "Ana")
    result = await consistency.world_check(conn, world["id"], "Todo esta tranquilo esta noche")
    assert result["consistent"] is True
    assert result["conflicts"] == []


async def test_llm_judge_conflict_is_merged_when_fact_id_is_valid(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Ana")
    store.create_fact(conn, world["id"], "Ana nunca ha salido de su pueblo natal", entity_ids=[e["id"]])

    async def fake_chat(prompt: str) -> str:
        return '{"conflicts": [{"fact_id": "F1", "why": "Ana would not be abroad"}]}'

    result = await consistency.world_check(conn, world["id"], "Ana llega a un pais lejano", chat_fn=fake_chat)
    assert result["consistent"] is False
    assert result["conflicts"][0]["fact_id"] == "F1"


async def test_llm_judge_hallucinated_fact_id_is_ignored(conn, world):
    store.create_entity(conn, world["id"], "character", "Ana")

    async def fake_chat(prompt: str) -> str:
        return '{"conflicts": [{"fact_id": "F999", "why": "made up"}]}'

    result = await consistency.world_check(conn, world["id"], "Ana hace algo", chat_fn=fake_chat)
    assert all(c["fact_id"] != "F999" for c in result["conflicts"])


async def test_llm_judge_unparseable_output_does_not_crash(conn, world):
    store.create_entity(conn, world["id"], "character", "Ana")

    async def fake_chat(prompt: str) -> str:
        return "not json at all"

    result = await consistency.world_check(conn, world["id"], "algo pasa", chat_fn=fake_chat)
    assert result["consistent"] is True


# --- regressions found in review ------------------------------------------

async def test_short_names_match_whole_words_only(conn, world):
    store.create_entity(conn, world["id"], "character", "Ana", status="dead")
    result = await consistency.world_check(conn, world["id"], "Marisol abre la ventana del faro.")
    assert result["consistent"] is True


async def test_dead_character_found_by_alias(conn, world):
    store.create_entity(conn, world["id"], "character", "Ulla Vessane", aliases=["la Reina"], status="dead")
    result = await consistency.world_check(conn, world["id"], "La Reina ordena zarpar.")
    assert result["consistent"] is False
    assert result["conflicts"][0]["fact_id"] == "E1"


async def test_talking_about_the_dead_is_not_a_conflict(conn, world):
    store.create_entity(conn, world["id"], "character", "Ulla", status="dead")
    result = await consistency.world_check(conn, world["id"], "Marisol visita la tumba de Ulla.")
    assert result["consistent"] is True


async def test_undone_turn_does_not_set_last_known_location(conn, world):
    from scheherazades_hoard import delta
    port = store.create_entity(conn, world["id"], "location", "Puerto")
    faro = store.create_entity(conn, world["id"], "location", "Faro")
    iria = store.create_entity(conn, world["id"], "character", "Iria")
    sess = store.get_or_create_current_session(conn, world["id"])
    delta.record_turn(conn, world["id"], sess["id"], {"scene": {"location": port["ref"], "present": [iria["ref"]]}}, "narration", "narrator", text="a")
    turn, _, _ = delta.record_turn(conn, world["id"], sess["id"], {"scene": {"location": faro["ref"]}}, "narration", "narrator", text="b")
    delta.undo_last(conn, world["id"], turn)
    result = await consistency.world_check(conn, world["id"], "Iria espera en el Puerto.")
    assert result["consistent"] is True


async def test_result_says_whether_the_llm_judge_ran(conn, world):
    store.create_fact(conn, world["id"], "El faro está apagado")
    result = await consistency.world_check(conn, world["id"], "El faro brilla")
    assert result["llm_judge"] == "not_configured"

    async def failing(prompt):
        raise RuntimeError("no model")

    result = await consistency.world_check(conn, world["id"], "El faro brilla", chat_fn=failing)
    assert result["llm_judge"] == "unavailable"
