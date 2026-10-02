"""hoard.world/1: export, and an import that is idempotent, never deletes and never overwrites local edits."""
from __future__ import annotations

import copy
import json

import pytest

from scheherazades_hoard import db, exchange, store


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "x.db")
    yield c
    c.close()


@pytest.fixture()
def world(conn):
    w = store.create_world(conn, "Archipiélago", genre="fantasía", tone="melancólico", premise="Un reino hundido", language="es")
    wid = w["id"]
    ana = store.create_entity(conn, wid, "character", "Ana", aliases=["la capitana"], summary="Capitana del faro", description="Alta y seria.",
                              fields={"edad": 34, "rango": "capitana", "stats": {"fuerza": 3}}, secrets="Ana es la espía del rey", tags=["marina"],
                              images=["data:image/png;base64,AAAA"])
    beto = store.create_entity(conn, wid, "character", "Beto", summary="Grumete", status="muerto")
    faro = store.create_entity(conn, wid, "location", "El Faro", summary="Torre sobre el acantilado")
    cuarto = store.create_entity(conn, wid, "location", "Sala de la linterna", parent_id=faro["id"])
    liga = store.create_entity(conn, wid, "faction", "La Liga del Mar")
    espada = store.create_entity(conn, wid, "item", "Espada rota", summary="Reliquia")
    store.create_entity(conn, wid, "creature", "Kraken")
    store.create_relation(conn, wid, ana["id"], beto["id"], "mentor", note="le enseñó a navegar", since="año 3")
    store.create_relation(conn, wid, ana["id"], liga["id"], "miembro")
    store.create_timeline_event(conn, wid, "Año 1", "Se enciende el faro", entity_ids=[faro["id"], ana["id"]])
    store.create_timeline_event(conn, wid, "", "Cae el reino")
    store.create_fact(conn, wid, "Ana nunca miente", entity_ids=[ana["id"]])
    return {"id": wid, "ana": ana, "beto": beto, "faro": faro, "espada": espada}


def new_world(conn, name="Destino"):
    return store.create_world(conn, name, language="es")["id"]


def snapshot(conn, wid):
    return (
        [(e["kind"], e["name"], e["summary"], e["status"]) for e in store.list_entities(conn, wid, limit=1000)],
        [(r["type"], r["note"]) for r in store.list_relations(conn, wid)],
        [(t["in_world_date"], t["summary"]) for t in store.list_timeline(conn, wid)],
    )


def by_state(report, state):
    return [i for i in report["items"] if i["state"] == state]


def test_export_shape_and_what_it_leaves_out(conn, world):
    doc = exchange.export_world(conn, world["id"])
    assert doc["schema"] == "hoard.world/1" and doc["source"]["app"] == "scheherazade"
    assert doc["source"]["ref"] == f"hoard://scheherazade/world/{world['id']}" and doc["source"]["revision"].startswith("sha256:")
    assert doc["world"] == {"name": "Archipiélago", "genre": "fantasía", "tone": "melancólico", "premise": "Un reino hundido", "language": "es"}
    assert [c["name"] for c in doc["characters"]] == ["Ana", "Beto"]
    assert [p["name"] for p in doc["places"]] == ["El Faro", "Sala de la linterna"]
    assert [f["name"] for f in doc["factions"]] == ["La Liga del Mar"]
    assert {t["name"]: t["kind"] for t in doc["things"]} == {"Espada rota": "item", "Kraken": "creature"}
    ana = doc["characters"][0]
    assert ana["ref"] == f"hoard://scheherazade/entity/{world['ana']['id']}" and ana["aliases"] == ["la capitana"] and ana["status"] == "alive"
    assert ana["fields"] == {"edad": "34", "rango": "capitana", "stats": '{"fuerza":3}'} and ana["revision"].startswith("sha256:")
    assert doc["characters"][1]["status"] == "dead"
    assert doc["places"][1]["parent_ref"] == doc["places"][0]["ref"]
    rel = doc["relations"][0]
    assert (rel["type"], rel["note"], rel["since"], rel["from"], rel["to"]) == ("mentor", "le enseñó a navegar", "año 3", ana["ref"], doc["characters"][1]["ref"])
    assert [e["summary"] for e in doc["events"]] == ["Se enciende el faro", "Cae el reino"]
    assert doc["events"][0]["date"] == "Año 1" and set(doc["events"][0]["entities"]) == {doc["places"][0]["ref"], ana["ref"]}
    text = json.dumps(doc, ensure_ascii=False)
    for forbidden in ("espía", "data:image", "nunca miente", "secrets", "images"):
        assert forbidden not in text
    exchange.validate(doc)


