"""The per-tool routes /api/agent/<tool> need the bearer token of POST /api/agent/call unless the request comes from
the app's own UI; plus what the shared commons now do for this app (guard, atomic backend.json, db timeout, text)."""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from agent_auth import agent_headers
from fastapi.testclient import TestClient

from scheherazades_hoard import backend, db, store
from scheherazades_hoard.api import create_app

PORT = 18861
MCP_SERVER = Path(__file__).resolve().parents[1] / "scheherazades_hoard" / "mcp_server.py"


@pytest.fixture()
def app(tmp_path):
    return create_app(tmp_path / "data", port=PORT)


@pytest.fixture()
def anonymous(app):
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def test_tool_routes_are_refused_without_the_token(anonymous):
    tools = [t["name"] for t in anonymous.get("/api/agent/tools").json()["tools"]]
    assert len(tools) == 19
    for name in tools:
        r = anonymous.post(f"/api/agent/{name}", json={})
        assert r.status_code == 401, name
        assert r.json()["error"] == "unauthorized"
    assert anonymous.post("/api/agent/story_worlds", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_tool_routes_work_with_the_token_and_are_audited(app, anonymous):
    r = anonymous.post("/api/agent/story_world_create", json={"name": "Faro"}, headers=agent_headers(app))
    assert r.status_code == 200
    calls = anonymous.get("/api/agent_calls").json()
    assert [c["tool"] for c in calls] == ["story_world_create"]
    lowercase = {"Authorization": agent_headers(app)["Authorization"].replace("Bearer", "bearer")}
    assert anonymous.post("/api/agent/story_worlds", json={}, headers=lowercase).status_code == 200


def test_the_apps_own_ui_needs_no_token_and_is_not_audited(anonymous):
    ui = {"X-Hoard-Client": "ui"}
    assert anonymous.post("/api/agent/story_world_create", json={"name": "Faro"}, headers=ui).status_code == 200
    assert anonymous.get("/api/agent_calls").json() == []


def test_a_cross_origin_page_cannot_use_the_ui_marker(anonymous):
    r = anonymous.post("/api/agent/story_worlds", json={}, headers={"X-Hoard-Client": "ui", "Origin": "http://evil.example"})
    assert r.status_code == 403


def test_catalogue_and_call_keep_their_own_rules(app, anonymous):
    assert anonymous.get("/api/agent/tools").status_code == 200
    assert anonymous.post("/api/agent/call", json={"name": "story_worlds", "arguments": {}}).status_code == 401
    ok = anonymous.post("/api/agent/call", json={"name": "story_worlds", "arguments": {}}, headers=agent_headers(app))
    assert ok.status_code == 200


def test_security_headers_survive_the_shared_guard(anonymous):
    r = anonymous.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors" in r.headers["content-security-policy"]


def test_the_guard_pins_the_port_and_opens_a_configured_host(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEHERAZADE_ALLOWED_HOSTS", "pc2.example")
    with TestClient(create_app(tmp_path / "data", port=PORT), base_url=f"http://127.0.0.1:{PORT}") as c:
        assert c.get("/api/health", headers={"Host": "pc2.example"}).status_code == 200
        assert c.get("/api/health", headers={"Host": "127.0.0.1:9999"}).status_code == 403
        assert c.get("/api/health", headers={"Host": "evil.example"}).status_code == 403


def _adapter():
    spec = importlib.util.spec_from_file_location("sh_mcp_adapter", MCP_SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adapter_reads_the_token_from_env_file_or_data_dir(tmp_path, monkeypatch):
    for name in ("SCHEHERAZADE_TOKEN", "SCHEHERAZADE_TOKEN_FILE", "SCHEHERAZADE_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    adapter = _adapter()
    (tmp_path / "mcp-token").write_text("from-data-dir\n", encoding="utf-8")
    monkeypatch.setenv("SCHEHERAZADE_DATA_DIR", str(tmp_path))
    assert adapter._token() == "from-data-dir"
    other = tmp_path / "other-token"
    other.write_text("﻿from-file", encoding="utf-8")
    monkeypatch.setenv("SCHEHERAZADE_TOKEN_FILE", str(other))
    assert adapter._token() == "from-file"
    monkeypatch.setenv("SCHEHERAZADE_TOKEN", "from-env")
    assert adapter._token() == "from-env"


async def test_adapter_without_a_valid_token_gets_a_readable_error(app, tmp_path, monkeypatch):
    import httpx
    import uvicorn

    from mcp.server.fastmcp.exceptions import ToolError

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    import asyncio
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            try:
                if httpx.get(f"http://127.0.0.1:{PORT}/api/health", trust_env=False, timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                await asyncio.sleep(0.1)
        monkeypatch.setenv("SCHEHERAZADE_URL", f"http://127.0.0.1:{PORT}")
        monkeypatch.setenv("SCHEHERAZADE_TOKEN", "wrong")
        adapter = _adapter()
        with pytest.raises(ToolError, match="unauthorized"):
            await adapter._call("story_worlds", {})
        monkeypatch.setenv("SCHEHERAZADE_TOKEN", agent_headers(app)["Authorization"].split()[1])
        assert await adapter._call("story_worlds", {}) == []
    finally:
        server.should_exit = True
        await task


# --- the commons: busy timeout, atomic backend.json, shared text search -----------------------------

def test_the_database_waits_for_a_busy_lock(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 10000
    conn.close()


def test_backend_json_is_written_atomically(tmp_path, monkeypatch):
    path = tmp_path / "backend.json"
    backend.apply_settings(path, {"llm_url": "http://127.0.0.1:8081/v1/chat/completions"})
    before = path.read_text(encoding="utf-8")
    assert before.endswith("\n") and "8081" in before
    # a write that cannot complete leaves the previous file, and no temp file behind
    import os

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        backend.apply_settings(path, {"llm_url": "http://127.0.0.1:9999/v1/chat/completions"})
    assert path.read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == ["backend.json"]


def test_search_ignores_stopwords_and_accents(tmp_path):
    conn = db.connect(tmp_path / "s.db")
    world = store.create_world(conn, "W", language="es")
    store.upsert_entity(conn, world["id"], "character", "Ana la Capitana", summary="Navega el mar de sal")
    assert [e["name"] for e in store.search_world(conn, world["id"], "¿Quién es la capitana?")["entities"]] == ["Ana la Capitana"]
    assert store.search_world(conn, world["id"], "???")["entities"] == []
    assert store._fts_query("") == '""'
    assert store._norm("  ÁRBOL Ñandú ") == "arbol nandu"
