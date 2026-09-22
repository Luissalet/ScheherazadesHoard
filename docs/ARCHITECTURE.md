# Architecture

## Process model

One process: `python -m scheherazades_hoard` starts a single `uvicorn`
server (default `127.0.0.1:8816`) serving both the JSON API and the built
React SPA (`frontend/dist`, SPA-fallback to `index.html`). There is no
background worker or second process — every operation here completes
within an HTTP request; nothing in this app is slow enough to need a job
queue (`world_context`, `story_append` and `world_check` are all
sub-second against SQLite; only a narrator call to a language model can
take longer, and that call is a plain awaited `httpx` request with a
spinner in the UI, not a background job).

On start the process writes its own pid to `<data dir>/scheherazade.pid`
(removed on a clean shutdown) for `scripts/stop.ps1`: on Windows the
`.venv\Scripts\python.exe` that the launcher starts is a small redirector
whose child is the real interpreter, so the pid `Start-Process` returns
is not the one holding the port. It also attaches a rotating
`<data dir>/logs/app.log` (1 MB x 3) with tool names, timings and error
types only.

The MCP adapter (`scheherazades_hoard/mcp_server.py`) is launched as a
**separate** process over stdio (by Faustus, or any MCP client) and talks
to the running app over loopback HTTP — it never touches SQLite directly
and imports nothing from the `scheherazades_hoard` package, so it works
even if an MCP client spawns it with a different Python resolution than
the app's own venv would use for its dependencies.

## Modules (`scheherazades_hoard/`)

| Module | Responsibility |
| --- | --- |
| `db.py` | SQLite schema (WAL mode), FTS5 virtual tables over entities and facts (`unicode61 remove_diacritics 2`, for accent-insensitive Spanish search), `connect()` / `new_id()` / `now()` / json helpers. |
| `views.py` | The compact, secret-free shapes the agent tools return (entity/fact/thread/clock/world briefs, relations seen from one entity, what a delta applied, a scene as refs and names). The UI keeps using the richer REST endpoints. |
| `store.py` | CRUD for every domain object (worlds, entities, relations, facts, timeline events, threads, clocks, tables, sessions, turns, dice log, agent calls). Every mutating function takes `commit: bool = True` so callers that need atomicity across several writes (see `delta.py`) can defer the commit to one enclosing transaction. |
| `dice.py` | The dice grammar: `NdM`, `+/-` constants, `kh/kl`/`dh/dl` (keep/drop highest/lowest), exploding `!`, `adv(d20)`/`dis(d20)`, `dF` fate dice, plus `check(dc, mod)` (d20, crit on natural 20/1) and `move(stat)` (2d6, 6-/7-9/10+ bands). Pure functions, no I/O; `secrets.SystemRandom` unless a `seed` is given, in which case the roll uses `random.Random(seed)` and the seed is recorded so it is reproducible. |
| `tables.py` | Random table rolling, resolving nested `[[Other Table]]` references. |
| `context.py` | `world_context()` — the heart of the app. Deterministic ranking (canon facts and facts mentioning present entities score highest, then recency) over FTS5 candidates, assembled into a compact, budget-bound brief with short citable ids (`E1`, `F1`, `T1`, `C1`). |
| `delta.py` | The scene-delta schema and its engine: `validate_delta()` rejects, item by item, unknown ids, a dead character in the scene, a move to something that is not a location, duplicate names or aliases, renames onto another entity, bad statuses and malformed items; `record_turn()` applies the valid items and appends the turn that carries them inside one `SAVEPOINT`, merging the scene into the previous one; `undo_last()` reverses exactly what a turn changed, newest change first. |
| `consistency.py` | `world_check()` — lexical retrieval of candidate facts plus three concrete rules (dead-but-acting, location mismatch, contradicted relation), and an optional LLM-judge pass over the same candidates that must cite real fact ids. |
| `jsonx.py` | Robust JSON extraction from free-form model text: fenced code blocks, balanced-brace bare-object extraction, trailing-comma repair. Never raises — callers get `None` and treat the narration as `unparsed` instead. |
| `export.py` | Session → Markdown chapter (the API offers an optional polish by the shared model, which falls back to the plain chapter with the reason), world bible → Markdown (one section per entity kind), and full JSON export/import (format tag `scheherazades-hoard-world-export`), sessions and turns included; undo snapshots are not carried over, so no imported session becomes current. |
| `hoard_link/` | Hoard Link, the shared model-backend resolver, vendored unmodified (`VENDORED.txt` names the public source and version). |
| `backend.py` | This app's thin wrapper over Hoard Link (see below). |
| `narrator.py` | Standalone-mode narration: builds the system/user prompt from `world_context()` plus the player's action, calls the backend, and splits the model's reply into narration prose and a delta with `jsonx`. |
| `prospero.py` | Optional illustration adapter — checks `127.0.0.1:8815/api/health` for Prospero's Hoard and, if present, calls its agent API; fails closed (returns `False`/`None`) on any error so this feature never blocks the rest of the app. |
| `demo.py` | `seed_demo_world()` — idempotent synthetic world ("El Archipiélago de Sal": 14 entities, 5 characters with secrets, 7 relations, 6 facts, 2 timeline events, 3 threads, 2 clocks, 2 tables, one 13-turn session recorded through `record_turn()` with two seeded, logged 2d6 moves), used by `--demo` and by the screenshots script. |
| `api.py` | `create_app()` — FastAPI app: the browser-attack guard middleware, exception handlers, every `/api/agent/<tool>` endpoint (exactly what the MCP adapter calls), the richer UI CRUD endpoints, and static-file serving for the SPA. |
| `mcp_server.py` | The standalone stdio MCP adapter described in `docs/MCP.md`. |
| `__main__.py` | CLI entry point (`--port`, `--data-dir`, `--demo`, `--no-browser`). |

