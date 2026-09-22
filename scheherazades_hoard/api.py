"""FastAPI application: HTTP API, browser-attack guard, and the audited
`/api/agent/*` surface that both the UI and the MCP adapter call through.

`create_app(data_dir, static_dir)` is the single factory used by
`__main__.py`, the tests (via `TestClient`), and the MCP protocol test
(which starts a real uvicorn server from it).
"""
from __future__ import annotations

import functools
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import __version__, backend, consistency, context as context_mod
from . import db, delta as delta_mod, dice, export, narrator, prospero, store, tables

SERVICE = "scheherazades-hoard"
DISPLAY_NAME = "Scheherazade's Hoard"
DEFAULT_PORT = 8816

_db_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class WorldCreate(BaseModel):
    name: str
    genre: str = ""
    tone: str = ""
    premise: str = ""
    ruleset: str = "freeform"
    language: str = "es"
    rules_text: str = ""
    style_notes: str = ""
    content_lines: list[str] = Field(default_factory=list)
    content_veils: list[str] = Field(default_factory=list)


class WorldUpdate(BaseModel):
    name: Optional[str] = None
    genre: Optional[str] = None
    tone: Optional[str] = None
    premise: Optional[str] = None
    ruleset: Optional[str] = None
    language: Optional[str] = None
    rules_text: Optional[str] = None
    style_notes: Optional[str] = None
    content_lines: Optional[list[str]] = None
    content_veils: Optional[list[str]] = None
    calendar: Optional[dict] = None


class WorldContextBody(BaseModel):
    world: str
    scene: Optional[dict] = None
    focus: Optional[str] = None
    include_secrets: bool = False
    budget_chars: int = 3000


class WorldSearchBody(BaseModel):
    world: str
    query: str
    kinds: Optional[list[str]] = None
    limit: int = 8


class EntityGetBody(BaseModel):
    world: str
    ref: str
    include_secrets: bool = False


class EntityUpsertBody(BaseModel):
    world: str
    kind: str
    name: str
    aliases: Optional[list[str]] = None
    summary: str = ""
    description: str = ""
    fields: Optional[dict] = None
    secrets: str = ""
    status: str = "alive"
    tags: Optional[list[str]] = None
    parent_id: Optional[str] = None


class EntityCreateBody(BaseModel):
    """Direct human creation via the Bible UI — no `world`, it's the path param."""
    kind: str
    name: str
    aliases: Optional[list[str]] = None
    summary: str = ""
    description: str = ""
    fields: Optional[dict] = None
    secrets: str = ""
    status: str = "alive"
    tags: Optional[list[str]] = None
    parent_id: Optional[str] = None


