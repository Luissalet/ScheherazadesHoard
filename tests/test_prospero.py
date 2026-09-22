"""Unit tests for the tiny, mocked Prospero's Hoard illustration adapter."""
from __future__ import annotations

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


async def test_illustrate_scene_returns_image_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/agent/studio_generate_image"
        return httpx.Response(200, json={"image_url": "http://127.0.0.1:8815/files/abc.png"})
    url = await prospero.illustrate_scene("un muelle en ruinas", "Puerto Salado", "tenso", transport=httpx.MockTransport(handler))
    assert url == "http://127.0.0.1:8815/files/abc.png"


async def test_illustrate_scene_returns_none_on_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    url = await prospero.illustrate_scene("x", transport=httpx.MockTransport(handler))
    assert url is None


async def test_illustrate_scene_returns_none_when_prompt_empty():
    url = await prospero.illustrate_scene("", "", "")
    assert url is None


def test_build_prompt_joins_nonempty_parts():
    assert prospero.build_prompt("un muelle", "Puerto", "tenso") == "Puerto, un muelle, tenso"
    assert prospero.build_prompt("", "", "") == ""
