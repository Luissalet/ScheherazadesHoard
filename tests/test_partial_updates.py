"""The UI saves only the fields a person changed, so an edit the assistant made
meanwhile survives. These tests pin that the PATCH routes merge: a field that is
not sent is never touched, and a field sent empty is cleared on purpose."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_auth import agent_headers
from scheherazades_hoard.api import create_app

PORT = 18861


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "data", port=PORT)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}", headers=agent_headers(app)) as c:
        yield c


@pytest.fixture()
def world(client):
    r = client.post("/api/agent/story_world_create", json={
        "name": "Archipielago", "genre": "fantasy", "tone": "grim", "premise": "reino hundido", "language": "es",
    })
    assert r.status_code == 200
    return r.json()


@pytest.fixture()
def maria(client, world):
    r = client.post(f"/api/worlds/{world['id']}/entities", json={
        "kind": "character", "name": "Maria", "summary": "contrabandista", "description": "alta y callada",
        "aliases": ["Mari"], "tags": ["puerto"], "secrets": "traiciona al gremio",
    })
    assert r.status_code == 200
    return r.json()


def test_entity_patch_keeps_every_field_that_is_not_sent(client, world, maria):
    # the assistant changes the status, then the person saves only the summary
    assert client.patch(f"/api/worlds/{world['id']}/entities/{maria['ref']}", json={"status": "missing"}).status_code == 200
    r = client.patch(f"/api/worlds/{world['id']}/entities/{maria['ref']}", json={"summary": "capitana"})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == "capitana"
    assert body["status"] == "missing"
    assert body["description"] == "alta y callada"
    assert body["aliases"] == ["Mari"] and body["tags"] == ["puerto"]
    assert body["secrets"] == "traiciona al gremio"


def test_entity_patch_clears_a_field_sent_empty_and_leaves_the_others(client, world, maria):
    r = client.patch(f"/api/worlds/{world['id']}/entities/{maria['ref']}", json={"description": "", "tags": []})
    assert r.status_code == 200
    body = r.json()
    assert body["description"] == "" and body["tags"] == []
    assert body["summary"] == "contrabandista" and body["aliases"] == ["Mari"]


def test_entity_patch_with_nothing_changes_nothing(client, world, maria):
    r = client.patch(f"/api/worlds/{world['id']}/entities/{maria['ref']}", json={})
    assert r.status_code == 200
    assert r.json()["summary"] == "contrabandista"
    assert r.json()["updated_at"] == maria["updated_at"]


def test_entity_fields_patch_merges_into_existing_fields(client, world, maria):
    client.patch(f"/api/worlds/{world['id']}/entities/{maria['ref']}", json={"fields": {"hp": 10, "class": "rogue"}})
    r = client.patch(f"/api/worlds/{world['id']}/entities/{maria['ref']}", json={"fields_patch": {"hp": 7}})
    assert r.json()["fields"] == {"hp": 7, "class": "rogue"}


def test_world_patch_only_touches_the_fields_sent(client, world):
    assert client.patch(f"/api/worlds/{world['id']}", json={"tone": "hopeful"}).status_code == 200
    r = client.patch(f"/api/worlds/{world['id']}", json={"genre": "noir"})
    assert r.status_code == 200
    body = r.json()
    assert body["genre"] == "noir"
    assert body["tone"] == "hopeful"
    assert body["premise"] == "reino hundido"


def test_session_rename_keeps_the_rest_of_the_session(client, world):
    s = client.post(f"/api/worlds/{world['id']}/sessions", json={"title": "Uno"}).json()
    r = client.patch(f"/api/worlds/{world['id']}/sessions/{s['id']}", json={"title": "Dos"})
    assert r.status_code == 200
    assert r.json()["title"] == "Dos"
    assert r.json()["started_at"] == s["started_at"]
