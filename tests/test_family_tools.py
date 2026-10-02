"""world_export, world_import and scene_narrate over HTTP, with a stand-in for the hub."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_auth import agent_headers
from scheherazades_hoard.api import create_app

PORT = 18861


class FakeHub:
    """The three things the app asks of the hub; records what it was asked."""

    def __init__(self, audio=None, error=None, status=200, running=True, result=None):
        self.audio, self.error, self.status, self.running, self.result = audio, error, status, running, result
        self.calls: list[tuple] = []
        self.links: list[tuple] = []

    def call(self, app, tool, arguments=None, timeout=120.0):
        self.calls.append((app, tool, dict(arguments or {}), timeout))
        if self.error:
            return {"ok": False, "app": app, "tool": tool, "status": self.status, "error": self.error}
        result = self.result if self.result is not None else {"ok": True, "path": str(self.audio)}
        return {"ok": True, "app": app, "tool": tool, "status": 200, "result": result}

    def link(self, from_uri, to_uri, rel="related", **labels):
        self.links.append((from_uri, to_uri, rel, labels))
        return {"ok": True}

    def app_running(self, app):
        return self.running


@pytest.fixture()
def wav(tmp_path):
    path = tmp_path / "voice" / "line.wav"
    path.parent.mkdir()
    path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 40)
    return path


def make_client(tmp_path, hub):
    app = create_app(tmp_path / "data", port=PORT, hub=hub)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}", headers=agent_headers(app))


@pytest.fixture()
def hub(wav):
    return FakeHub(audio=wav)


@pytest.fixture()
def client(tmp_path, hub):
    with make_client(tmp_path, hub) as c:
        c.hub = hub
        yield c


@pytest.fixture()
def world(client):
    w = client.post("/api/agent/story_world_create", json={"name": "Faro", "language": "es"}).json()
    client.post("/api/agent/entity_upsert", json={"world": w["id"], "kind": "character", "name": "Ana", "summary": "Capitana", "secrets": "espía"})
    client.post("/api/agent/entity_upsert", json={"world": w["id"], "kind": "location", "name": "El Faro"})
    return w


# --- world_export / world_import -------------------------------------------------

def test_world_export_over_http_and_the_audit_line(client, world):
    r = client.post("/api/agent/world_export", json={"world_id": world["id"]})
    assert r.status_code == 200
    doc = r.json()
    assert doc["ok"] is True and doc["schema"] == "hoard.world/1" and [c["name"] for c in doc["characters"]] == ["Ana"]
    assert "espía" not in r.text
    assert client.post("/api/agent/world_export", json={"world": "Faro"}).json()["source"]["ref"].endswith(world["id"])
    assert client.post("/api/agent/world_export", json={}).status_code == 400
    assert client.post("/api/agent/world_export", json={"world_id": "nope"}).status_code == 404
    calls = client.get("/api/agent_calls").json()
    assert [c["tool"] for c in calls[:2]] == ["world_export", "world_export"] or "world_export" in {c["tool"] for c in calls}


def test_world_import_over_http_is_idempotent_and_links_the_source(client, world):
    doc = {"schema": "hoard.world/1", "source": {"app": "writer", "ref": "hoard://writer/project/p9", "revision": "sha256:r"},
           "world": {"name": "Novela", "language": "en"},
           "characters": [{"ref": "hoard://writer/codex/c1", "revision": "sha256:1", "name": "Iria", "summary": "Navegante"}],
           "places": [{"ref": "hoard://writer/codex/c2", "revision": "sha256:2", "name": "Puerto"}],
           "relations": [{"ref": "hoard://writer/rel/r1", "from": "hoard://writer/codex/c1", "to": "hoard://writer/codex/c2", "type": "vive_en"}]}
    r = client.post("/api/agent/world_import", json={"data": doc})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["world_created"] is True and body["counts"] == {"created": 3} and body["items_truncated"] is False
    world_id = body["world"]["id"]
    assert client.hub.links == [(body["world_ref"], "hoard://writer/project/p9", "imported_from", {"from_label": "Novela", "to_label": "Novela"})]
    again = client.post("/api/agent/world_import", json={"data": doc}).json()
    assert again["world"]["id"] == world_id and again["world_created"] is False and again["counts"] == {"unchanged": 3}
    into = client.post("/api/agent/world_import", json={"data": doc, "world_id": "Faro"}).json()
    assert into["world"]["id"] == world["id"] and into["counts"] == {"created": 3}
    assert {e["name"] for e in client.get(f"/api/worlds/{world_id}/entities").json()} == {"Iria", "Puerto"}


def test_world_import_refuses_what_is_not_a_world_document(client):
    r = client.post("/api/agent/world_import", json={"data": {"schema": "other/1"}})
    assert r.status_code == 400 and r.json()["error"] == "bad_document"
    assert client.post("/api/agent/world_import", json={"data": "text"}).status_code == 400
    assert client.post("/api/agent/world_import", json={"data": {"schema": "hoard.world/1"}, "world_id": "nope"}).status_code == 404
    assert client.get("/api/worlds").json() == []


def test_world_import_report_is_capped(client):
    doc = {"schema": "hoard.world/1", "characters": [{"ref": f"hoard://writer/codex/{i}", "name": f"P{i}"} for i in range(130)]}
    body = client.post("/api/agent/world_import", json={"data": doc}).json()
    assert body["counts"] == {"created": 130} and len(body["items"]) == 100 and body["items_truncated"] is True


# --- scene_narrate ----------------------------------------------------------------

@pytest.fixture()
def story(client, world):
    for text, role in (("La marea sube.", "narration"), ("—No hay tiempo —dice Ana—.", "dialogue"), ("Tira los dados", "ooc")):
        client.post("/api/agent/story_append", json={"world": world["id"], "text": text, "role": role})
    session = client.get(f"/api/worlds/{world['id']}/sessions").json()[-1]
    return {"world": world, "session": session}


def test_scene_narrate_keeps_the_audio_with_the_turn(client, story, wav, tmp_path):
    r = client.post("/api/agent/scene_narrate", json={"session_id": story["session"]["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["turn_index"] == 1  # the last narration/dialogue, not the out-of-character one
    app, tool, args, _ = client.hub.calls[-1]
    assert (app, tool) == ("prospero", "voice_tts") and args == {"text": "No hay tiempo —dice Ana—.", "lang": "es"}
    from pathlib import Path
    stored = Path(body["path"])
    assert stored.parent == tmp_path / "data" / "audio" and stored.read_bytes() == wav.read_bytes() and stored != wav
    audio = client.get(body["audio_url"])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav" and audio.content == wav.read_bytes()
    turns = client.get(f"/api/worlds/{story['world']['id']}/sessions/{story['session']['id']}/turns").json()
    assert [bool(t["audio"]) for t in turns] == [False, True, False]
    assert turns[1]["audio"]["file"] == stored.name
    export = client.get(f"/api/worlds/{story['world']['id']}/export.json").json()
    assert all("audio" not in t for t in export["turns"])


def test_scene_narrate_picks_the_turn_by_index_or_id_and_passes_voice_and_lang(client, story):
    sid = story["session"]["id"]
    turns = client.get(f"/api/worlds/{story['world']['id']}/sessions/{sid}/turns").json()
    assert client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 0, "voice": "es_ES-sharvard", "lang": "en"}).json()["turn_index"] == 0
    assert client.hub.calls[-1][2] == {"text": "La marea sube.", "lang": "en", "voice": "es_ES-sharvard"}
    assert client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": "1"}).json()["turn_index"] == 1
    assert client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": turns[0]["id"]}).json()["turn_id"] == turns[0]["id"]
    assert client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 2}).status_code == 400  # out of character
    assert client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 99}).status_code == 404
    assert client.post("/api/agent/scene_narrate", json={"session_id": "nope"}).status_code == 404
    by_title = client.post("/api/agent/scene_narrate", json={"session_id": story["session"]["title"], "world": "Faro"})
    assert by_title.status_code == 200


def test_narrating_again_replaces_the_audio_of_that_turn(client, story, wav):
    sid = story["session"]["id"]
    first = client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 0}).json()
    second = client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 0}).json()
    assert first["path"] == second["path"] and len(list((wav.parent.parent / "data" / "audio").glob("*"))) == 1


def test_scene_narrate_when_the_hub_or_the_voice_app_is_missing(tmp_path):
    for n, (hub, status, code) in enumerate(((FakeHub(error="hub not reachable at http://127.0.0.1:8810", status=None), 503, "voice_unavailable"),
                              (FakeHub(error="app prospero is not running", status=502), 503, "voice_unavailable"),
                              (FakeHub(error="unknown tool voice_tts", status=404), 503, "voice_unavailable"),
                              (FakeHub(error="engine failed", status=500), 502, "voice_failed"))):
        with make_client(tmp_path / str(n), hub) as c:
            made = c.post("/api/agent/story_world_create", json={"name": "A"})
            assert made.status_code == 200, made.text
            w = made.json()
            c.post("/api/agent/story_append", json={"world": w["id"], "text": "Hola", "role": "narration"})
            sid = c.get(f"/api/worlds/{w['id']}/sessions").json()[-1]["id"]
            r = c.post("/api/agent/scene_narrate", json={"session_id": sid})
            assert r.status_code == status and r.json()["error"] == code, r.text
            assert c.get(f"/api/worlds/{w['id']}/sessions/{sid}/turns").json()[0]["audio"] is None


@pytest.mark.parametrize("result,code", [({"ok": False, "error": "no voice"}, "voice_failed"), ({"ok": True}, "audio_unreadable"),
                                          ({"ok": True, "path": "/nope/missing.wav"}, "audio_unreadable"),
                                          ({"ok": True, "path": "C:/x/y.exe"}, "audio_unreadable")])
def test_scene_narrate_unusable_answers(tmp_path, result, code):
    with make_client(tmp_path, FakeHub(result=result)) as c:
        w = c.post("/api/agent/story_world_create", json={"name": "A"}).json()
        c.post("/api/agent/story_append", json={"world": w["id"], "text": "Hola", "role": "narration"})
        sid = c.get(f"/api/worlds/{w['id']}/sessions").json()[-1]["id"]
        r = c.post("/api/agent/scene_narrate", json={"session_id": sid})
        assert r.status_code == 502 and r.json()["error"] == code


def test_nothing_to_narrate_and_undone_turns(client, world):
    client.post("/api/agent/story_append", json={"world": world["id"], "text": "fuera", "role": "ooc"})
    sid = client.get(f"/api/worlds/{world['id']}/sessions").json()[-1]["id"]
    r = client.post("/api/agent/scene_narrate", json={"session_id": sid})
    assert r.status_code == 400 and "no narration" in r.json()["message"]
    client.post("/api/agent/story_append", json={"world": world["id"], "text": "Un trueno", "role": "narration"})
    client.post("/api/agent/story_undo", json={"world": world["id"]})
    assert client.post("/api/agent/scene_narrate", json={"session_id": sid}).status_code == 400
    assert client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 1}).status_code == 400


def test_audio_route_only_serves_what_was_kept(client, story):
    assert client.get("/api/turns/tn_unknown/audio").status_code == 404
    sid = story["session"]["id"]
    body = client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 0}).json()
    from pathlib import Path
    Path(body["path"]).unlink()
    assert client.get(body["audio_url"]).status_code == 404


def test_narration_availability_follows_the_hub(tmp_path, wav):
    with make_client(tmp_path / "a", FakeHub(audio=wav, running=True)) as up, make_client(tmp_path / "b", FakeHub(audio=wav, running=False)) as down:
        assert up.get("/api/narration/available").json() == {"available": True}
        assert down.get("/api/narration/available").json() == {"available": False}


def test_the_agent_calls_are_audited_but_the_ui_clicks_are_not(client, story):
    sid = story["session"]["id"]
    client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 0}, headers={"X-Hoard-Client": "ui"})
    assert "scene_narrate" not in {c["tool"] for c in client.get("/api/agent_calls").json()}
    client.post("/api/agent/scene_narrate", json={"session_id": sid, "turn": 0})
    client.post("/api/agent/world_import", json={"data": {"schema": "hoard.world/1"}})
    assert {"scene_narrate", "world_import"} <= {c["tool"] for c in client.get("/api/agent_calls").json()}
