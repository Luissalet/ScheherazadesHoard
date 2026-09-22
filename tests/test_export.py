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


# --- usability report #5: the chapter must be manuscript-clean -------------

def test_chapter_drops_ooc_and_roll_lines(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(conn, world["id"], sess["id"], "narration", "narrator", text="La niebla cubre el puerto.")
    store.append_turn(conn, world["id"], sess["id"], "ooc", "user", text="¿hacemos una pausa?")
    store.append_turn(
        conn, world["id"], sess["id"], "roll", "agent", text="tirada de sigilo",
        rolls=[{"expression": "2d6+1", "total": 9, "band": "strong_hit"}],
    )
    md = export.session_to_markdown(conn, world["id"])
    assert "niebla" in md
    assert "pausa" not in md and "OOC" not in md
    assert "strong_hit" not in md and "2d6" not in md and "sigilo" not in md


def test_chapter_renders_actions_in_italics_not_as_a_blockquote(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(conn, world["id"], sess["id"], "action", "user", text="Iria abre la puerta.")
    md = export.session_to_markdown(conn, world["id"])
    assert "*Iria abre la puerta.*" in md
    assert "> Iria" not in md


def test_chapter_leaves_raya_dialogue_untouched(conn, world):
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(conn, world["id"], sess["id"], "dialogue", "narrator", text="—Vamos —dijo Iria.")
    md = export.session_to_markdown(conn, world["id"])
    assert "—Vamos —dijo Iria." in md
    assert "“—Vamos" not in md


def test_chapter_gives_model_dialogue_its_opening_raya(conn, world):
    # What a model actually sends: the spoken words with a raya aside,
    # but no opening dash. A Spanish chapter must not wrap it in quotes.
    sess = store.get_or_create_current_session(conn, world["id"])
    store.append_turn(conn, world["id"], sess["id"], "dialogue", "narrator",
                      text="No ha vuelto desde el martes —dice Rosalía—. Y su farol sigue apagado.")
    store.append_turn(conn, world["id"], sess["id"], "dialogue", "narrator", text="Vamos ya.")
    md = export.session_to_markdown(conn, world["id"])
    assert "—No ha vuelto desde el martes —dice Rosalía—. Y su farol sigue apagado." in md
    assert "—Vamos ya." in md
    assert "“" not in md and "”" not in md


def test_chapter_quotes_plain_dialogue_in_an_english_world(conn):
    w = store.create_world(conn, "Harbour", language="en")
    sess = store.get_or_create_current_session(conn, w["id"])
    store.append_turn(conn, w["id"], sess["id"], "dialogue", "narrator", text="Let's go.")
    md = export.session_to_markdown(conn, w["id"])
    assert "“Let's go.”" in md


def test_chapter_title_is_the_sessions_own_localized_default(conn, world):
    md = export.session_to_markdown(conn, world["id"])
    assert md.startswith("# Sesión 1")


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


def test_json_backup_keeps_the_sessions_and_their_story(conn, world):
    # A backup that re-imported the world but not the play history lost
    # every night of play (found in the second walkthrough of UC7).
    iria = store.create_entity(conn, world["id"], "character", "Iria")
    hospicio = store.create_entity(conn, world["id"], "location", "Hospicio")
    s1 = store.start_session(conn, world["id"], "La primera noche")
    store.append_turn(conn, world["id"], s1["id"], "narration", "narrator", text="La niebla sube.",
                      scene={"location": hospicio["id"], "present": [iria["id"]], "mood": "tenso"})
    gone = store.append_turn(conn, world["id"], s1["id"], "narration", "narrator", text="Iria muere.")
    store.mark_turn_undone(conn, gone["id"])

    imported = export.import_world_json(conn, export.export_world_json(conn, world["id"]))

    sessions = store.list_sessions(conn, imported["id"])
    assert [s["title"] for s in sessions] == ["La primera noche"]
    turns = store.list_turns(conn, sessions[0]["id"])
    assert [t["text"] for t in turns] == ["La niebla sube.", "Iria muere."]
    assert turns[1]["undone"] is True
    new_iria = store.get_entity(conn, imported["id"], "Iria")
    assert store.current_scene(conn, imported["id"])["present"] == [new_iria["id"]]
    md = export.session_to_markdown(conn, imported["id"], sessions[0]["id"])
    assert "La niebla sube." in md and "Iria muere." not in md
    # nothing imported is current, so undo can never reach an imported turn
    assert store.get_current_session(conn, imported["id"]) is None


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
