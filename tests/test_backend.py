"""The app's wrapper around the vendored Hoard Link (offline, httpx.MockTransport).

Hoard Link's own resolution order and policies are tested in its own
repository; these tests cover what this app adds on top: the Settings
form mapping, token redaction, a broken backend.json, and that chat goes
through the vendored package.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from scheherazades_hoard import backend
from scheherazades_hoard.api import create_app
from scheherazades_hoard.backend import Link, LinkConfig, Unavailable

PORT = 18862
VENDORED = Path(backend.__file__).parent / "hoard_link"


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _link(config: LinkConfig, handler=_refuse) -> Link:
    return Link(config, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_hoard_link_is_vendored_with_its_provenance():
    assert (VENDORED / "link.py").is_file() and (VENDORED / "LICENSE").is_file()
    text = (VENDORED / "VENDORED.txt").read_text(encoding="utf-8")
    assert text.startswith(
        "Vendored from HoardLink (https://github.com/Luissalet/HoardLink), version "
    )
    assert "byte-identical" in text.lower()
    assert backend.Link.__module__.startswith("scheherazades_hoard.hoard_link")


def test_settings_form_maps_onto_the_hoard_link_schema(tmp_path):
    path = tmp_path / "backend.json"
    backend.apply_settings(path, {
        "llm_url": "http://127.0.0.1:8081/v1/chat/completions", "llm_model": "qwen-27b",
        "faustus_url": "http://127.0.0.1:7000", "faustus_token": "ody_secret", "allow_load": False,
    })
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["capabilities"]["llm"] == {
        "url": "http://127.0.0.1:8081/v1/chat/completions", "model": "qwen-27b", "allow_load": False,
    }
    assert data["faustus"] == {"url": "http://127.0.0.1:7000", "token": "ody_secret"}
    cfg = LinkConfig.load(path, env={})
    assert cfg.capability("llm").url.endswith("/v1/chat/completions")
    assert cfg.faustus_token == "ody_secret"


def test_empty_string_clears_an_override_and_none_keeps_it(tmp_path):
    path = tmp_path / "backend.json"
    backend.apply_settings(path, {"llm_url": "http://127.0.0.1:1234/v1/chat/completions", "faustus_token": "t"})
    backend.apply_settings(path, {"llm_url": "", "faustus_token": None})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "llm" not in data["capabilities"]
    assert data["faustus"]["token"] == "t"


async def test_status_never_contains_the_token(tmp_path):
    path = tmp_path / "backend.json"
    backend.apply_settings(path, {"faustus_url": "http://127.0.0.1:7000", "faustus_token": "ody_secret"})
    link = _link(LinkConfig.load(path, env={}))
    status = await backend.status(link)
    assert "ody_secret" not in json.dumps(status)
    assert status["config"]["token_set"] is True
    assert status["llm"]["state"] == "unavailable"
    assert status["llm"]["reason"]  # a sentence the Settings screen can show
    await link.aclose()


def test_broken_backend_json_still_starts_and_says_why(tmp_path):
    path = tmp_path / "backend.json"
    path.write_text("{not json", encoding="utf-8")
    link, error = backend.load_link(path, env={})
    assert isinstance(link, Link)
    assert error and "not valid JSON" in error


async def test_chat_goes_through_the_vendored_link_and_strips_think_tags():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "<think>plan</think>La marea sube."}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            })
        return _refuse(request)

    cfg = LinkConfig.load(None, env={"HOARD_LLM_URL": "http://127.0.0.1:8081/v1/chat/completions",
                                     "HOARD_LLM_MODEL": "qwen-27b"})
    link = _link(cfg, handler)
    result = await link.chat([{"role": "user", "content": "hola"}], max_tokens=20)
    assert result.text == "La marea sube."
    assert result.reasoning and "plan" in result.reasoning
    assert seen["body"]["model"] == "qwen-27b"
    await link.aclose()


async def test_nothing_reachable_raises_unavailable_with_reasons():
    link = _link(LinkConfig.load(None, env={}))
    with pytest.raises(Unavailable) as info:
        await link.chat([{"role": "user", "content": "hola"}])
    assert info.value.reasons
    await link.aclose()


# --- HTTP surface -----------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "data", port=PORT)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def test_settings_endpoint_round_trip_without_leaking_the_token(client):
    r = client.post("/api/backend/settings", json={
        "llm_url": "http://127.0.0.1:8081/v1/chat/completions", "llm_model": "qwen-27b", "faustus_token": "ody_x",
    })
    assert r.status_code == 200
    body = r.json()
    assert "ody_x" not in r.text
    assert body["config"]["token_set"] is True
    assert body["llm"]["state"] == "resolved" and body["llm"]["model"] == "qwen-27b"
    assert "explicit configuration" in body["llm"]["reason"]

    r = client.post("/api/backend/settings", json={"llm_url": ""})
    assert r.json()["config"]["llm_url"] is None
    assert "ody_x" not in client.get("/api/backend").text


def test_settings_rejects_a_url_without_scheme(client):
    r = client.post("/api/backend/settings", json={"llm_url": "127.0.0.1:8081"})
    assert r.status_code == 400
    assert "http://" in r.json()["message"]
