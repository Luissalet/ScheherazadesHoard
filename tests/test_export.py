"""Unit tests for Markdown and JSON export/import."""
from __future__ import annotations

import pytest

from scheherazades_hoard import db, export, store


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture()
def world(conn):
    return store.create_world(conn, "Archipielago", premise="reino hundido", genre="fantasy")


def test_session_markdown_merges_turns(conn, world):
    e = store.create_entity(conn, world["id"], "character", "Marisol")
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(conn, world["id"], sess["id"], "narration", "narrator", text="La niebla cubre el puerto.")
    store.append_turn(conn, world["id"], sess["id"], "dialogue", "user", text="Vamos al barco.")
    md = export.session_to_markdown(conn, world["id"])
    assert "niebla" in md
    assert "Vamos al barco" in md
    assert md.startswith("#")


def test_session_markdown_excludes_undone_turns(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    t1 = store.append_turn(conn, world["id"], sess["id"], "narration", "narrator", text="visible")
    t2 = store.append_turn(conn, world["id"], sess["id"], "narration", "narrator", text="invisible-after-undo")
    store.mark_turn_undone(conn, t2["id"])
    md = export.session_to_markdown(conn, world["id"])
    assert "visible" in md
    assert "invisible-after-undo" not in md


def test_bible_has_one_section_per_kind(conn, world):
    store.create_entity(conn, world["id"], "character", "Marisol")
    store.create_entity(conn, world["id"], "location", "Puerto Salado")
    store.create_entity(conn, world["id"], "faction", "Los Hundidos")
    bible = export.world_bible_markdown(conn, world["id"])
    assert "## Characters" in bible
    assert "## Locations" in bible
    assert "## Factions" in bible
    assert "## Items" not in bible  # no items created


def test_bible_excludes_secrets_by_default(conn, world):
    store.create_entity(conn, world["id"], "character", "Marisol", secrets="es una espia")
    bible = export.world_bible_markdown(conn, world["id"])
    assert "espia" not in bible


def test_bible_includes_secrets_when_requested(conn, world):
    store.create_entity(conn, world["id"], "character", "Marisol", secrets="es una espia")
    bible = export.world_bible_markdown(conn, world["id"], include_secrets=True)
    assert "espia" in bible
    assert "[GM secret]" in bible


def test_json_export_import_roundtrip(conn, world):
    e1 = store.create_entity(conn, world["id"], "character", "Marisol", fields={"hp": 10})
    e2 = store.create_entity(conn, world["id"], "location", "Puerto Salado")
    store.create_relation(conn, world["id"], e1["id"], e2["id"], "vive en")
    store.create_fact(conn, world["id"], "Marisol vive en el puerto", entity_ids=[e1["id"]], canon=True)
    store.create_thread(conn, world["id"], "Un misterio")
    c = store.create_clock(conn, world["id"], "Tormenta", segments=4)
    store.tick_clock(conn, world["id"], c["ref"], 2)
    store.create_table(conn, world["id"], "Rumores", [{"text": "algo"}])

    data = export.export_world_json(conn, world["id"])
    imported = export.import_world_json(conn, data)

    assert imported["id"] != world["id"]
    entities = store.list_entities(conn, imported["id"])
    assert len(entities) == 2
    marisol = next(e for e in entities if e["name"] == "Marisol")
    assert marisol["fields"] == {"hp": 10}
    assert len(store.list_relations(conn, imported["id"])) == 1
    assert len(store.list_facts(conn, imported["id"])) == 1
    assert len(store.list_threads(conn, imported["id"])) == 1
    clocks = store.list_clocks(conn, imported["id"])
    assert clocks[0]["filled"] == 2
    assert len(store.list_tables(conn, imported["id"])) == 1


def test_import_rejects_wrong_format(conn):
    with pytest.raises(ValueError):
        export.import_world_json(conn, {"format": "something-else"})


async def test_polished_markdown_falls_back_on_chat_failure(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(conn, world["id"], sess["id"], "narration", "narrator", text="algo pasa")

    async def broken_chat(prompt: str) -> str:
        raise RuntimeError("backend down")

    result = await export.session_to_markdown_polished(conn, world["id"], None, broken_chat)
    assert "algo pasa" in result


async def test_polished_markdown_uses_chat_output(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(conn, world["id"], sess["id"], "narration", "narrator", text="algo pasa")

    async def fake_chat(prompt: str) -> str:
        return "Una prosa mas elegante sobre lo que paso."

    result = await export.session_to_markdown_polished(conn, world["id"], None, fake_chat)
    assert "elegante" in result