def test_export_is_deterministic_and_revisions_follow_content(conn, world):
    first = exchange.export_world(conn, world["id"])
    second = exchange.export_world(conn, world["id"])
    assert first["characters"] == second["characters"] and first["source"]["revision"] == second["source"]["revision"]
    store.update_entity(conn, world["id"], world["beto"]["id"], summary="Grumete valiente")
    third = exchange.export_world(conn, world["id"])
    assert third["characters"][1]["revision"] != first["characters"][1]["revision"] and third["characters"][0]["revision"] == first["characters"][0]["revision"]
    assert third["source"]["revision"] != first["source"]["revision"]


def test_import_into_a_new_world_creates_everything(conn, world):
    doc = exchange.export_world(conn, world["id"])
    report = exchange.import_world(conn, doc)
    assert report["world_created"] is True and report["world"]["name"] == "Archipiélago (2)"
    assert report["counts"] == {"created": 11}  # 7 entities, 2 relations, 2 events
    new_id = report["world"]["id"]
    assert new_id != world["id"]
    names = {e["name"]: e for e in store.list_entities(conn, new_id, limit=100)}
    assert set(names) == {"Ana", "Beto", "El Faro", "Sala de la linterna", "La Liga del Mar", "Espada rota", "Kraken"}
    assert names["Ana"]["aliases"] == ["la capitana"] and names["Beto"]["status"] == "dead" and names["Kraken"]["kind"] == "creature"
    assert names["Ana"]["secrets"] == "" and names["Ana"]["images"] == []
    assert names["Sala de la linterna"]["parent_id"] == names["El Faro"]["id"]
    assert len(store.list_relations(conn, new_id)) == 2 and len(store.list_timeline(conn, new_id)) == 2
    event = next(t for t in store.list_timeline(conn, new_id) if t["summary"] == "Se enciende el faro")
    assert set(event["entity_ids"]) == {names["El Faro"]["id"], names["Ana"]["id"]}
    meta = store.get_world(conn, new_id)
    assert (meta["genre"], meta["tone"], meta["premise"], meta["language"]) == ("fantasía", "melancólico", "Un reino hundido", "es")


def test_reimport_is_idempotent_and_goes_to_the_same_world(conn, world):
    doc = exchange.export_world(conn, world["id"])
    first = exchange.import_world(conn, doc)
    target = first["world"]["id"]
    before = snapshot(conn, target)
    again = exchange.import_world(conn, doc)
    assert again["world_created"] is False and again["world"]["id"] == target
    assert set(again["counts"]) == {"unchanged"} and again["counts"]["unchanged"] == 11
    assert snapshot(conn, target) == before
    assert len(store.list_worlds(conn)) == 2


def test_a_changed_source_updates_untouched_records_and_spares_edited_ones(conn, world):
    doc = exchange.export_world(conn, world["id"])
    target = exchange.import_world(conn, doc)["world"]["id"]
    ana = store.get_entity(conn, target, "Ana", loose=False)
    store.update_entity(conn, target, ana["id"], summary="Editada aquí")  # a local edit after the import

    changed = copy.deepcopy(doc)
    for c in changed["characters"]:
        c["summary"] = f"{c['summary']} (v2)"
        c["revision"] = exchange.digest(c["summary"])
    changed["events"][1]["summary"] = "Cae el reino de los mares"
    changed["events"][1]["revision"] = "sha256:new-event"
    changed["relations"][0]["note"] = "ahora es su rival"
    changed["relations"][0]["revision"] = "sha256:new-rel"
    report = exchange.import_world(conn, changed)
    states = {i["name"]: i["state"] for i in report["items"] if i["section"] == "characters"}
    assert states == {"Ana": "local_modified", "Beto": "updated"}
    assert store.get_entity(conn, target, "Ana", loose=False)["summary"] == "Editada aquí"
    assert store.get_entity(conn, target, "Beto", loose=False)["summary"] == "Grumete (v2)"
    assert any(t["summary"] == "Cae el reino de los mares" for t in store.list_timeline(conn, target))
    assert any(r["note"] == "ahora es su rival" for r in store.list_relations(conn, target))
    assert by_state(report, "local_modified")[0]["reason"]
    # and importing the same changed document again changes nothing more
    assert set(exchange.import_world(conn, changed)["counts"]) <= {"unchanged", "local_modified"}