## Data model

SQLite (stdlib `sqlite3`, WAL mode), one file per data directory. Core
tables: `worlds`, `entities`, `relations`, `facts`, `timeline_events`,
`threads`, `clocks`, `random_tables`, `sessions`, `turns`, `dice_log`,
`agent_calls`, plus the `entities_fts` / `facts_fts` FTS5 virtual tables.
Every entity/fact/thread/clock has a per-world `seq` column with a unique
index, which is how short, stable, citable refs (`E12`, `F3`, `T1`, `C2`)
stay meaningful across a long-running world without ever renumbering.

`data/` (or `--data-dir`) holds the live database; `--demo` uses a
separate `data-demo/` directory seeded with synthetic data, so the app
can be tried, screenshotted and shared without ever touching a real
world's file.

## The shared model backend (Hoard Link)

By design, this app never starts or loads a model of its own. Hoard Link
is vendored unmodified in `scheherazades_hoard/hoard_link/`
and resolves the `llm` capability in this order: explicit configuration
(`data/backend.json`, written by the Settings screen, and `HOARD_LLM_URL`
/ `HOARD_LLM_MODEL` / `HOARD_FAUSTUS_URL` / `HOARD_FAUSTUS_TOKEN`), then
Faustus's model registry (the server and model Faustus already uses), then
servers already running on loopback (llama.cpp on 8080-8090, resident
Ollama models, an OpenAI-compatible server on 1234). Probes run in
parallel, are cached for 30 s and never raise; with nothing reachable the
result is `unavailable` with one reason per source.

`backend.py` adds only what is specific to this app: it maps the Settings
form's flat fields onto Hoard Link's `backend.json` schema (an empty
field clears an override), builds `GET /api/backend` without the token
(`token_set: true` instead), and keeps the app starting on defaults, with
the error shown, if `backend.json` is broken. "Re-check" builds a fresh
`Link`, which empties the probe cache.

Model-dependent features (the standalone narrator, `world_check`'s judge,
the polished chapter) say what is missing when nothing resolves; the
rest of the app does not need a model.

## HTTP API

