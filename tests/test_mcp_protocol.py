"""The proof the plugin works: spawn `mcp_server.py` over real MCP stdio
transport against a real running app (a live uvicorn.Server on a free
port), and drive it through `mcp.client.stdio` — not through the API
directly. This is the Definition-of-Done "MCP protocol test".
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from scheherazades_hoard.api import create_app

PORT = 18863
REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER_PATH = REPO_ROOT / "scheherazades_hoard" / "mcp_server.py"


class _ServerThread(threading.Thread):
    def __init__(self, app, port: int):
        super().__init__(daemon=True)
        self.config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        self.server = uvicorn.Server(self.config)

    def run(self) -> None:
        asyncio.run(self.server.serve())

    def stop(self) -> None:
        self.server.should_exit = True


@pytest.fixture(scope="module")
def live_app_url(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("mcp_live")
    app = create_app(data_dir, port=PORT)
    thread = _ServerThread(app, PORT)
    thread.start()
    for _ in range(100):
        try:
            r = httpx.get(f"http://127.0.0.1:{PORT}/api/health", timeout=0.5)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("app did not start in time")
    yield f"http://127.0.0.1:{PORT}"
    thread.stop()
    thread.join(timeout=5)


def _params(url: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_PATH)],
        env={**os.environ, "SCHEHERAZADE_URL": url},
    )


def _text(result) -> str:
    return result.content[0].text


async def test_list_tools_exposes_all_fourteen(live_app_url):
    async with stdio_client(_params(live_app_url)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            names = {t.name for t in tools}
            assert names == {
                "story_worlds", "story_world_create", "world_context", "world_search",
                "entity_get", "entity_upsert", "story_append", "dice_roll", "table_roll",
                "thread_update", "clock_tick", "world_check", "session_export", "story_undo",
            }
            # every tool has annotations set, and read-only ones are honest about it
            by_name = {t.name: t for t in tools}
            assert by_name["world_context"].annotations.readOnlyHint is True
            assert by_name["story_append"].annotations.readOnlyHint is False
            assert all(t.annotations.destructiveHint is False for t in tools)
            assert all(t.annotations.openWorldHint is False for t in tools)
            read_only = {n for n, t in by_name.items() if t.annotations.readOnlyHint}
            assert read_only == {"story_worlds", "world_context", "world_search", "entity_get",
                                 "world_check", "session_export"}
            for t in tools:
                # Faustus picks tools by retrieval over descriptions, in
                # English and Spanish: every tool needs a Keywords line.
                keywords = [ln for ln in t.description.splitlines() if ln.strip().startswith("Keywords:")]
                assert keywords, t.name
                assert len(keywords[0].split(",")) >= 6, t.name


async def test_full_loop_over_mcp_stdio(live_app_url):
    async with stdio_client(_params(live_app_url)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            created = await session.call_tool(
                "story_world_create", {"name": "Mundo MCP", "ruleset": "pbta_2d6", "language": "es"},
            )
            assert created.isError is False
            world = json.loads(_text(created))
            world_id = world["id"]

            entity = await session.call_tool(
                "entity_upsert", {"world": world_id, "kind": "character", "name": "Marisol", "summary": "capitana"},
            )
            assert entity.isError is False
            e = json.loads(_text(entity))
            assert e["ref"] == "E1"

            roll = await session.call_tool("dice_roll", {"expression": "1d20+2", "world": world_id})
            assert roll.isError is False
            assert "total" in json.loads(_text(roll))

            appended = await session.call_tool(
                "story_append",
                {
                    "world": world_id, "text": "algo pasa",
                    "delta": {
                        "new_facts": [{"text": "un hecho nuevo"}],
                        "scene": {"present": [e["ref"]], "mood": "tenso"},
                    },
                },
            )
            assert appended.isError is False
            assert json.loads(_text(appended))["rejected"] == []

            # world_context has no `scene` argument (matches the spec's tool
            # signature) — it falls back to the current session's last
            # recorded scene, which story_append just set.
            ctx = await session.call_tool("world_context", {"world": world_id})
            assert ctx.isError is False
            assert "Marisol" in json.loads(_text(ctx))["brief"]

            undone = await session.call_tool("story_undo", {"world": world_id})
            assert undone.isError is False


async def test_error_surfaces_as_tool_error(live_app_url):
    async with stdio_client(_params(live_app_url)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            created = await session.call_tool("story_world_create", {"name": "Otro Mundo"})
            world_id = json.loads(_text(created))["id"]
            result = await session.call_tool("entity_get", {"world": world_id, "ref": "no-existe"})
            assert result.isError is True
            assert "no entity matches" in _text(result)


async def test_unavailable_app_raises_readable_error(tmp_path):
    # Point the adapter at a port nothing is listening on.
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_PATH)],
        env={**os.environ, "SCHEHERAZADE_URL": "http://127.0.0.1:18869"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("story_worlds", {})
            assert result.isError is True
            assert "not running" in _text(result)
            assert "scheherazades-hoard_unavailable" in _text(result)


def test_refuses_non_loopback_url(monkeypatch):
    import importlib
    import sys as _sys

    monkeypatch.setenv("SCHEHERAZADE_URL", "http://example.com:8816")
    _sys.modules.pop("scheherazades_hoard.mcp_server", None)
    with pytest.raises(RuntimeError, match="non-loopback"):
        importlib.import_module("scheherazades_hoard.mcp_server")
    _sys.modules.pop("scheherazades_hoard.mcp_server", None)
    monkeypatch.setenv("SCHEHERAZADE_URL", "http://127.0.0.1:8816")


async def test_secrets_and_compact_results_over_mcp(live_app_url):
    async with stdio_client(_params(live_app_url)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            world = json.loads(_text(await session.call_tool("story_world_create", {"name": "Mundo Secreto", "ruleset": "pbta_2d6"})))
            await session.call_tool("entity_upsert", {
                "world": world["id"], "kind": "character", "name": "Cato", "summary": "erudito del puerto",
                "secrets": "robó el mapa",
            })
            hits = await session.call_tool("world_search", {"world": world["id"], "query": "puerto"})
            assert "robó el mapa" not in _text(hits)
            roll = json.loads(_text(await session.call_tool("dice_roll", {"expression": "2d6+1", "world": world["id"]})))
            assert roll["band"] in ("miss", "weak_hit", "strong_hit")
            bad = await session.call_tool("story_append", {"world": world["id"], "text": "x", "role": "narrator"})
            assert bad.isError is True and "bad_request: unknown turn role" in _text(bad)
