# Scheherazade's Hoard
### Who's alive? Who's where? What have you promised them?
**A world-state and continuity keeper for interactive fiction and tabletop play — it remembers everything a language model forgets, and hands the narrator exactly the slice it needs for the next scene.**

[Español](README.es.md) · [Run locally](#run-locally-on-windows) · [Connect an AI](docs/MCP.md) · [Portfolio](https://luissalet.github.io/Portfolio/#projects)

![The Play screen, mid-scene, with the dice tray and threads/clocks panel](docs/media/02-play.png)
*Actual application, demo data ("El Archipiélago de Sal", an original setting seeded by `--demo`).*

## Why

Language models are good narrators and terrible continuity editors. After
an hour of interactive fiction or a tabletop session they forget who knows
what, resurrect dead characters, move towns, lose the plot threads and
fudge dice. Scheherazade keeps the **world state outside the model** —
entities, relationships, secrets, places, a chronology, open threads,
clocks, tables and an audited dice log — and builds the narrator a
compact, ranked, budget-bound brief for the next scene, then records what
that scene actually changed. It can narrate on its own with a shared
local model, or hand its tools to another AI (Faustus) so that AI
narrates while this app remembers everything.

## What is implemented

| Area | Available now | Boundary |
| --- | --- | --- |
| World state | Entities (character/location/faction/item/lore/creature), relations, facts with provenance, timeline, threads, clocks, random tables — SQLite + FTS5, accent-insensitive Spanish search | No multi-user editing; one local writer |
| Dice | Full grammar (`NdM`, `+/-`, `kh/kl`/`dh/dl`, exploding `!`, `adv`/`dis`, fate dice), `check(dc, mod)` and `move(stat)` helpers, seeded reproducibility, audited log | No physical dice-image rendering |
| Context builder | Deterministic, ranked, budget-bound `world_context()` with citable short ids | Ranking is lexical/rule-based, not embeddings-based semantic search |
| Delta engine | Atomic apply (SQLite `SAVEPOINT`), per-item validation, full undo of the last turn | One level of undo (the last turn), not a full history stack |
| Narrator (standalone) | Builds the prompt, calls the shared model backend, parses narration + delta robustly (fenced JSON, bare braces, trailing-comma repair) | Non-streaming; a spinner, not token-by-token output |
| Consistency check | Three concrete rules (dead-but-acting, location mismatch, contradicted relation) plus an optional LLM judge citing fact ids | Cannot catch contradictions no rule covers and no fact makes explicit |
| Export | Session → Markdown chapter (optional LLM polish pass), world bible → Markdown, full JSON export/import | Polish pass is instructed not to add facts but is not formally verified against the source |
| Illustrations | Calls Prospero's Hoard's agent API when it is running; hidden otherwise | Requires that separate app; not built into this one |
| Shared model backend | Resolves an explicit override, a connected AI's model registry, or a loopback local server, in that order; every feature works with no model connected, visibly degraded | Built as a local adapter (`backend.py`) matching the shared interface rather than the vendored shared package — see below |
| UI | Play, Bible, Map of relations (SVG), Timeline, Threads & clocks (kanban + segmented-circle clocks), Tables, Sessions, Dice log, Backends, Assistant activity, Settings; ES/EN, light/dark | Map layout is a fixed circular layout, not a physics simulation |

**Boundary — the shared backend adapter.** The house convention for this
family of apps is to vendor a shared "model backend" package so every app
resolves a model the same way. At the point this app was built, that
shared package was still being finished by a parallel effort, so this app
implements the same public shape itself, in `backend.py` (`resolve()` /
`status()` / `wait_idle()` / `chat()`, the same states and error types).
Swapping in the vendored package later is a drop-in replacement of that
one file; nothing else in the app depends on how it is implemented.

## Connect it to Faustus

The app declares itself with `faustus-plugin.json`. Start the app, then in
Faustus: **Connectors → Nearby apps → Add**. Faustus finds it by scanning
loopback ports and reading that manifest.

| Tool | Read-only | What it does |
| --- | --- | --- |
| `story_worlds()` | yes | List every world with counts and current session |
| `story_world_create(...)` | no | Create a new world |
| `world_context(world, ...)` | yes | The narrator's brief for the next scene |
| `world_search(world, query, ...)` | yes | Search entities/facts |
| `entity_get(world, ref, ...)` | yes | One entity with relations and facts |
| `entity_upsert(world, kind, name, ...)` | no | Create or update an entity |
| `story_append(world, text, ...)` | no | Record a turn and apply a delta |
| `dice_roll(expression, ...)` | no | Roll dice with an audited log |
| `table_roll(world, table)` | no | Roll on a random table |
| `thread_update(world, thread, ...)` | no | Advance/resolve/abandon a thread |
| `clock_tick(world, clock, ticks=1)` | no | Advance a clock |
| `world_check(world, statement)` | yes | Check a statement against established facts |
| `session_export(world, ...)` | yes | Export a chapter / the bible / full JSON |
| `story_undo(world)` | no | Revert the last turn |

Full argument lists, return shapes and limits: [`docs/MCP.md`](docs/MCP.md).

It also works with any other MCP client over stdio:

```json
{
  "mcpServers": {
    "scheherazade": {
      "command": "/absolute/path/to/scheherazades-hoard/.venv/Scripts/python.exe",
      "args": ["/absolute/path/to/scheherazades-hoard/scheherazades_hoard/mcp_server.py"],
      "env": { "SCHEHERAZADE_URL": "http://127.0.0.1:8816" }
    }
  }
}
```

## Run locally on Windows

Double-click **`Iniciar Scheherazade's Hoard.cmd`** (first run creates the
virtual environment, installs dependencies and builds the frontend
automatically; it opens the app in your browser once it is ready). Stop
it with **`Detener Scheherazade's Hoard.cmd`**.

Manual steps, from the repo root, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
cd frontend; npm ci; npm run build; cd ..
.venv\Scripts\python.exe -m scheherazades_hoard --demo
```

`--demo` uses a synthetic seeded world in `data-demo/` instead of your
real `data/`, so you can try everything without touching (or needing) any
real data. Drop `--demo` for your own worlds; add `--no-browser` to skip
the automatic tab.

## Architecture

Modules, data model, the atomic delta engine, and the decisions behind
them: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Tests

```
python -m pytest tests/ -q
```

171 tests, offline by default (no network, no real model — the narrator,
backend and Prospero adapters are exercised through `httpx.MockTransport`
and mocked HTTP calls), running in under 10 seconds. Coverage includes
the full dice grammar and seeded reproducibility, the context builder's
budget/ranking/secret-exclusion, delta validation and atomic apply +
undo, JSON extraction robustness, the consistency checker's rules,
accent-insensitive FTS search, Markdown/JSON export, and an MCP protocol
test that spawns the real adapter over stdio against a live instance of
the app (`mcp.client.stdio`, `list_tools` plus a full
create-world → roll → append → undo round trip).

`npm run build` (inside `frontend/`) runs `tsc -b && vite build` with
TypeScript strict mode, `noUnusedLocals` and `noUnusedParameters` on.

## Privacy and limits

- Binds `127.0.0.1` only; no telemetry; no network access except a model
  call you triggered (the shared backend, or Prospero's Hoard for
  illustrations), and both are visibly optional — every feature that
  does not need a model keeps working without one.
- Your worlds live in `data/` (gitignored) as a local SQLite file. There
  is no cloud sync and no account.
- A dead character can still be referenced in narration text; only
  *acting* as one is caught by the consistency check. Undo covers the
  last turn, not a full history stack.
- The narrator's structured output is best-effort parsing of free text;
  a genuinely malformed reply is kept as narration with `unparsed: true`
  rather than silently dropped or guessed at.
