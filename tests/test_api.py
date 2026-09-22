"""FastAPI TestClient tests: HTTP surface, guard middleware, and the
/api/agent/* tools that the MCP adapter calls through."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scheherazades_hoard.api import create_app

PORT = 18860


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "data", port=PORT)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


@pytest.fixture()
def world(client):
    r = client.post("/api/agent/story_world_create", json={
        "name": "Archipielago", "premise": "reino hundido", "ruleset": "pbta_2d6", "language": "es",
    })
    assert r.status_code == 200
    return r.json()


# --- health & guard --------------------------------------------------------

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "scheherazades-hoard"
    assert body["name"] == "Scheherazade's Hoard"
    assert body["status"] == "ok"


def test_guard_rejects_unknown_host(client):
    r = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden_host"


def test_guard_accepts_localhost_alias(client):
    r = client.get("/api/health", headers={"Host": f"localhost:{PORT}"})
    assert r.status_code == 200


def test_guard_rejects_cross_origin_post(client):
    r = client.post("/api/agent/story_world_create", json={"name": "X"}, headers={"Origin": "http://evil.example.com"})
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden_origin"


def test_guard_rejects_cross_site_fetch_metadata(client):
    r = client.post("/api/agent/story_world_create", json={"name": "X"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden_cross_site"


def test_guard_allows_same_origin_post(client):
    r = client.post(
        "/api/agent/story_world_create", json={"name": "X"},
        headers={"Origin": f"http://127.0.0.1:{PORT}"},
    )
    assert r.status_code == 200


def test_guard_allows_plain_get_navigation_from_any_tab(client):
    # GET must keep working even with a foreign-looking Sec-Fetch-Site,
    # since a browser tab navigating to the app sends one.
    r = client.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200


# --- worlds ------------------------------------------------------------

def test_create_and_get_world(client):
    r = client.post("/api/agent/story_world_create", json={"name": "W", "ruleset": "d20"})
    assert r.status_code == 200
    wid = r.json()["id"]
    r2 = client.get(f"/api/worlds/{wid}")
    assert r2.status_code == 200
    assert r2.json()["ruleset"] == "d20"


def test_create_world_rejects_bad_ruleset(client):
    r = client.post("/api/agent/story_world_create", json={"name": "W", "ruleset": "nope"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_request"


def test_story_worlds_agent_tool_lists_worlds(world, client):
    r = client.post("/api/agent/story_worlds", json={})
    assert r.status_code == 200
    names = [w["name"] for w in r.json()]
    assert "Archipielago" in names


def test_update_world_settings(world, client):
    r = client.patch(f"/api/worlds/{world['id']}", json={"tone": "oscuro"})
    assert r.status_code == 200
    assert r.json()["tone"] == "oscuro"


def test_get_unknown_world_is_404(client):
    r = client.get("/api/worlds/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


# --- entities ------------------------------------------------------------

def test_entity_upsert_then_get(world, client):
    r = client.post("/api/agent/entity_upsert", json={
        "world": world["id"], "kind": "character", "name": "Marisol", "summary": "capitana",
    })
    assert r.status_code == 200
    e = r.json()
    assert e["ref"] == "E1"

    r2 = client.post("/api/agent/entity_get", json={"world": world["id"], "ref": "Marisol"})
    assert r2.status_code == 200
    assert r2.json()["name"] == "Marisol"
    assert "secrets" not in r2.json()


def test_entity_get_includes_secrets_only_when_asked(world, client):
    client.post("/api/agent/entity_upsert", json={
        "world": world["id"], "kind": "character", "name": "Marisol", "secrets": "es una espia",
    })
    r = client.post("/api/agent/entity_get", json={"world": world["id"], "ref": "Marisol", "include_secrets": True})
    assert r.json()["secrets"] == "es una espia"


def test_entity_upsert_rejects_bad_kind(world, client):
    r = client.post("/api/agent/entity_upsert", json={"world": world["id"], "kind": "spaceship", "name": "Nave"})
    assert r.status_code == 400


def test_direct_entity_crud_via_ui_endpoints(world, client):
    r = client.post(f"/api/worlds/{world['id']}/entities", json={"kind": "location", "name": "Puerto Salado"})
    assert r.status_code == 200
    ref = r.json()["ref"]
    r2 = client.patch(f"/api/worlds/{world['id']}/entities/{ref}", json={"summary": "un muelle roto"})
    assert r2.status_code == 200
    assert r2.json()["summary"] == "un muelle roto"
    r3 = client.get(f"/api/worlds/{world['id']}/entities")
    assert len(r3.json()) == 1


# --- dice, tables, threads, clocks --------------------------------------

def test_dice_roll_logs_to_dice_log(world, client):
    r = client.post("/api/agent/dice_roll", json={"expression": "2d6+3", "world": world["id"], "reason": "ataque"})
    assert r.status_code == 200
    assert 5 <= r.json()["total"] <= 15
    r2 = client.get(f"/api/worlds/{world['id']}/dice_log")
    assert len(r2.json()) == 1
    assert r2.json()[0]["reason"] == "ataque"


def test_dice_roll_bad_expression_is_400(world, client):
    r = client.post("/api/agent/dice_roll", json={"expression": "bogus", "world": world["id"]})
    assert r.status_code == 400


def test_table_roll(world, client):
    client.post(f"/api/worlds/{world['id']}/tables", json={"name": "Rumores", "entries": [{"text": "algo"}]})
    r = client.post("/api/agent/table_roll", json={"world": world["id"], "table": "Rumores", "seed": 1})
    assert r.status_code == 200
    assert r.json()["text"] == "algo"


def test_thread_update(world, client):
    client.post(f"/api/worlds/{world['id']}/threads", json={"title": "Un misterio"})
    r = client.post("/api/agent/thread_update", json={"world": world["id"], "thread": "Un misterio", "status": "resolved"})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"


def test_clock_tick(world, client):
    client.post(f"/api/worlds/{world['id']}/clocks", json={"name": "Tormenta", "segments": 4})
    r = client.post("/api/agent/clock_tick", json={"world": world["id"], "clock": "Tormenta", "ticks": 2})
    assert r.status_code == 200
    assert r.json()["filled"] == 2


# --- story turns, delta, undo --------------------------------------------

def test_story_append_and_undo(world, client):
    r = client.post("/api/agent/story_append", json={
        "world": world["id"], "text": "algo pasa",
        "delta": {"new_entities": [{"kind": "character", "name": "Nuevo"}]},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["rejected"] == []
    assert body["applied"]["created_entities"][0]["name"] == "Nuevo"
    assert body["turn_id"].startswith("tn_")

    r2 = client.get(f"/api/worlds/{world['id']}/entities")
    assert len(r2.json()) == 1

    r3 = client.post("/api/agent/story_undo", json={"world": world["id"]})
    assert r3.status_code == 200
    r4 = client.get(f"/api/worlds/{world['id']}/entities")
    assert len(r4.json()) == 0


def test_story_undo_with_nothing_to_undo_is_404(world, client):
    r = client.post("/api/agent/story_undo", json={"world": world["id"]})
    assert r.status_code == 404


def test_story_append_reports_rejected_items(world, client):
    ghost = client.post("/api/agent/entity_upsert", json={
        "world": world["id"], "kind": "character", "name": "Fantasma", "status": "dead",
    }).json()
    r = client.post("/api/agent/story_append", json={
        "world": world["id"], "text": "x",
        "delta": {"scene": {"present": [ghost["ref"]]}},
    })
    assert r.status_code == 200
    assert len(r.json()["rejected"]) == 1


# --- world_check, session_export ------------------------------------------

def test_world_check_endpoint(world, client):
    client.post("/api/agent/entity_upsert", json={"world": world["id"], "kind": "character", "name": "Marisol", "status": "dead"})
    r = client.post("/api/agent/world_check", json={"world": world["id"], "statement": "Marisol camina"})
    assert r.status_code == 200
    assert r.json()["consistent"] is False


def test_session_export_bible_when_no_session_given(world, client):
    client.post("/api/agent/entity_upsert", json={"world": world["id"], "kind": "character", "name": "Marisol"})
    r = client.post("/api/agent/session_export", json={"world": world["id"], "format": "md"})
    assert r.status_code == 200
    assert "Marisol" in r.json()["text"]


def test_session_export_json_full_dump(world, client):
    r = client.post("/api/agent/session_export", json={"world": world["id"], "format": "json"})
    assert r.status_code == 200
    assert r.json()["format"] == "scheherazades-hoard-world-export"


# --- audit trail & backend -------------------------------------------------

def test_agent_calls_are_recorded(world, client):
    client.post("/api/agent/dice_roll", json={"expression": "1d6", "world": world["id"]})
    r = client.get("/api/agent_calls")
    assert r.status_code == 200
    tools = [c["tool"] for c in r.json()]
    assert "dice_roll" in tools


def test_backend_status_shape(client):
    r = client.get("/api/backend")
    assert r.status_code == 200
    body = r.json()
    assert "llm" in body
    assert body["llm"]["state"] in ("resolved", "unavailable")
    assert body["config"]["token_set"] is False


def test_prospero_available_false_when_not_running(client):
    r = client.get("/api/prospero/available")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_no_frontend_built_returns_placeholder(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# --- regressions found in review ------------------------------------------

def _upsert(client, world, **body):
    r = client.post("/api/agent/entity_upsert", json={"world": world["id"], **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_entity_upsert_update_keeps_unsent_values(world, client):
    _upsert(client, world, kind="character", name="Iria", summary="capitana", secrets="es la heredera",
            fields={"coraje": 2}, status="dead")
    _upsert(client, world, kind="character", name="Iria", fields={"herida": True})
    e = client.post("/api/agent/entity_get", json={"world": world["id"], "ref": "Iria", "include_secrets": True}).json()
    assert e["summary"] == "capitana"
    assert e["secrets"] == "es la heredera"
    assert e["status"] == "dead"  # an update must never resurrect a character
    assert e["fields"] == {"coraje": 2, "herida": True}


def test_entity_upsert_by_alias_keeps_canonical_name(world, client):
    _upsert(client, world, kind="character", name="Tomás Rojas")
    client.patch(f"/api/worlds/{world['id']}/entities/Tomás Rojas", json={"aliases": ["el Rojo"]})
    _upsert(client, world, kind="character", name="el Rojo", summary="contrabandista")
    e = client.post("/api/agent/entity_get", json={"world": world["id"], "ref": "el rojo"}).json()
    assert e["name"] == "Tomás Rojas"
    assert e["summary"] == "contrabandista"


def test_entity_upsert_refuses_kind_change(world, client):
    _upsert(client, world, kind="location", name="Puerto Salado")
    r = client.post("/api/agent/entity_upsert", json={"world": world["id"], "kind": "character", "name": "Puerto Salado"})
    assert r.status_code == 400
    assert "already exists as a location" in r.json()["message"]


def test_entity_status_accepts_spanish_and_rejects_unknown(world, client):
    e = _upsert(client, world, kind="character", name="Ulla", status="Muerta")
    assert e["status"] == "dead"
    r = client.post("/api/agent/entity_upsert", json={"world": world["id"], "kind": "character", "name": "Ulla", "status": "sleepy"})
    assert r.status_code == 400
    assert "alive" in r.json()["message"]


def test_not_found_message_is_not_double_quoted(world, client):
    r = client.post("/api/agent/entity_get", json={"world": world["id"], "ref": "nadie"})
    assert r.status_code == 404
    assert r.json()["message"] == "no entity matches 'nadie'"


def test_world_search_never_returns_secrets_and_is_compact(world, client):
    _upsert(client, world, kind="character", name="Cato", summary="erudito del puerto", secrets="robó el mapa")
    r = client.post("/api/agent/world_search", json={"world": world["id"], "query": "puerto"})
    body = r.json()
    assert "robó el mapa" not in r.text
    hit = body["entities"][0]
    assert set(hit) == {"id", "ref", "kind", "name", "status", "summary"}
    assert body["has_more"] is False


def test_world_search_kind_filter_applies_before_limit(world, client):
    for i in range(4):
        _upsert(client, world, kind="location", name=f"Faro {i}", summary="faro")
    _upsert(client, world, kind="character", name="Guardiana", summary="vive en el faro")
    body = client.post("/api/agent/world_search", json={
        "world": world["id"], "query": "faro", "kinds": ["character"], "limit": 2,
    }).json()
    assert [e["name"] for e in body["entities"]] == ["Guardiana"]


def test_world_search_has_more_when_limited(world, client):
    for i in range(3):
        _upsert(client, world, kind="location", name=f"Isla {i}", summary="isla")
    body = client.post("/api/agent/world_search", json={"world": world["id"], "query": "isla", "limit": 2}).json()
    assert len(body["entities"]) == 2
    assert body["has_more"] is True


def test_entity_upsert_result_is_a_brief_without_secrets(world, client):
    e = _upsert(client, world, kind="character", name="Mara", secrets="traidora")
    assert e["created"] is True and e["ref"].startswith("E")
    assert "secrets" not in e
    again = _upsert(client, world, kind="character", name="Mara", summary="piloto")
    assert again["created"] is False and again["id"] == e["id"]


def test_entity_get_names_the_other_side_of_relations(world, client):
    _upsert(client, world, kind="character", name="Iria")
    _upsert(client, world, kind="character", name="Tomás")
    client.post(f"/api/worlds/{world['id']}/relations", json={"a": "Iria", "b": "Tomás", "type": "hermana de"})
    e = client.post("/api/agent/entity_get", json={"world": world["id"], "ref": "Tomás"}).json()
    rel = e["relations"][0]
    assert rel["direction"] == "in" and rel["other_name"] == "Iria" and rel["type"] == "hermana de"


def test_entity_facts_found_even_behind_many_newer_facts(world, client):
    _upsert(client, world, kind="character", name="Ulla")
    client.post(f"/api/worlds/{world['id']}/facts", json={"text": "Ulla firmó el pacto", "entity_ids": ["Ulla"]})
    for i in range(60):
        client.post(f"/api/worlds/{world['id']}/facts", json={"text": f"hecho {i}"})
    e = client.post("/api/agent/entity_get", json={"world": world["id"], "ref": "Ulla"}).json()
    assert [f["text"] for f in e["facts"]] == ["Ulla firmó el pacto"]


def test_story_append_with_bad_role_applies_nothing(world, client):
    client.post(f"/api/worlds/{world['id']}/clocks", json={"name": "Marea", "segments": 4})
    r = client.post("/api/agent/story_append", json={
        "world": world["id"], "text": "x", "role": "narrator", "delta": {"clock_ticks": [{"ref": "C1"}]},
    })
    assert r.status_code == 400
    assert "narration" in r.json()["message"]  # the error lists the valid roles
    assert client.get(f"/api/worlds/{world['id']}/clocks").json()[0]["filled"] == 0


def test_story_append_result_is_compact_with_named_scene(world, client):
    _upsert(client, world, kind="location", name="Puerto Salado")
    _upsert(client, world, kind="character", name="Iria", secrets="heredera")
    body = client.post("/api/agent/story_append", json={
        "world": world["id"], "text": "Llegan al puerto.",
        "delta": {"scene": {"location": "Puerto Salado", "present": ["Iria"]},
                  "new_entities": [{"kind": "item", "name": "Ancla", "secrets": "maldita"}]},
    }).json()
    assert body["scene"]["location"] == {"ref": "E1", "name": "Puerto Salado"}
    assert body["scene"]["present"] == [{"ref": "E2", "name": "Iria"}]
    assert "maldita" not in str(body) and "heredera" not in str(body)
    assert body["applied"]["created_entities"][0]["ref"] == "E3"


def test_story_append_needs_text_or_delta(world, client):
    r = client.post("/api/agent/story_append", json={"world": world["id"], "text": "  "})
    assert r.status_code == 400