- Every route is guarded by a middleware that rejects requests whose
  `Host` header is not `127.0.0.1:<port>` / `localhost:<port>` (DNS
  rebinding), and, for any non-GET/HEAD/OPTIONS request, rejects a
  present `Origin` that is not the app's own origin or a
  `Sec-Fetch-Site: cross-site` header. There is no CORS layer — this is a
  local, single-origin app.
- `/api/agent/<tool>` (POST JSON) is the agent surface: one endpoint per
  MCP tool, returning exactly what that tool returns, so the same
  `TestClient`-tested logic backs both the UI (which calls these same
  endpoints, via `frontend/src/lib/api.ts`'s `agent()` helper, for
  anything an agent could also do) and the MCP adapter.
  Errors are always `{"error": "<code>", "message": "<actionable text>"}`
  with a 4xx/5xx status; a custom exception handler flattens FastAPI's
  default `HTTPException` shape to match.
- Agent results are compact views (`views.py`): ids and short text, no
  timestamps, no secrets unless asked. Long exports are paged.
- Every `/api/agent/*` call is recorded in `agent_calls` (tool, argument
  summary, duration, ok/error) and shown in the UI's "Assistant activity"
  page. The UI marks its own requests with `X-Hoard-Client: ui` and those
  are not recorded, so the page shows what an agent did, not the human's
  clicks. (Any local process could send that header; the audit is for
  reviewing a cooperative model, not a security boundary.)
- The SPA file server resolves every path and serves only files inside
  `frontend/dist`; unknown `/api/*` paths are JSON 404s. Responses carry
  `Content-Security-Policy: frame-ancestors 'self' http://127.0.0.1:* http://localhost:*`
  (loopback apps such as Faustus may frame the UI, web pages may not),
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.

## Frontend

React 19 + Vite 6 + TypeScript (strict — `noUnusedLocals` /
`noUnusedParameters` on, `npm run build` runs `tsc -b && vite build`),
plain CSS custom properties (no Tailwind), `lucide-react` icons,
`@fontsource-variable/cormorant-garamond` for story text and
`@fontsource-variable/inter` for the interface. A left sidebar switches
between per-world sections (Play, Bible, Map of relations, Timeline,
Threads & clocks, Tables, Sessions, Dice log) and global ones (Worlds,
Backends, Assistant activity, Settings). Light/dark theme follows
`prefers-color-scheme` with a manual override persisted in
`localStorage`; the ES/EN interface language follows `navigator.language`
by default with a header toggle, all strings in one `src/lib/i18n.ts`
dictionary. No `window.confirm`/`alert` anywhere — destructive actions
(undo, delete) use an inline two-step confirm button instead, since a
native dialog would freeze a browser-automation tab driving the UI.

## Decisions worth calling out

- **SQLite over anything heavier.** A single local writer, no concurrent
  multi-process access, WAL mode is enough for responsiveness, and it
  needs zero setup on a Windows (or any) desktop.
- **One transaction per turn via `SAVEPOINT`, not an ORM.** The domain
  is small enough that a hand-rolled `SAVEPOINT record_turn` / `RELEASE`
  / `ROLLBACK TO` in `delta.py`, with every `store.py` write taking
  `commit=False` inside it, is more legible than an ORM for one feature.
  The turn is part of the transaction so that a failure can never leave
  applied changes without a turn to undo them (a model retrying would
  otherwise apply them twice).
- **The narrator's JSON is treated as unreliable text, not a guaranteed
  contract.** `jsonx.py` exists because language models wrap JSON in
  prose, fence it inconsistently, and leave trailing commas; failing hard
  on a parse error would lose an otherwise-good scene, so the app instead
  keeps the narration and marks the delta `unparsed`.
- **Everything an agent can do, a human can also do through the UI**, via
  the same `/api/agent/*` endpoints (world_check is the Play screen's
  continuity box, session_export the Sessions page, and so on); the
  logic lives once, in the core modules. The UI's extras (direct Bible
  edits, the standalone narrator, import) use REST routes of their own.
