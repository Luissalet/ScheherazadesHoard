"""Unit tests for the Hoard Link adapter (offline, httpx.MockTransport)."""
from __future__ import annotations

import httpx
import pytest

from scheherazades_hoard.backend import BackendError, Link, LinkConfig, Unavailable


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


async def test_nothing_reachable_is_unavailable():
    link = Link(LinkConfig(), transport=httpx.MockTransport(_refuse))
    res = await link.resolve("llm")
    assert res.state == "unavailable"
    assert "not reachable" in res.reason or "no llama.cpp" in res.reason


async def test_explicit_config_wins_over_everything():
    link = Link(LinkConfig(llm_url="http://127.0.0.1:9999/v1/chat/completions", llm_model="m"), transport=httpx.MockTransport(_refuse))
    res = await link.resolve("llm")
    assert res.state == "resolved"
    assert res.provider == "configured"
    assert res.api == "openai"


async def test_faustus_with_valid_token_resolves():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            assert request.headers.get("authorization") == "Bearer ody_test"
            return httpx.Response(200, json={"status": "healthy"})
        if request.url.path == "/api/models":
            return httpx.Response(200, json={"items": [
                {"url": "http://127.0.0.1:8081/v1/chat/completions", "models": ["qwen-27b"],
                 "model_type": "llm", "backend": "llamacpp", "endpoint_name": "main"},
            ]})
        raise httpx.ConnectError("refused", request=request)

    cfg = LinkConfig(faustus_url="http://127.0.0.1:7000", faustus_token="ody_test")
    link = Link(cfg, transport=httpx.MockTransport(handler))
    res = await link.resolve("llm")
    assert res.state == "resolved"
    assert res.provider == "llamacpp"
    assert res.model == "qwen-27b"
    assert "Faustus registry" in res.reason


async def test_faustus_401_is_recorded_and_falls_through():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health" and ":7000" in str(request.url):
            return httpx.Response(401)
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    res = await link.resolve("llm")
    assert res.state == "unavailable"
    assert "needs a token" in res.reason


async def test_llamacpp_probe_resolves_with_model_and_idle_state():
    def handler(request: httpx.Request) -> httpx.Response:
        if ":8080" in str(request.url) and request.url.path == "/props":
            return httpx.Response(200, json={"model_path": "/models/qwen3-27b-q8.gguf"})
        if ":8080" in str(request.url) and request.url.path == "/slots":
            return httpx.Response(200, json=[{"is_processing": True}])
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    res = await link.resolve("llm")
    assert res.state == "resolved"
    assert res.provider == "llamacpp"
    assert res.model == "qwen3-27b-q8"
    assert res.details["idle"] is False
    assert "busy" in res.reason


async def test_ollama_resolves_only_when_resident():
    def handler(request: httpx.Request) -> httpx.Response:
        if ":11434" in str(request.url) and request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    res = await link.resolve("llm")
    assert res.state == "resolved"
    assert res.provider == "ollama"
    assert res.model == "qwen3:8b"


async def test_ollama_not_resident_is_unavailable_by_default():
    def handler(request: httpx.Request) -> httpx.Response:
        if ":11434" in str(request.url) and request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    res = await link.resolve("llm")
    assert res.state == "unavailable"


async def test_resolution_is_cached_within_window():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if ":8080" in str(request.url) and request.url.path == "/props":
            return httpx.Response(200, json={"model_path": "/m.gguf"})
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    await link.resolve("llm")
    n_after_first = calls["n"]
    await link.resolve("llm")
    assert calls["n"] == n_after_first  # cached, no new probes


async def test_chat_strips_think_tags_and_exposes_reasoning():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/props":
            return httpx.Response(200, json={"model_path": "/m.gguf"})
        if request.url.path == "/slots":
            return httpx.Response(200, json=[{"is_processing": False}])
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "<think>plan</think>Hola"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            })
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    result = await link.chat([{"role": "user", "content": "hi"}])
    assert result.text == "Hola"
    assert "plan" in result.reasoning


async def test_chat_ollama_image_and_message_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        if request.url.path == "/api/chat":
            body = request.read()
            import json as _json
            payload = _json.loads(body)
            assert payload["model"] == "qwen3:8b"
            assert payload["stream"] is False
            return httpx.Response(200, json={"message": {"content": "hola"}, "eval_count": 2, "prompt_eval_count": 3})
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    result = await link.chat([{"role": "user", "content": "hi"}])
    assert result.api == "ollama"
    assert result.text == "hola"
    assert result.usage["completion_tokens"] == 2


async def test_chat_raises_unavailable_when_nothing_resolves():
    link = Link(LinkConfig(), transport=httpx.MockTransport(_refuse))
    with pytest.raises(Unavailable):
        await link.chat([{"role": "user", "content": "hi"}])


async def test_chat_raises_backend_error_on_http_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/props":
            return httpx.Response(200, json={"model_path": "/m.gguf"})
        if request.url.path == "/slots":
            return httpx.Response(200, json=[{"is_processing": False}])
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(500, text="internal error")
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(BackendError):
        await link.chat([{"role": "user", "content": "hi"}])


async def test_wait_idle_true_when_no_llamacpp_busy_signal():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "m"}]})
        raise httpx.ConnectError("refused", request=request)

    link = Link(LinkConfig(), transport=httpx.MockTransport(handler))
    assert await link.wait_idle("llm", max_wait_s=1) is True


def test_sync_facade_runs_status():
    link = Link(LinkConfig(), transport=httpx.MockTransport(_refuse))
    status = link.sync.status()
    assert status["llm"]["state"] == "unavailable"


def test_env_overrides_backend_json(monkeypatch):
    cfg = LinkConfig.load(None, env={"HOARD_LLM_URL": "http://127.0.0.1:1/v1/chat/completions"})
    assert cfg.llm_url == "http://127.0.0.1:1/v1/chat/completions"
