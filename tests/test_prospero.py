"""Mocked checks for the optional Prospero illustration adapter."""

import asyncio

import httpx

from scheherazades_hoard import prospero


async def test_is_available_false_when_unreachable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)
    assert await prospero.is_available(transport=httpx.MockTransport(refuse)) is False


async def test_is_available_true_when_service_matches():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"service": "prosperos-hoard"})
    assert await prospero.is_available(transport=httpx.MockTransport(handler)) is True


async def test_is_available_false_for_wrong_service():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"service": "something-else"})
    assert await prospero.is_available(transport=httpx.MockTransport(handler)) is False


async def test_illustrate_scene_returns_none_on_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    assert await prospero.illustrate_scene("x", transport=httpx.MockTransport(handler)) is None


async def test_illustrate_scene_returns_none_when_prompt_empty():
    assert await prospero.illustrate_scene("", "", "") is None


def test_build_prompt_joins_nonempty_parts():
    assert prospero.build_prompt("un muelle", "Puerto", "tenso") == "Puerto, un muelle, tenso"
    assert prospero.build_prompt("", "", "") == ""


def test_illustration_creates_project_and_returns_asset_url():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        if request.url.path == "/api/projects" and request.method == "GET":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/api/projects" and request.method == "POST":
            return httpx.Response(200, json={"id": "project_1"})
        if request.url.path.endswith("studio_generate_image"):
            return httpx.Response(200, json={"job": {"id": "job_1", "state": "queued"}})
        if request.url.path.endswith("studio_job"):
            return httpx.Response(200, json={"id": "job_1", "state": "done", "asset_ids": ["asset_1"]})
        return httpx.Response(404)

    url = asyncio.run(prospero.illustrate_scene("un faro en la niebla", world_name="Archipiélago",
                                               transport=httpx.MockTransport(handler)))
    assert url == "http://127.0.0.1:8815/api/assets/asset_1/file"
    assert calls[0][2]["query"] == "Scheherazade · Archipiélago"
    assert calls[2][2]["project"] == "project_1"


def test_illustration_reuses_project_and_handles_failed_job():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"id": "existing", "name": "Scheherazade · Mundo"}]})
        return httpx.Response(200, json={"job": {"id": "j", "state": "failed"}})

    url = asyncio.run(prospero.illustrate_scene("noche", world_name="Mundo",
                                               transport=httpx.MockTransport(handler)))
    assert url is None