def test_an_existing_name_is_linked_not_duplicated_and_not_overwritten(conn):
    target = new_world(conn)
    store.create_entity(conn, target, "character", "Ana", summary="Mi Ana, escrita a mano")
    store.create_entity(conn, target, "location", "Mercado")
    doc = {"schema": "hoard.world/1", "source": {"app": "writer", "ref": "hoard://writer/project/p1", "revision": "sha256:a"},
           "world": {"name": "Libro"},
           "characters": [{"ref": "hoard://writer/codex/c1", "revision": "sha256:1", "name": "Ana", "summary": "Ana del libro"}],
           "places": [{"ref": "hoard://writer/codex/c2", "revision": "sha256:2", "name": "Mercado", "summary": "x"}],
           "factions": [{"ref": "hoard://writer/codex/c3", "revision": "sha256:3", "name": "Mercado"}]}
    report = exchange.import_world(conn, doc, world_id=target)
    states = {i["ref"]: i["state"] for i in report["items"]}
    assert states == {"hoard://writer/codex/c1": "linked_existing", "hoard://writer/codex/c2": "linked_existing", "hoard://writer/codex/c3": "name_collision"}
    assert [e["name"] for e in store.list_entities(conn, target, limit=10)] == ["Ana", "Mercado"]
    assert store.get_entity(conn, target, "Ana", loose=False)["summary"] == "Mi Ana, escrita a mano"
    # a later revision from the source does not overwrite the hand-written one either
    doc["characters"][0].update(summary="Ana v2", revision="sha256:1b")
    again = exchange.import_world(conn, doc, world_id=target)
    assert next(i for i in again["items"] if i["ref"] == "hoard://writer/codex/c1")["state"] == "local_modified"
    assert store.get_entity(conn, target, "Ana", loose=False)["summary"] == "Mi Ana, escrita a mano"


def test_import_never_deletes(conn, world):
    doc = exchange.export_world(conn, world["id"])
    target = exchange.import_world(conn, doc)["world"]["id"]
    store.create_entity(conn, target, "character", "Solo aquí")
    smaller = {"schema": "hoard.world/1", "source": doc["source"], "world": doc["world"], "characters": doc["characters"][:1]}
    smaller["source"] = {**doc["source"], "revision": "sha256:other"}
    exchange.import_world(conn, smaller)
    names = {e["name"] for e in store.list_entities(conn, target, limit=100)}
    assert {"Solo aquí", "Beto", "El Faro"} <= names and len(store.list_relations(conn, target)) == 2


def test_a_record_deleted_here_is_not_resurrected(conn, world):
    doc = exchange.export_world(conn, world["id"])
    target = exchange.import_world(conn, doc)["world"]["id"]
    beto = store.get_entity(conn, target, "Beto", loose=False)
    store.delete_entity(conn, beto["id"])
    again = exchange.import_world(conn, doc)
    assert next(i for i in again["items"] if i["name"] == "Beto")["reason"] == "deleted_locally"
    assert not any(e["name"] == "Beto" for e in store.list_entities(conn, target, limit=100))
    assert next(i for i in again["items"] if i["section"] == "relations" and i["state"] == "skipped")["reason"] == "endpoint_missing"


def test_a_world_importing_its_own_export_changes_nothing(conn, world):
    doc = exchange.export_world(conn, world["id"])
    before = snapshot(conn, world["id"])
    report = exchange.import_world(conn, doc, world_id=world["id"])
    assert set(report["counts"]) == {"own"} and snapshot(conn, world["id"]) == before


def test_same_as_ties_a_record_to_its_other_app_identity(conn):
    target = new_world(conn)
    doc = {"schema": "hoard.world/1", "source": {"app": "writer", "ref": "hoard://writer/project/p1"},
           "characters": [{"ref": "hoard://writer/codex/c1", "revision": "sha256:1", "name": "Ana", "summary": "x"}]}
    exchange.import_world(conn, doc, world_id=target)
    exported = exchange.export_world(conn, target)
    ana = exported["characters"][0]
    assert ana["same_as"] == ["hoard://writer/codex/c1"] and ana["ref"].startswith("hoard://scheherazade/entity/")
    # the same record coming back under its new ref is recognised through same_as
    back = {"schema": "hoard.world/1", "characters": [{"ref": "hoard://writer/codex/c1-v2", "same_as": [ana["ref"]], "revision": "sha256:z", "name": "Ana", "summary": "x"}]}
    report = exchange.import_world(conn, back, world_id=target)
    assert report["items"][0]["state"] in ("own", "updated", "local_modified") and len(store.list_entities(conn, target, limit=10)) == 1


