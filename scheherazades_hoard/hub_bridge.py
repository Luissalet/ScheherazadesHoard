"""The way this app reaches other family apps through the hub (all optional).

`Hub` is the real thing; tests hand `create_app` a stand-in with the same three
methods. Every call is blocking and short, never raises, and answers
`{"ok": False, "error": ...}` when the hub is not there, so the app carries on alone.
"""
from __future__ import annotations

from typing import Any, Optional

from .hoard_link import fam_refs, family
from .hoard_link._hubclient import fetch


class Hub:
    def call(self, app: str, tool: str, arguments: Optional[dict[str, Any]] = None, timeout: float = 120.0) -> dict[str, Any]:
        """A tool of another app through the hub's proxy: `{ok, app, tool, status, result|error}`."""
        try:
            return family.call(app, tool, arguments or {}, timeout=timeout)
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "app": app, "tool": tool, "status": None, "error": f"{type(error).__name__}: {error}"}

    def link(self, from_uri: str, to_uri: str, rel: str = "related", **labels: str) -> dict[str, Any]:
        """Tell the hub two records are the same thing / connected (a hint)."""
        return fam_refs.link(from_uri, to_uri, rel, **labels)

    def app_running(self, app: str) -> bool:
        """Whether the hub reports `app` as running right now."""
        try:
            status, body = fetch(f"{family._hub()}/api/apps/{app}", timeout=1.5, headers=family._headers())
        except Exception:  # noqa: BLE001
            return False
        return status == 200 and isinstance(body, dict) and body.get("state") == "running"
