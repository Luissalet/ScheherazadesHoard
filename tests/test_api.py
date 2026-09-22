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
    assert len(body["turn"]["delta"]["created_entities"]) == 1

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