def test_things_kinds_and_statuses_from_other_apps_are_mapped(conn):
    target = new_world(conn)
    doc = {"schema": "hoard.world/1", "things": [
        {"ref": "hoard://writer/codex/m1", "name": "Hechizo", "kind": "magic"}, {"ref": "hoard://writer/codex/i1", "name": "Llave", "kind": "object"},
        {"ref": "hoard://writer/codex/x1", "name": "Algo"}],
        "characters": [{"ref": "hoard://writer/codex/c9", "name": "Zoe", "status": "retired ", "fields": {"a": 1, "b": None, "": "x"}}]}
    exchange.import_world(conn, doc, world_id=target)
    kinds = {e["name"]: e["kind"] for e in store.list_entities(conn, target, limit=10)}
    assert kinds == {"Hechizo": "lore", "Llave": "item", "Algo": "lore", "Zoe": "character"}
    zoe = store.get_entity(conn, target, "Zoe", loose=False)
    assert zoe["status"] == "unknown" and zoe["fields"] == {"a": "1"}


def test_bad_items_are_skipped_with_a_reason_and_the_rest_goes_through(conn):
    target = new_world(conn)
    doc = {"schema": "hoard.world/1", "characters": [
        {"ref": "not-a-ref", "name": "A"}, {"ref": "hoard://writer/codex/1", "name": "  "}, {"ref": "hoard://writer/codex/2", "name": "Bien"}, "junk"],
        "relations": [{"ref": "hoard://writer/rel/1", "from": "hoard://writer/codex/2", "to": "hoard://writer/codex/2", "type": "x"},
                      {"ref": "hoard://writer/rel/2", "from": "hoard://writer/codex/2", "to": "hoard://writer/codex/404", "type": "x"}],
        "events": [{"ref": "hoard://writer/ev/1", "summary": ""}]}
    report = exchange.import_world(conn, doc, world_id=target)
    assert [(i["state"], i.get("reason")) for i in report["items"]] == [
        ("skipped", "bad_ref"), ("skipped", "no_name"), ("created", None), ("skipped", "invalid"), ("skipped", "endpoint_missing"), ("skipped", "no_summary")]
    assert [e["name"] for e in store.list_entities(conn, target, limit=10)] == ["Bien"]


@pytest.mark.parametrize("bad", [None, [], {}, {"schema": "hoard.world/2"}, {"schema": "hoard.world/1", "characters": "x"},
                                 {"schema": "hoard.world/1", "world": []}])
def test_a_document_that_is_not_hoard_world_1_is_refused(conn, bad):
    before = len(store.list_worlds(conn))
    with pytest.raises(exchange.WorldDocumentError):
        exchange.import_world(conn, bad)
    assert len(store.list_worlds(conn)) == before


def test_too_many_records_are_refused(conn):
    doc = {"schema": "hoard.world/1", "characters": [{"ref": f"hoard://w/c/{i}", "name": f"n{i}"} for i in range(exchange.MAX_ITEMS + 1)]}
    with pytest.raises(exchange.WorldDocumentError):
        exchange.import_world(conn, doc)


def test_a_failure_midway_leaves_nothing_behind(conn, monkeypatch):
    doc = {"schema": "hoard.world/1", "world": {"name": "Rota"}, "characters": [{"ref": "hoard://w/c/1", "name": "Ana"}, {"ref": "hoard://w/c/2", "name": "Beto"}]}
    real = store.create_entity
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return real(*a, **k)

    monkeypatch.setattr(store, "create_entity", flaky)
    with pytest.raises(RuntimeError):
        exchange.import_world(conn, doc)
    assert store.list_worlds(conn) == []


def test_long_text_is_clipped_and_hash_helpers_are_stable():
    assert exchange.digest({"b": 1, "a": 2}) == exchange.digest({"a": 2, "b": 1})
    assert exchange.digest("é") != exchange.digest("e") and exchange.digest([]).startswith("sha256:")
