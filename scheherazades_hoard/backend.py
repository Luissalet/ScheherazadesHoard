"""This app's side of the shared model backend.

The resolution and the calls themselves are Hoard Link's, vendored
unmodified in `./hoard_link/` (see `hoard_link/VENDORED.txt`): explicit
configuration, then Faustus's model registry, then servers already running
on loopback (llama.cpp, resident Ollama models, an OpenAI-compatible
server), and never a model of our own. This module only adds what is
specific to Scheherazade:

- the Settings form's flat fields (`llm_url`, `llm_model`, `faustus_url`,
  `faustus_token`, `allow_load`) mapped onto Hoard Link's `backend.json`
  schema, with an empty string meaning "clear this override";
- a status dict for `GET /api/backend` that never contains the token;
- a Link that still starts when `backend.json` is broken, reporting why.

Only the `llm` capability is used: this is a storytelling app.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from .hoard_link import BackendError, ChatResult, Link, LinkConfig, Resolution, Unavailable

__all__ = [
    "APP", "BackendError", "ChatResult", "Link", "LinkConfig", "Resolution", "Unavailable",
    "apply_settings", "load_link", "read_settings", "status",
]

APP = "scheherazades-hoard"
CAPABILITY = "llm"


def read_settings(path: Path) -> dict[str, Any]:
    """The raw backend.json object, or {} when it is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_link(path: Path, env: Optional[Mapping[str, str]] = None) -> tuple[Link, Optional[str]]:
    """A Link for this app, plus the config error if backend.json was unusable
    (the app then runs on defaults instead of refusing to start)."""
    env = os.environ if env is None else env
    try:
        return Link(LinkConfig.load(path, env=env, app=APP)), None
    except ValueError as e:
        return Link(LinkConfig.load(None, env=env, app=APP)), str(e)


def apply_settings(path: Path, patch: Mapping[str, Any]) -> dict[str, Any]:
    """Merge the Settings form into backend.json and return the new object.

    None leaves a value alone; an empty string removes the override so that
    resolution falls back to Faustus and loopback probing again.
    """
    data = read_settings(path)
    faustus = dict(data.get("faustus") or {})
    caps = dict(data.get("capabilities") or {})
    llm = dict(caps.get(CAPABILITY) or {})

    def put(section: dict, key: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            value = value.strip()
            if not value:
                section.pop(key, None)
                return
        section[key] = value

    put(llm, "url", patch.get("llm_url"))
    put(llm, "model", patch.get("llm_model"))
    if patch.get("allow_load") is not None:
        llm["allow_load"] = bool(patch["allow_load"])
    put(faustus, "url", patch.get("faustus_url"))
    put(faustus, "token", patch.get("faustus_token"))

    if llm:
        caps[CAPABILITY] = llm
    else:
        caps.pop(CAPABILITY, None)
    data["capabilities"] = caps
    if faustus:
        data["faustus"] = faustus
    else:
        data.pop("faustus", None)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _redacted(config: LinkConfig) -> dict[str, Any]:
    llm = config.capability(CAPABILITY)
    return {
        "llm_url": llm.url, "llm_model": llm.model, "allow_load": llm.allow_load,
        "faustus_url": config.faustus_urls[0] if len(config.faustus_urls) == 1 else None,
        "faustus_candidates": list(config.faustus_urls),
        "token_set": bool(config.faustus_token),
        "only_resident": config.only_resident,
    }


async def status(link: Link, config_error: Optional[str] = None) -> dict[str, Any]:
    """`GET /api/backend`: the llm resolution with its reason, and the
    configuration without the token."""
    res = await link.resolve(CAPABILITY)
    out: dict[str, Any] = {
        "llm": res.to_dict(),
        "config": _redacted(link.config),
        "checked_at": time.time(),
        "source": "hoard_link",
    }
    if config_error:
        out["config_error"] = config_error
    return out