class EntityPatchBody(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    fields_patch: Optional[dict] = None
    fields: Optional[dict] = None
    secrets: Optional[str] = None
    status: Optional[str] = None
    aliases: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    name: Optional[str] = None


class RelationCreateBody(BaseModel):
    a: str
    b: str
    type: str
    note: str = ""
    since: str = ""


class FactCreateBody(BaseModel):
    text: str
    entity_ids: Optional[list[str]] = None
    canon: bool = False


class StoryAppendBody(BaseModel):
    world: str
    text: str = ""
    role: str = "narration"
    author: str = "agent"
    delta: Optional[dict] = None
    scene: Optional[dict] = None
    rolls: Optional[list[dict]] = None


class DiceRollBody(BaseModel):
    expression: str
    reason: str = ""
    world: Optional[str] = None
    who: str = "agent"
    seed: Optional[int] = None


class TableRollBody(BaseModel):
    world: str
    table: str
    seed: Optional[int] = None


class ThreadUpdateBody(BaseModel):
    world: str
    thread: str
    status: Optional[str] = None
    note: Optional[str] = None


class ThreadCreateBody(BaseModel):
    title: str
    status: str = "open"
    notes: str = ""


class ClockTickBody(BaseModel):
    world: str
    clock: str
    ticks: int = 1


class ClockCreateBody(BaseModel):
    name: str
    segments: int = 4
    on_full: str = ""


class TableCreateBody(BaseModel):
    name: str
    entries: list[dict]


class WorldCheckBody(BaseModel):
    world: str
    statement: str


class SessionExportBody(BaseModel):
    world: str
    session: Optional[str] = None
    format: str = "md"


class TimelineCreateBody(BaseModel):
    in_world_date: str = ""
    summary: str
    entity_ids: Optional[list[str]] = None


class NarrateBody(BaseModel):
    world: str
    action_text: str
    scene: Optional[dict] = None
    budget_chars: int = 3000


class BackendSettingsBody(BaseModel):
    llm_url: Optional[str] = None
    llm_model: Optional[str] = None
    faustus_url: Optional[str] = None
    faustus_token: Optional[str] = None
    allow_load: Optional[bool] = None


class EmptyBody(BaseModel):
    """No parameters — a POST body is still accepted (and may be omitted)
    so every agent tool is called the same way (POST JSON)."""


class StoryUndoBody(BaseModel):
    world: str


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(data_dir: Path, static_dir: Optional[Path] = None, port: int = DEFAULT_PORT) -> FastAPI:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(data_dir / "scheherazade.db")
    backend_json = data_dir / "backend.json"

    app = FastAPI(title=DISPLAY_NAME)
    app.state.conn = conn
    app.state.port = port
    app.state.data_dir = data_dir
    app.state.link = backend.Link(backend.LinkConfig.load(backend_json, app="scheherazades-hoard"))
    app.state.backend_json = backend_json

    # -- browser-attack guard (DNS rebinding + basic CSRF), all routes -----
    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.headers.get("host", "")
        hostname = host.split(":")[0]
        allowed_hostnames = {"127.0.0.1", "localhost"}
        expected_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if hostname not in allowed_hostnames or host not in expected_hosts:
            return JSONResponse(
                {"error": "forbidden_host", "message": f"unexpected Host header: {host!r}"},
                status_code=403,
            )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            own_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            if origin and origin not in own_origins:
                return JSONResponse(
                    {"error": "forbidden_origin", "message": f"unexpected Origin header: {origin!r}"},
                    status_code=403,
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"error": "forbidden_cross_site", "message": "cross-site request rejected"},
                    status_code=403,
                )
        return await call_next(request)

    def C() -> Any:
        return app.state.conn

    def L() -> backend.Link:
        return app.state.link

    # -- uniform error shape: JSON {"error","message"} with a 4xx status ---

    @app.exception_handler(store.NotFound)
    async def not_found_handler(request: Request, exc: store.NotFound):
        return JSONResponse({"error": "not_found", "message": str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse({"error": "bad_request", "message": str(exc)}, status_code=400)

    @app.exception_handler(backend.Unavailable)
    async def unavailable_handler(request: Request, exc: backend.Unavailable):
        return JSONResponse({"error": "llm_unavailable", "message": str(exc)}, status_code=503)

    @app.exception_handler(backend.BackendError)
    async def backend_error_handler(request: Request, exc: backend.BackendError):
        return JSONResponse({"error": "backend_error", "message": str(exc)}, status_code=502)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Every manual `raise HTTPException(status, {"error":..., "message":...})`
        # in this file already passes the right shape as `detail`; flatten it
        # instead of nesting under FastAPI's default {"detail": ...}.
        if isinstance(exc.detail, dict):
            return JSONResponse(exc.detail, status_code=exc.status_code)
        return JSONResponse({"error": "http_error", "message": str(exc.detail)}, status_code=exc.status_code)

    def agent_call(tool_name: str):
        """Decorator: runs the wrapped coroutine and records it in
        `agent_calls` (ok/error, duration) — this is the audit trail the
        Settings/"Assistant activity" screen shows. Errors are re-raised so
        the exception handlers above still produce the JSON error shape."""
        def decorator(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                start = time.monotonic()
                body = kwargs.get("body", args[0] if args else None)
                args_summary = body.model_dump_json() if isinstance(body, BaseModel) else str(body)
                try:
                    result = await fn(*args, **kwargs)
                except Exception as e:
                    with _db_lock:
                        store.log_agent_call(C(), tool_name, args_summary, (time.monotonic() - start) * 1000, False, str(e)[:300])
                    raise
                with _db_lock:
                    store.log_agent_call(C(), tool_name, args_summary, (time.monotonic() - start) * 1000, True)
                return result
            return wrapper
        return decorator

    # -- health & backend -------------------------------------------------

    @app.get("/api/health")
    async def health():
        with _db_lock:
            worlds = store.list_worlds(C())
        return {
            "service": SERVICE, "name": DISPLAY_NAME, "version": __version__,
            "status": "ok", "worlds": len(worlds),
        }

    @app.get("/api/backend")
    async def get_backend():
        status = await L().status()
        status["ffmpeg"] = None  # this app has no media pipeline; kept for a uniform Settings screen
        return status

    @app.post("/api/backend/recheck")
    async def recheck_backend():
        await L().resolve("llm", force=True)
        return await L().status()

    @app.post("/api/backend/settings")
    async def set_backend_settings(body: BackendSettingsBody):
        current: dict = {}
        if app.state.backend_json.exists():
            current = db.loads(app.state.backend_json.read_text(encoding="utf-8"), {})
        for key, value in body.model_dump(exclude_none=True).items():
            current[key] = value
        app.state.backend_json.write_text(db.dumps(current), encoding="utf-8")
        app.state.link = backend.Link(backend.LinkConfig.load(app.state.backend_json, app="scheherazades-hoard"))
        status = await app.state.link.status()
        return status

    # -- worlds (UI reads + direct human edits) ----------------------------

    @app.get("/api/worlds")
    async def list_worlds_ep():
        with _db_lock:
            return store.list_worlds(C())

    @app.get("/api/worlds/{world}")
    async def get_world_ep(world: str):
        with _db_lock:
            try:
                return store.get_world(C(), world)
            except store.NotFound as e:
                raise HTTPException(404, {"error": "not_found", "message": str(e)})

    @app.post("/api/worlds")
    async def create_world_ep(body: WorldCreate):
        with _db_lock:
            try:
                return store.create_world(C(), **body.model_dump())
            except ValueError as e:
                raise HTTPException(400, {"error": "bad_request", "message": str(e)})

    @app.patch("/api/worlds/{world}")
    async def update_world_ep(world: str, body: WorldUpdate):
        with _db_lock:
            try:
                return store.update_world(C(), world, **body.model_dump(exclude_none=True))
            except store.NotFound as e:
                raise HTTPException(404, {"error": "not_found", "message": str(e)})

    # -- entities (UI direct CRUD) -----------------------------------------

    @app.get("/api/worlds/{world}/entities")
    async def list_entities_ep(world: str, kind: Optional[str] = None):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            return store.list_entities(C(), wid, kind=kind)

    @app.get("/api/worlds/{world}/entities/{ref}")
    async def get_entity_ep(world: str, ref: str, include_secrets: bool = False):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                return _entity_detail(C(), wid, ref, include_secrets)
            except store.NotFound as e:
                raise HTTPException(404, {"error": "not_found", "message": str(e)})

    @app.post("/api/worlds/{world}/entities")
    async def create_entity_ep(world: str, body: EntityCreateBody):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                return store.create_entity(C(), wid, body.kind, body.name, **body.model_dump(exclude={"world", "kind", "name"}, exclude_none=True))
            except (store.NotFound, ValueError) as e:
                code = 404 if isinstance(e, store.NotFound) else 400
                raise HTTPException(code, {"error": "not_found" if code == 404 else "bad_request", "message": str(e)})

    @app.patch("/api/worlds/{world}/entities/{ref}")
    async def patch_entity_ep(world: str, ref: str, body: EntityPatchBody):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                return store.update_entity(C(), wid, ref, **body.model_dump(exclude_none=True))
            except store.NotFound as e:
                raise HTTPException(404, {"error": "not_found", "message": str(e)})

    @app.get("/api/worlds/{world}/relations")
    async def list_relations_ep(world: str, entity: Optional[str] = None):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            entity_id = store.resolve_entity_id(C(), wid, entity) if entity else None
            return store.list_relations(C(), wid, entity_id)

    @app.post("/api/worlds/{world}/relations")
    async def create_relation_ep(world: str, body: RelationCreateBody):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                a_id = store.resolve_entity_id(C(), wid, body.a)
                b_id = store.resolve_entity_id(C(), wid, body.b)
                return store.create_relation(C(), wid, a_id, b_id, body.type, body.note, body.since)
            except store.NotFound as e:
                raise HTTPException(404, {"error": "not_found", "message": str(e)})

    @app.get("/api/worlds/{world}/facts")
    async def list_facts_ep(world: str, entity: Optional[str] = None, limit: int = 50):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            entity_id = store.resolve_entity_id(C(), wid, entity) if entity else None
            return store.list_facts(C(), wid, entity_id, limit)

    @app.post("/api/worlds/{world}/facts")
    async def create_fact_ep(world: str, body: FactCreateBody):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                entity_ids = [store.resolve_entity_id(C(), wid, r) for r in (body.entity_ids or [])]
                return store.create_fact(C(), wid, body.text, entity_ids=entity_ids, canon=body.canon)
            except store.NotFound as e:
                raise HTTPException(404, {"error": "not_found", "message": str(e)})

    @app.get("/api/worlds/{world}/timeline")
    async def list_timeline_ep(world: str):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            return store.list_timeline(C(), wid)

    @app.post("/api/worlds/{world}/timeline")
    async def create_timeline_ep(world: str, body: TimelineCreateBody):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            entity_ids = [store.resolve_entity_id(C(), wid, r) for r in (body.entity_ids or [])]
            return store.create_timeline_event(C(), wid, body.in_world_date, body.summary, entity_ids=entity_ids)

    @app.get("/api/worlds/{world}/threads")
    async def list_threads_ep(world: str, status_: Optional[str] = None):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            return store.list_threads(C(), wid, status_)

    @app.post("/api/worlds/{world}/threads")
    async def create_thread_ep(world: str, body: ThreadCreateBody):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                return store.create_thread(C(), wid, body.title, body.status, body.notes)
            except ValueError as e:
                raise HTTPException(400, {"error": "bad_request", "message": str(e)})

    @app.get("/api/worlds/{world}/clocks")
    async def list_clocks_ep(world: str):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            return store.list_clocks(C(), wid)

    @app.post("/api/worlds/{world}/clocks")
    async def create_clock_ep(world: str, body: ClockCreateBody):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                return store.create_clock(C(), wid, body.name, body.segments, body.on_full)
            except ValueError as e:
                raise HTTPException(400, {"error": "bad_request", "message": str(e)})

    @app.get("/api/worlds/{world}/tables")
    async def list_tables_ep(world: str):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            return store.list_tables(C(), wid)

    @app.post("/api/worlds/{world}/tables")
    async def create_table_ep(world: str, body: TableCreateBody):
        with _db_lock:
            try:
                wid = store.resolve_world_id(C(), world)
                return store.create_table(C(), wid, body.name, body.entries)
            except ValueError as e:
                raise HTTPException(400, {"error": "bad_request", "message": str(e)})

    @app.get("/api/worlds/{world}/sessions")
    async def list_sessions_ep(world: str):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            return store.list_sessions(C(), wid)

    @app.get("/api/worlds/{world}/sessions/{session}/turns")
    async def list_turns_ep(world: str, session: str):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            session_id = store.resolve_session_id(C(), wid, session)
            return store.list_turns(C(), session_id)

    @app.get("/api/worlds/{world}/dice_log")
    async def list_dice_log_ep(world: str, limit: int = 20):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            return store.list_dice_log(C(), wid, limit)

    @app.get("/api/worlds/{world}/bible.md")
    async def bible_md_ep(world: str, include_secrets: bool = False):
        with _db_lock:
            wid = store.resolve_world_id(C(), world)
            text = export.world_bible_markdown(C(), wid, include_secrets)
        return PlainTextResponse(text, media_type="text/markdown")

    @app.post("/api/worlds/{world}/illustrate")
    async def illustrate_ep(world: str, body: dict):
        available = await prospero.is_available()
        if not available:
            raise HTTPException(503, {"error": "prospero_unavailable", "message": "Prospero's Hoard is not running."})
        url = await prospero.illustrate_scene(
            body.get("scene_brief", ""), body.get("location_name", ""), body.get("mood", "")
        )
        if not url:
            raise HTTPException(502, {"error": "illustrate_failed", "message": "Prospero could not generate an image."})
        return {"image_url": url}

    @app.get("/api/agent_calls")
    async def list_agent_calls_ep(limit: int = 50):
        with _db_lock:
            return store.list_agent_calls(C(), limit)

    @app.post("/api/worlds/{world}/narrate")
    async def narrate_ep(world: str, body: NarrateBody):
        try:
            with _db_lock:
                wid = store.resolve_world_id(C(), world)
            result = await narrator.narrate(L(), C(), wid, body.action_text, scene=body.scene, budget_chars=body.budget_chars)
            return result
        except store.NotFound as e:
            raise HTTPException(404, {"error": "not_found", "message": str(e)})
        except backend.Unavailable as e:
            raise HTTPException(503, {"error": "llm_unavailable", "message": str(e)})

    # -- agent-facing tools (audited, MCP-mirrored) ------------------------

    @app.post("/api/agent/story_worlds")
    @agent_call("story_worlds")
    async def a_story_worlds(body: EmptyBody = EmptyBody()):
        return store.list_worlds(C())

    @app.post("/api/agent/story_world_create")
    @agent_call("story_world_create")
    async def a_story_world_create(body: WorldCreate):
        return store.create_world(C(), **body.model_dump())

    @app.post("/api/agent/world_context")
    @agent_call("world_context")
    async def a_world_context(body: WorldContextBody):
        wid = store.resolve_world_id(C(), body.world)
        return context_mod.world_context(C(), wid, body.scene, body.focus, body.include_secrets, body.budget_chars)

    @app.post("/api/agent/world_search")
    @agent_call("world_search")
    async def a_world_search(body: WorldSearchBody):
        wid = store.resolve_world_id(C(), body.world)
        return store.search_world(C(), wid, body.query, body.kinds, body.limit)

    @app.post("/api/agent/entity_get")
    @agent_call("entity_get")
    async def a_entity_get(body: EntityGetBody):
        wid = store.resolve_world_id(C(), body.world)
        return _entity_detail(C(), wid, body.ref, body.include_secrets)

    @app.post("/api/agent/entity_upsert")
    @agent_call("entity_upsert")
    async def a_entity_upsert(body: EntityUpsertBody):
        wid = store.resolve_world_id(C(), body.world)
        return store.upsert_entity(C(), wid, body.kind, body.name, **body.model_dump(exclude={"world", "kind", "name"}, exclude_none=True))

    @app.post("/api/agent/story_append")
    @agent_call("story_append")
    async def a_story_append(body: StoryAppendBody):
        wid = store.resolve_world_id(C(), body.world)
        session = store.get_or_create_current_session(C(), wid)
        valid, rejected = delta_mod.validate_delta(C(), wid, body.delta or {})
        result, undo = delta_mod.apply_delta(C(), wid, session["id"], valid)
        scene = result.get("scene") or body.scene or {}
        turn = store.append_turn(
            C(), wid, session["id"], body.role, body.author, text=body.text,
            rolls=body.rolls or [], scene=scene, delta=result, applied=True, undo_snapshot=undo,
        )
        return {"turn": turn, "rejected": rejected}

    @app.post("/api/agent/dice_roll")
    @agent_call("dice_roll")
    async def a_dice_roll(body: DiceRollBody):
        result = dice.roll(body.expression, seed=body.seed)
        wid = store.resolve_world_id(C(), body.world) if body.world else None
        entry = store.log_dice(
            C(), body.expression, result.total, [d.to_dict() for d in result.dice],
            seed=body.seed, reason=body.reason, who=body.who, world_id=wid,
        )
        return {**result.to_dict(), "log_id": entry["id"]}

    @app.post("/api/agent/table_roll")
    @agent_call("table_roll")
    async def a_table_roll(body: TableRollBody):
        wid = store.resolve_world_id(C(), body.world)
        return tables.roll_table(C(), wid, body.table, seed=body.seed)

    @app.post("/api/agent/thread_update")
    @agent_call("thread_update")
    async def a_thread_update(body: ThreadUpdateBody):
        wid = store.resolve_world_id(C(), body.world)
        return store.update_thread(C(), wid, body.thread, body.status, body.note)

    @app.post("/api/agent/clock_tick")
    @agent_call("clock_tick")
    async def a_clock_tick(body: ClockTickBody):
        wid = store.resolve_world_id(C(), body.world)
        return store.tick_clock(C(), wid, body.clock, body.ticks)

    @app.post("/api/agent/world_check")
    @agent_call("world_check")
    async def a_world_check(body: WorldCheckBody):
        wid = store.resolve_world_id(C(), body.world)

        async def chat_fn(prompt: str) -> str:
            result = await L().chat([{"role": "user", "content": prompt}], max_tokens=400, temperature=0.0)
            return result.text

        return await consistency.world_check(C(), wid, body.statement, chat_fn=chat_fn)

    @app.post("/api/agent/session_export")
    @agent_call("session_export")
    async def a_session_export(body: SessionExportBody):
        wid = store.resolve_world_id(C(), body.world)
        if body.format == "json":
            return export.export_world_json(C(), wid)
        if body.session:
            text = export.session_to_markdown(C(), wid, body.session)
        else:
            text = export.world_bible_markdown(C(), wid)
        return {"format": "md", "text": text}

    @app.post("/api/agent/story_undo")
    @agent_call("story_undo")
    async def a_story_undo(body: StoryUndoBody):
        wid = store.resolve_world_id(C(), body.world)
        session = store.get_or_create_current_session(C(), wid)
        last_turn = store.get_last_turn(C(), wid, session["id"])
        if not last_turn:
            raise HTTPException(404, {"error": "not_found", "message": "no turn to undo"})
        delta_mod.undo_last(C(), wid, last_turn)
        return {"undone_turn_id": last_turn["id"]}

    # story_undo's body is a plain dict {"world": "..."}; give it a model too
    # so FastAPI/TestClient JSON works the same as the other agent routes.

    def _entity_detail(conn_, world_id: str, ref: str, include_secrets: bool) -> dict:
        e = store.get_entity(conn_, world_id, ref)
        if not include_secrets:
            e = {k: v for k, v in e.items() if k != "secrets"}
        e["relations"] = store.list_relations(conn_, world_id, e["id"] if "id" in e else store.resolve_entity_id(conn_, world_id, ref))
        e["facts"] = store.list_facts(conn_, world_id, store.resolve_entity_id(conn_, world_id, ref), limit=50)
        return e

    # -- static frontend ----------------------------------------------------

    if static_dir and Path(static_dir).exists():
        index_file = Path(static_dir) / "index.html"

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            candidate = Path(static_dir) / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            if index_file.exists():
                return FileResponse(index_file)
            return HTMLResponse("<h1>Scheherazade's Hoard</h1><p>Frontend not built.</p>")
    else:
        @app.get("/")
        async def no_frontend():
            return HTMLResponse(
                "<h1>Scheherazade's Hoard</h1>"
                "<p>The frontend has not been built yet. Run "
                "<code>cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</code>.</p>"
            )

    return app
