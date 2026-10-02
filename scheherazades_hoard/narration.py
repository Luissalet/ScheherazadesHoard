"""Narrate a turn aloud: pick the text, keep the audio the voice app made.

Pure logic (no FastAPI): `api.py` does the hub call and the HTTP.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional, Union

from . import store

NARRATABLE_ROLES = ("narration", "dialogue", "action")
MAX_TEXT = 4000
MAX_AUDIO_BYTES = 200 * 1024 * 1024
AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".m4a": "audio/mp4",
               ".flac": "audio/flac", ".opus": "audio/ogg", ".webm": "audio/webm"}


class NarrationError(ValueError):
    """Something the caller can fix (no such turn, nothing to read, the audio is not usable)."""

    def __init__(self, message: str, code: str = "bad_request"):
        super().__init__(message)
        self.code = code


def find_session(conn, session_id: str, world: Optional[str] = None) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row:
        return dict(row)
    if world:
        world_id = store.resolve_world_id(conn, world)
        resolved = store.resolve_session_id(conn, world_id, session_id)
        return dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (resolved,)).fetchone())
    raise store.NotFound(f"no session matches {session_id!r}")


def pick_turn(conn, session: dict[str, Any], turn: Union[int, str, None] = None) -> dict[str, Any]:
    """The turn to read: by index or id, else the last live narration, dialogue or action turn with text."""
    turns = store.list_turns(conn, session["id"])
    if turn is None or (isinstance(turn, str) and not turn.strip()):
        live = [t for t in turns if not t["undone"] and t["role"] in NARRATABLE_ROLES and t["text"].strip()]
        if not live:
            raise NarrationError("this session has no narration to read aloud yet", "nothing_to_narrate")
        return live[-1]
    wanted = turn
    if isinstance(wanted, str) and wanted.strip().lstrip("-").isdigit():
        wanted = int(wanted.strip())
    for t in turns:
        if (isinstance(wanted, int) and t["idx"] == wanted) or (isinstance(wanted, str) and t["id"] == wanted):
            if t["undone"]:
                raise NarrationError(f"turn {turn!r} was undone", "turn_undone")
            if t["role"] not in NARRATABLE_ROLES or not t["text"].strip():
                raise NarrationError(f"turn {turn!r} is a {t['role']} turn with nothing to narrate", "nothing_to_narrate")
            return t
    raise store.NotFound(f"no turn {turn!r} in this session")


def text_to_read(turn: dict[str, Any]) -> str:
    text = " ".join(turn["text"].split())
    if turn["role"] == "dialogue":
        text = text.lstrip("—–- ").strip()
    return text[:MAX_TEXT]


def keep_audio(data_dir: Path, turn_id: str, source: Any) -> tuple[str, Path]:
    """Copy the audio file a voice app reports into this app's data folder: (file name, full path).

    The source path comes from another app, so it is only read, never served: the UI plays the copy."""
    if not isinstance(source, str) or not source.strip():
        raise NarrationError("the voice app answered without an audio path", "audio_unreadable")
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix not in AUDIO_TYPES:
        raise NarrationError(f"the voice app returned a {suffix or 'file without extension'} file; expected audio", "audio_unreadable")
    try:
        size = path.stat().st_size if path.is_file() else -1
    except OSError:
        size = -1
    if size <= 0:
        raise NarrationError(f"the audio file {source!r} cannot be read from this machine", "audio_unreadable")
    if size > MAX_AUDIO_BYTES:
        raise NarrationError("the audio file is larger than 200 MB", "audio_unreadable")
    folder = Path(data_dir) / "audio"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{turn_id}.*"):
        old.unlink(missing_ok=True)
    target = folder / f"{turn_id}{suffix}"
    shutil.copyfile(path, target)
    return target.name, target


def audio_file(data_dir: Path, record: dict[str, Any]) -> Optional[Path]:
    """The stored audio of a turn when the file is still there (the name never escapes the audio folder)."""
    name = Path(record["file"]).name
    path = Path(data_dir) / "audio" / name
    return path if path.is_file() else None
