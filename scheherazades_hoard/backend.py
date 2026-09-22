"""Adapter to the shared local model backend (the "Hoard Link" resolver).

By design, this app must never load its
own copy of a model server. It vendors `hoard_link` when that sibling
project is complete; while it is still being built alongside this one, this
module implements the same public shape described in
the Hoard Link README (`Link`, `LinkConfig`,
`resolve`, `status`, `chat`) directly against Faustus and loopback model
servers, so swapping in the real vendored package later needs no caller
changes. Only the `llm` capability is implemented — this is a storytelling
app, not a media pipeline; embeddings/tts/image are out of scope and
`resolve()` returns `Unavailable` for them.

Resolution order for `llm`: explicit config (backend.json / env) -> a
reachable Faustus's model registry -> loopback probes (llama.cpp,
Ollama-resident-only, an OpenAI-compatible server) ->
unavailable. Every result carries a human-readable reason.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_PROBE_CACHE_S = 30
_LLAMACPP_PORTS = range(8080, 8091)
_OLLAMA_PORT = 11434
_OPENAI_COMPAT_PORTS = (1234,)
_FAUSTUS_CANDIDATES = ("http://127.0.0.1:7000", "http://127.0.0.1:7001")


class Unavailable(RuntimeError):
    def __init__(self, capability: str, reasons: list[str]):
        self.capability = capability
        self.reasons = reasons
        super().__init__(f"{capability} unavailable: " + "; ".join(reasons) if reasons else f"{capability} unavailable")


class BackendError(RuntimeError):
    def __init__(self, provider: str, status: int, body_excerpt: str):
        self.provider = provider
        self.status = status
        self.body_excerpt = body_excerpt
        super().__init__(f"{provider} returned HTTP {status}: {body_excerpt[:200]}")


@dataclass
class Resolution:
    capability: str
    state: str  # "resolved" | "unavailable"
    provider: Optional[str] = None
    url: Optional[str] = None
    model: Optional[str] = None
    api: Optional[str] = None  # "openai" | "ollama"
    reason: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "capability": self.capability, "state": self.state, "provider": self.provider,
            "url": self.url, "model": self.model, "api": self.api, "reason": self.reason,
        }


@dataclass
class ChatResult:
    text: str
    model: str
    provider: str
    api: str
    usage: dict
    elapsed_ms: float
    reasoning: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "text": self.text, "model": self.model, "provider": self.provider,
            "usage": self.usage, "elapsed_ms": self.elapsed_ms, "reasoning": self.reasoning,
        }


@dataclass
class LinkConfig:
    app: str = "scheherazades-hoard"
    llm_url: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api: Optional[str] = None  # "openai" | "ollama", inferred if not set
    faustus_url: Optional[str] = None
    faustus_token: Optional[str] = None
    allow_load: bool = False
    only_resident: bool = True

    @classmethod
    def load(cls, path: Optional[Path], env: Optional[dict] = None, app: str = "scheherazades-hoard") -> "LinkConfig":
        env = env or os.environ
        data: dict[str, Any] = {}
        if path and Path(path).exists():
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        cfg = cls(
            app=app,
            llm_url=data.get("llm_url"),
            llm_model=data.get("llm_model"),
            llm_api=data.get("llm_api"),
            faustus_url=data.get("faustus_url"),
            faustus_token=data.get("faustus_token"),
            allow_load=bool(data.get("allow_load", False)),
            only_resident=bool(data.get("only_resident", True)),
        )
        cfg.llm_url = env.get("HOARD_LLM_URL", cfg.llm_url)
        cfg.llm_model = env.get("HOARD_LLM_MODEL", cfg.llm_model)
        cfg.faustus_url = env.get("HOARD_FAUSTUS_URL", cfg.faustus_url)
        cfg.faustus_token = env.get("HOARD_FAUSTUS_TOKEN", cfg.faustus_token)
        return cfg

    def redacted(self) -> dict:
        d = {
            "llm_url": self.llm_url, "llm_model": self.llm_model, "llm_api": self.llm_api,
            "faustus_url": self.faustus_url, "token_set": bool(self.faustus_token),
            "allow_load": self.allow_load, "only_resident": self.only_resident,
        }
        return d


def _basename_model(path: Optional[str]) -> str:
    if not path:
        return "unknown"
    return Path(path).stem


class Link:
    """Resolves and calls the shared local LLM. Only `llm` is implemented."""

    def __init__(self, config: LinkConfig, transport: Optional[httpx.BaseTransport] = None):
        self.config = config
        self._transport = transport
        self._cache: dict[str, tuple[float, Resolution]] = {}
        self._sync = None

    def _client(self, timeout: float = 2.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=timeout)

    # -- resolution ---------------------------------------------------

    async def resolve(self, capability: str = "llm", force: bool = False) -> Resolution:
        if capability != "llm":
            return Resolution(capability, "unavailable", reason=f"{capability} is out of scope for this app")
        cached = self._cache.get(capability)
        if cached and not force and (time.monotonic() - cached[0]) < _PROBE_CACHE_S:
            return cached[1]
        resolution = await self._resolve_llm()
        self._cache[capability] = (time.monotonic(), resolution)
        return resolution

    async def _resolve_llm(self) -> Resolution:
        reasons: list[str] = []

        if self.config.llm_url:
            api = self.config.llm_api or ("ollama" if "/api/chat" in self.config.llm_url else "openai")
            return Resolution(
                "llm", "resolved", provider="configured", url=self.config.llm_url,
                model=self.config.llm_model or "configured-model", api=api,
                reason=f"llm -> {self.config.llm_url} ({self.config.llm_model or 'default model'}), from explicit configuration",
            )

        faustus_hit = await self._probe_faustus()
        if faustus_hit:
            return faustus_hit
        reasons.extend(self._last_faustus_reasons)

        llama_hit = await self._probe_llamacpp()
        if llama_hit:
            return llama_hit
        reasons.append("no llama.cpp server on 127.0.0.1:8080-8090")

        ollama_hit = await self._probe_ollama()
        if ollama_hit:
            return ollama_hit
        reasons.append("no resident Ollama model on 127.0.0.1:11434")

        openai_compat_hit = await self._probe_openai_compat()
        if openai_compat_hit:
            return openai_compat_hit
        reasons.append("no OpenAI-compatible server on 127.0.0.1:1234")

        return Resolution("llm", "unavailable", reason="; ".join(reasons), details={"reasons": reasons})

    _last_faustus_reasons: list[str] = []

    async def _probe_faustus(self) -> Optional[Resolution]:
        self._last_faustus_reasons = []
        candidates = [self.config.faustus_url] if self.config.faustus_url else list(_FAUSTUS_CANDIDATES)
        headers = {"Authorization": f"Bearer {self.config.faustus_token}"} if self.config.faustus_token else {}
        async with self._client(timeout=1.0) as client:
            for base in candidates:
                if not base:
                    continue
                try:
                    r = await client.get(f"{base}/api/health", headers=headers)
                except httpx.HTTPError:
                    self._last_faustus_reasons.append(f"Faustus at {base} not reachable")
                    continue
                if r.status_code == 401 or r.status_code == 403:
                    self._last_faustus_reasons.append(f"Faustus at {base} needs a token (got {r.status_code})")
                    continue
                if r.status_code != 200:
                    self._last_faustus_reasons.append(f"Faustus at {base} health check failed ({r.status_code})")
                    continue
                try:
                    body = r.json()
                except ValueError:
                    continue
                if body.get("status") not in ("healthy", "ok"):
                    self._last_faustus_reasons.append(f"Faustus at {base} reports status={body.get('status')}")
                    continue
                try:
                    mr = await client.get(f"{base}/api/models", headers=headers)
                except httpx.HTTPError:
                    self._last_faustus_reasons.append(f"Faustus at {base} /api/models not reachable")
                    continue
                if mr.status_code != 200:
                    self._last_faustus_reasons.append(f"Faustus at {base} /api/models failed ({mr.status_code})")
                    continue
                items = (mr.json() or {}).get("items", [])
                llm_items = [it for it in items if it.get("model_type") == "llm"]
                if not llm_items:
                    self._last_faustus_reasons.append(f"Faustus at {base} has no llm entries in its registry")
                    continue
                item = llm_items[0]
                url = item["url"]
                api = "ollama" if "/api/chat" in url else "openai"
                model = (item.get("models") or ["unknown"])[0]
                return Resolution(
                    "llm", "resolved", provider=item.get("backend", "faustus"), url=url, model=model, api=api,
                    reason=f"llm -> {item.get('backend', 'faustus')} at {url} ({model}), from Faustus registry",
                    details={"endpoint_name": item.get("endpoint_name")},
                )
        return None

    async def _probe_llamacpp(self) -> Optional[Resolution]:
        async with self._client(timeout=1.0) as client:
            for port in _LLAMACPP_PORTS:
                base = f"http://127.0.0.1:{port}"
                try:
                    r = await client.get(f"{base}/props")
                except httpx.HTTPError:
                    continue
                if r.status_code != 200:
                    continue
                try:
                    props = r.json()
                except ValueError:
                    continue
                model = _basename_model(props.get("model_path"))
                slots_idle = True
                try:
                    sr = await client.get(f"{base}/slots")
                    if sr.status_code == 200:
                        slots_idle = not any(s.get("is_processing") for s in sr.json())
                except (httpx.HTTPError, ValueError):
                    pass
                return Resolution(
                    "llm", "resolved", provider="llamacpp", url=f"{base}/v1/chat/completions",
                    model=model, api="openai",
                    reason=f"llm -> llama.cpp at {base} ({model}), resident" + ("" if slots_idle else "; currently busy"),
                    details={"idle": slots_idle},
                )
        return None

    async def _probe_ollama(self) -> Optional[Resolution]:
        base = f"http://127.0.0.1:{_OLLAMA_PORT}"
        async with self._client(timeout=1.0) as client:
            try:
                r = await client.get(f"{base}/api/ps")
            except httpx.HTTPError:
                return None
            if r.status_code != 200:
                return None
            try:
                models = (r.json() or {}).get("models", [])
            except ValueError:
                return None
            if not models and self.config.only_resident:
                return None
            if not models:
                try:
                    tr = await client.get(f"{base}/api/tags")
                    models = (tr.json() or {}).get("models", [])
                except (httpx.HTTPError, ValueError):
                    models = []
            if not models:
                return None
            name = models[0].get("name") or models[0].get("model")
            return Resolution(
                "llm", "resolved", provider="ollama", url=f"{base}/api/chat", model=name, api="ollama",
                reason=f"llm -> Ollama at {base} ({name}), resident",
            )
        return None

    async def _probe_openai_compat(self) -> Optional[Resolution]:
        async with self._client(timeout=1.0) as client:
            for port in _OPENAI_COMPAT_PORTS:
                base = f"http://127.0.0.1:{port}"
                try:
                    r = await client.get(f"{base}/v1/models")
                except httpx.HTTPError:
                    continue
                if r.status_code != 200:
                    continue
                try:
                    items = (r.json() or {}).get("data", [])
                except ValueError:
                    continue
                if not items:
                    continue
                model = items[0].get("id", "unknown")
                return Resolution(
                    "llm", "resolved", provider="openai-compatible", url=f"{base}/v1/chat/completions",
                    model=model, api="openai",
                    reason=f"llm -> OpenAI-compatible server at {base} ({model})",
                )
        return None

    # -- status ---------------------------------------------------------

    async def status(self) -> dict:
        resolution = await self.resolve("llm")
        return {
            "llm": resolution.to_dict(),
            "config": self.config.redacted(),
            "checked_at": time.time(),
        }

    # -- good-citizen wait ------------------------------------------------

    async def wait_idle(self, capability: str = "llm", max_wait_s: float = 10.0) -> bool:
        resolution = await self.resolve(capability)
        if resolution.state != "resolved" or resolution.provider != "llamacpp":
            return True  # nothing to yield to, or no busy signal (e.g. Ollama)
        deadline = time.monotonic() + max_wait_s
        while True:
            fresh = await self.resolve(capability, force=True)
            if fresh.details.get("idle", True):
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(2)

    # -- chat -------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int = 512,
        temperature: float = 0.7,
        capability: str = "llm",
        response_format: Optional[dict] = None,
        timeout: float = 60.0,
    ) -> ChatResult:
        resolution = await self.resolve(capability)
        if resolution.state != "resolved":
            raise Unavailable(capability, resolution.details.get("reasons") or [resolution.reason])

        start = time.monotonic()
        async with self._client(timeout=timeout) as client:
            if resolution.api == "ollama":
                payload = {
                    "model": resolution.model, "messages": messages, "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                }
                r = await client.post(resolution.url, json=payload)
                if r.status_code >= 400:
                    raise BackendError(resolution.provider, r.status_code, r.text)
                body = r.json()
                text = (body.get("message") or {}).get("content", "")
                usage = {
                    "prompt_tokens": body.get("prompt_eval_count", 0),
                    "completion_tokens": body.get("eval_count", 0),
                }
            else:
                payload: dict[str, Any] = {
                    "model": resolution.model, "messages": messages,
                    "max_tokens": max_tokens, "temperature": temperature,
                }
                if response_format:
                    payload["response_format"] = response_format
                r = await client.post(resolution.url, json=payload)
                if r.status_code >= 400:
                    raise BackendError(resolution.provider, r.status_code, r.text)
                body = r.json()
                choice = (body.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content", "")
                usage = body.get("usage", {})

        elapsed_ms = (time.monotonic() - start) * 1000
        reasoning = None
        think_match = _THINK_RE.search(text)
        if think_match:
            reasoning = think_match.group(0)
            text = _THINK_RE.sub("", text).strip()
        return ChatResult(
            text=text, model=resolution.model or "unknown", provider=resolution.provider or "unknown",
            api=resolution.api or "openai", usage=usage, elapsed_ms=elapsed_ms, reasoning=reasoning,
        )

    # -- sync facade --------------------------------------------------------

    @property
    def sync(self) -> "_SyncFacade":
        if self._sync is None:
            self._sync = _SyncFacade(self)
        return self._sync


class _SyncFacade:
    """Runs the async API from synchronous code via a private event loop thread."""

    def __init__(self, link: Link):
        self._link = link
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
                self._thread.start()
            return self._loop

    def _run(self, coro: Awaitable[Any]) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def resolve(self, capability: str = "llm") -> Resolution:
        return self._run(self._link.resolve(capability))

    def status(self) -> dict:
        return self._run(self._link.status())

    def chat(self, *args: Any, **kwargs: Any) -> ChatResult:
        return self._run(self._link.chat(*args, **kwargs))
