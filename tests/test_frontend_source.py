"""Source-level regression checks for frontend behaviour that has no JS
test runner to protect it (the frontend build only type-checks and
bundles; there is no unit-test step). Each test reads the relevant
.tsx/.ts file and asserts on the exact code shape a past bug depended
on, so a refactor that silently drops the behaviour fails CI instead of
a user finding out.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def test_play_page_offers_a_narration_mode():
    """Usability report #3: without a model, Play must let a person write
    the narration themselves — a Narración/Narration tab alongside
    Acción/Diálogo/Fuera de personaje, not just those three."""
    play_page = (FRONTEND_SRC / "pages" / "PlayPage.tsx").read_text(encoding="utf-8")
    assert '"narration", "action", "dialogue", "ooc"' in play_page
    i18n = (FRONTEND_SRC / "lib" / "i18n.ts").read_text(encoding="utf-8")
    assert "play_mode_narration" in i18n


def test_sessions_page_can_start_and_rename_a_session():
    """Usability report #6: the Sesiones screen must offer starting a new
    (optionally named) session and renaming an existing one, not only
    exporting — the MCP tools alone are not enough per the repo's own
    rule that a person can do everything an agent can."""
    sessions_page = (FRONTEND_SRC / "pages" / "SessionsPage.tsx").read_text(encoding="utf-8")
    assert "api.startSession" in sessions_page
    assert "api.renameSession" in sessions_page
    api_ts = (FRONTEND_SRC / "lib" / "api.ts").read_text(encoding="utf-8")
    assert "startSession:" in api_ts and "renameSession:" in api_ts
