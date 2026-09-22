# Usability report

First real use of Scheherazade's Hoard, walking the scenarios in
[USE_CASES.md](USE_CASES.md) twice: as a person in the browser and as an
agent over MCP stdio. This pass only records findings; the fixes come
next and each will be marked here when it lands.

## How it was walked

- **Data:** a realistic Spanish world built through MCP, not the demo:
  "Velamar" (gótico urbano, `pbta_2d6`), 34 entities (15 characters, 10
  places, 3 factions, 3 items, 2 lore entries, 1 creature) with stats and
  GM secrets, 9 relations, 3 threads, one 6-segment clock, and a 44-beat
  session with 6 logged 2d6 rolls, a death, a disappearance, 10 facts,
  an out-of-character pause, one deliberate mistake per kind a small
  model makes, and one undo. Plus an empty second world for first-run
  screens. Everything lived in `data-uxtest/` (gitignored).
- **Agent:** `scripts/agent_walkthrough.py` spawns the real
  `mcp_server.py` over stdio against the running app and plays UC2, UC3,
  UC5 and UC7 as tool calls: 119 calls, 65 checks, 4.6 s. The narrator's
  turns are scripted (no model runs in this environment); each is what a
  27B model would send after reading the brief.
- **Person:** `scripts/person_walkthrough.py` drives the interface with
  Playwright in Spanish at 1280x800, in English and dark at 1920x1080,
  and at 390x844; 43 screenshots, each one opened and read. For UC4 a
  stand-in llama-server on a scratch port replayed six realistic 27B
  replies (listed in UC4).
- **Speed:** every agent call answered in 26-212 ms (`world_check` is
  the slowest); every screen rendered in under half a second; the
  narrator round trip against the stand-in server took 120-210 ms. No
  tool result contained an image.

## Findings

Ranked by how much they hurt a real user. "Required" marks the issues
confirmed from live tests on a real machine, not only in this pass's
scripted walkthroughs.

### Blockers

1. **Faustus cannot find these tools in Spanish (required, live).**
   Scenario UC5/UC2. Faustus's prompt listing and tool index keep only
   the first 120 characters of line one of each description. Every
   docstring's line one is a wrapped fragment ("Roll dice and write the
   result to the audited log. Never invent a") with no Spanish word;
   the `Keywords:` line, where the Spanish triggers are, is never seen.
   A lexical picker over what Faustus sees found the right tool for 2 of
   21 intents ("tirar dados", "deshacer último turno", "exportar
   capítulo" all found nothing); over the full descriptions, 21 of 21.
   Fix: line one of every tool (≤110 chars) says what it does with 2-4
   English and Spanish triggers. *Area:* `mcp_server.py`, `docs/MCP.md`.

2. **Sloppy model JSON ends up in the story (standalone narrator).**
   Scenario UC4. Of six realistic 27B replies, two were parsed. The
   other four - typographic quotes (`“scene”`), a reply cut at the token
   limit, `//` comments with trailing commas, the delta nested under
   `"delta"` - were marked "sin cambios estructurados" and the raw JSON
   stayed in the narration; "Aceptar" wrote it into the transcript, and
   from there into the chapter. Recoverable items were lost (a
   complete fact and a clock tick before the cut). An unterminated
   fence leaves "```json" in the prose; with two fenced blocks only the
   first is read. `<think>` blocks are already stripped by Hoard Link.
   Fix: normalise quotes, strip comments, accept a nested `delta`,
   salvage the complete items of a truncated object, always cut
   JSON-looking text out of the narration, and test each shape.
   *Area:* `jsonx.py`, `narrator.py`, Play proposal card.

3. **A person cannot keep continuity without a model.** Scenarios UC1,
   UC8. Play offers Acción, Diálogo and Fuera de personaje but no
   Narración, although the no-model banner says "puedes seguir jugando
   escribiendo tú la narración". There is no way to set the scene
   (place, who is present, mood) from the interface, and the Bible can
   create an entity but not edit one: no status change (mark someone
   dead), no summary fix, no aliases, relations or facts. The PATCH
   route exists; the page does not use it. This breaks the repo's own
   rule that a person can do everything an agent can. *Area:*
   `PlayPage.tsx`, `BiblePage.tsx`.

4. **One unknown name in `scene.present` empties the scene.** Scenario
   UC2. `{"scene": {"present": ["iria"]}}` rejects "iria" (unknown) and
   leaves the scene with nobody present; the next brief has no cast. A
   small model referring to someone by first name silently loses the
   whole cast. (When some refs are valid, only those stay - beat 30 kept
   Iria and Marta when dead Mateo was refused.) Fix: when every present
   ref is rejected, keep the previous cast. *Area:* `delta.py`.

5. **The chapter is not manuscript-clean.** Scenario UC3. The export of
   the 44-beat night keeps the out-of-character pause, the 🎲 roll lines
   with "strong_hit", action turns as `> ` blockquotes, wraps Spanish
   raya dialogue ("—dice Rosalía—") in English quotes “…”, and is titled
   "# Session 1" with "*Velamar*" under it. Ids, JSON and the undone
   turn were correctly left out. Fix: a manuscript form that keeps only
   narration, dialogue (untouched) and actions as prose, with the
   session title. *Area:* `export.py`, Sessions page.

6. **There is no way to start or name a session.** Scenario UC3.
   Everything goes into "Session 1" forever (`store.start_session`
   exists but neither the interface nor MCP exposes it), so "export last
   night's chapter" exports the whole campaign. *Area:* `api.py`,
   `mcp_server.py`, Sessions/Play.

7. **The app has no family icon (required).** Every screen shows a
   generic feather tile; there is no favicon (the tab shows the browser
   default) and the READMEs have no icon. Fix: `app-icon.png` at the
   repo root, `favicon.ico` and `favicon-192.png` in `frontend/public`
   linked from `index.html`, the icon at 28 px in the header, and above
   both README titles. *Area:* frontend, READMEs.

### Annoying

8. **`world_context` returns about twice its budget.** UC2. The brief
   respects `budget_chars`, but the result repeats the same content as
   `scene`, `lore`, `threads` and `recent_turns`: 4,665 characters at
   the default 3,000 and 2,747 at 1,200. For a small-context model the
   budget is not what it pays. *Area:* `context.py`.

9. **First names do not resolve, and the error does not help.** UC5.
   `entity_get("Nuño")`, `entity_get("Iria")` and scene refs by first
   name fail with `not_found: no entity matches 'Nuño'`, while
   `world_check` does understand first names. The error could name the
   match ("did you mean Nuño Vidal (E5)?"). `thread_update` does not
   accept part of a title either. *Area:* `store.py` resolvers.

10. **`entity_upsert` over MCP silently drops `aliases`.** UC7. The HTTP
    route accepts aliases, description and tags; the MCP signature does
    not, and the extra argument is ignored, so the call succeeds and
    "la Ciega" never resolves. *Area:* `mcp_server.py`.

11. **An agent cannot add relations, facts or clocks outside a turn.**
    UC7. Relations and facts from notes have to go through an empty
    `system` turn (which then sits in the session's undo history); a
    clock cannot be created by an agent at all - the walkthrough had to
    use the interface's route. *Area:* `mcp_server.py`, `api.py`.

12. **"Who is dead, where is everyone, who knows what" have no direct
    answer.** UC5. `world_search("muerto")` and `world_search("dead")`
    return nothing (status is not searchable); `entity_get` does not say
    where someone was last seen (the last-seen place is computed inside
    `world_check` only); knowledge exists only as fact text ("Iria sabe
    que…"), found by a search for "Iria sabe" but not checkable.
    *Area:* `store.search_world`, `views.entity_detail`, `consistency.py`.

13. **`world_check` false positive on a dead character only mentioned.**
    UC5. "…la llave del faro que encontró junto a Mateo" is flagged as
    "Mateo Lür está muerto/a y la afirmación le hace actuar". ("Iria deja
    flores en la tumba de Mateo Lür" is correctly consistent.) *Area:*
    `consistency.py` dead-acting rule.

14. **The polished chapter can replace the story with junk.** UC3. With
    the stand-in model, "Capítulo pulido" returned a 100-character reply
    ending in a JSON fence in place of a 5,000-character chapter, marked
    `polished: true`. Nothing checks length, fences or truncation. And
    polish refuses chapters over 6,000 characters - any real night of
    play. *Area:* `api.py` chapter route, `export.py`.

15. **Play always opens at the top of the transcript.** UC2/UC4. With
    44+ turns, every visit, every refresh and every accepted beat needs
    a scroll to the latest turn. *Area:* `PlayPage.tsx`.

16. **Proposed scene changes are not reviewable.** UC4. The proposal
    card lists facts, updates and ticks with checkboxes (labels in
    English: "fact:") but not the scene move, cast or mood, which are
    applied on accept unseen. *Area:* `PlayPage.tsx`.

17. **Below 760 px there is no navigation.** UC8. The menu button has an
    inline `display: none` and no rule shows it, so on a narrow window or
    panel the sidebar cannot be opened. *Area:* `Header.tsx`,
    `global.css`.

18. **The relations map is unreadable at 34 entities.** UC8. The circular
    layout overlaps labels (the bottom places, relation labels at the
    top) and does not distinguish the dead or missing. *Area:*
    `MapPage.tsx`.

19. **A JSON backup over MCP floods the model's context.** UC7.
    `session_export(format="json")` pages a 66,000-character JSON string
    through the model, four pages at 20,000; there is no import tool.
    Import through the interface works (it renames to "Velamar
    (imported)"). *Area:* `api.py`.

20. **Mixed languages in a Spanish world.** All. Delta rejections are in
    English ("Mateo Lür is dead and cannot act") while `world_check`
    answers in Spanish; roll bands appear raw ("weak_hit") in the
    transcript and chapter; status badges say "dead"; the ruleset select
    shows "freeform"; Backends reasons are English; the dice log says
    "agent"; the default session title is "Session 1".

21. **Rolls are not attached to their turn over MCP.** UC2.
    `story_append` over MCP has no `rolls` argument (the HTTP body has),
    so the model pastes the roll into the text and the dice log is not
    linked to the turn. *Area:* `mcp_server.py`.

### Cosmetic

22. Assistant activity shows durations like "1.1414450000302168 ms" and
    no time of day. *Area:* `ActivityPage.tsx`.
23. "1 hilos abiertos" on the world card. *Area:* `WorldsPage.tsx`.
24. The dice tray defaults to 1d20 in a `pbta_2d6` world, and quick rolls
    are recorded as "Tirada …" whatever the interface language.
25. The MCP adapter logs every loopback request at INFO on stderr
    ("HTTP Request: POST …"), noise in the client's MCP log.
26. "Deshacer último turno" drops below the fold at 1280x800 once a
    continuity result is showing.
27. Narrar without a model leaves a console error (the expected 503).

## Fixes (first pass)

Small commits, each with a regression test; `pytest` went from 240 to
279 passing, `npm run build`, the MCP protocol test and the manifest
test all stayed green throughout. Commit hashes are on `main`.

**Blockers**

1. **Fixed** (`783e74c`). Every tool's docstring now leads with a short
   bilingual summary line ("Roll dice / tirar dados, ...") instead of a
   wrapped English fragment, so a picker that only reads the first ~120
   characters of line one still finds the right tool in Spanish. Test:
   `tests/test_mcp_tool_discovery.py` reproduces the exact naive
   word-matching picker from the walkthrough against all 16 tools.
2. **Fixed** (`dee8b39`). `jsonx.extract_json_span` now normalises curly
   quotes, strips `//`/`/* */` comments, accepts a payload nested under
   a key like `"delta"` (new `prefer_keys` parameter), and repairs an
   object cut off mid-value by keeping the complete items before the
   cut and closing what was left open. `narrator.py` passes
   `DELTA_KEYS` as `prefer_keys` (so an earlier stray or duplicate JSON
   block no longer wins) and no longer leaves a dangling ```` ```json ````
   marker in the narration when the model never closes the fence. All
   four sloppy shapes from the report now parse; tests in
   `tests/test_jsonx.py` and `tests/test_narrator.py`.
3. **Partially fixed** (`fd7c0d4`). Play now has a Narración mode tab
   alongside Acción/Diálogo/Fuera de personaje, reusing the existing
   `story_append` plumbing — verified live with Playwright (tab
   appears, typed narration is recorded and rendered as prose, no
   console errors). Left: setting the scene (place/cast/mood) from Play,
   and editing an existing Bible entity (status/summary/aliases). Both
   are real features, not bug fixes — a scene-editor form and an
   entity-edit form each need their own design, review and tests, and
   cramming them in was more likely to produce something half-baked than
   something a person would actually want to use. Left for a follow-up
   pass; the PATCH route Bible editing needs already exists
   (`api.py`'s `patch_entity_ep`).
4. **Fixed** (`33cc78f`). When every name given for `scene.present` is
   rejected (unknown, dead, ...), the previous cast now carries forward
   instead of being replaced by an empty list. Test:
   `test_one_unknown_name_does_not_empty_an_existing_cast` in
   `tests/test_delta.py`.
5. **Fixed** (`e9c698b`). The exported chapter drops roll and
   out-of-character turns entirely, renders actions in italics instead
   of a blockquote, and leaves Spanish raya dialogue untouched instead
   of wrapping it in English curly quotes. A session's auto-generated
   title is now localized ("Sesión 1" in a Spanish world). Tests in
   `tests/test_export.py` and `tests/test_store.py`.
6. **Fixed** (`c983c63`, `10076f7`). `POST /api/worlds/{world}/sessions`
   and `PATCH .../sessions/{session}` (plus the matching `session_start`
   and `session_rename` MCP tools) let a session be started and named,
   from the API/MCP and, since `10076f7`, from the Sesiones screen
   itself (a "Nueva sesión" button and an inline rename control) —
   verified live with Playwright: create with a title, create with the
   localized default, rename, no console errors. Tests in
   `tests/test_api.py`, `tests/test_store.py`,
   `tests/test_mcp_protocol.py`.
7. **Fixed** (`3b470ba`). `frontend/public/favicon.svg` linked from
   `index.html`, the same mark replacing the sidebar's generic Feather
   glyph, and both READMEs now show it next to the title. Test:
   `tests/test_branding.py`.

**Annoying**

22. **Fixed** (`6cd6603`). Activity now has a Hora/Time column and
    durations round to whole ms instead of 13 decimals.
23. **Fixed** (`6cd6603`). The Worlds card shows "1 entidad" / "1 hilo
    abierto" (singular) instead of the plural form at count 1.
25. **Fixed** (`6cd6603`). `mcp_server.py` sets the `httpx` logger to
    WARNING, so a tool call no longer prints an INFO line to stderr.
    Test: `test_httpx_request_logging_is_quiet_on_stdio`.
8–21 (except 9, partially touched by #4's fix in spirit but not
directly), 24, 26, 27: **left**. Each needs either a product decision
(#8's budget accounting, #14's polish-safety threshold, #16's proposal
UI, #18's map layout, #20's full bilingual audit) or backend work of a
size that did not fit alongside the blockers under "small commits" —
none of them block a person or an agent from using the app today, which
is why the blockers came first. They are unchanged from the numbered
list above and are good candidates for the next pass, roughly in this
order of value: #9 (first-name resolution — quick, high value), #12
(status/last-seen search), #16 (show the scene move in the proposal
card), #11 (agent-created clocks), #13 (the "junto a" false positive).

**Cosmetic:** 22, 23 and 25 fixed above; 24, 26, 27 left (all small,
none urgent).

## Re-walk after the fixes (second pass)

Both walkthroughs again, on fresh scratch data: the agent one over MCP
stdio (117 calls, 4.5 s, **66 of 69 checks**, up from 59 of 69 before
this pass) and the person one in Playwright at 1280x800, 1920x1080 dark
English and 390x844, with the stand-in model for UC4; every screenshot
was opened and read. The re-walk found that two step-6 fixes were
incomplete and a backup lost the play history; those are fixed here,
each with a regression test (pytest 279 -> 294):

- **#5 not fully fixed.** The chapter left raya dialogue alone only when
  the turn already began with a dash; what a model actually sends
  ("No ha vuelto —dice Rosalía—.") was still wrapped in English quotes.
  A Spanish world, or any line with a raya aside, now gets the opening
  raya (`645f7f2`).
- **#1 not fully fixed.** The line-one picker still sent "qué mundos hay"
  to `world_search`; `story_worlds` now leads with that phrase and a test
  runs the walkthrough's own picker over all 21 intents (`2f37c53`).
- **#3 finished.** Play has a scene editor (place, who is present, mood),
  written as an undoable system turn with a scene delta that never
  reaches the chapter; the Bible has an edit form (name, status, summary,
  description, aliases, tags, secrets) over the existing PATCH route, and
  a bad status there is a 400 instead of a 500 (`7303e98`).
- **#9 fixed.** A first name that fits one entity resolves ("Nuño",
  "iria" in a scene); several matches give an error that lists them with
  ids; upsert and duplicate checks stay exact (`f247409`).
- **#10 fixed.** `entity_upsert` over MCP forwards `aliases`,
  `description` and `tags` (`f0aeb1d`).
- **#12 partly fixed.** `world_search("¿quién ha muerto?")`, "dead",
  "desaparecidos" list everyone in that state first (`c9c5e3c`); where
  someone was last seen is still only in `world_check`.
- **New: a JSON backup lost the sessions.** Import rebuilt the world but
  dropped every session and turn although the export carried them. It
  now restores them with scenes remapped and undone turns still undone;
  no imported session becomes current, since undo snapshots are not
  carried over (`e7b61fe`).

| Use case | Verdict |
| --- | --- |
| UC1 First evening, no model | Works: world, entities, scene set by hand, narration, action and a 2d6 roll, no model asked for |
| UC2 Long session through MCP | Works: dead refused in scenes and flagged, "Nuño elsewhere" flagged, undo restores state, first names resolve. Caveat: `world_context` returns about 1.5x its budget (#8) |
| UC3 Clean chapter | Works: titled "Sesión 1", prose, italics for actions, raya dialogue, no ids, JSON, dice, OOC or undone turns, from the UI and paged over MCP. Polish not re-tested with a real model (#14) |
| UC4 App narrates on its own | Works with caveat: all six sloppy replies parse, no JSON in the story, items reviewable; the scene move is still applied without being shown in the card (#16) |
| UC5 Continuity questions | Works with caveat: who died, what Iria knows and "is it consistent" are one call each; "where was Nuño last seen" needs `world_check`, and the "junto a Mateo" false positive remains (#13) |
| UC6 Illustrate with Prospero | Not testable here (Prospero was not running); the button is correctly hidden |
| UC7 World from notes by an agent | Works: 34 entities with aliases ("la Ciega" resolves), relations, threads, clock; the backup re-imports with its sessions. Caveats: clocks and standalone relations still need the HTTP route or a system turn (#11); the JSON backup pages through the model (#19) |
| UC8 Fix by hand the next evening | Works with caveat: summary fixed, someone marked missing, threads, clocks, dice log, activity, two-step undo, keyboard, both themes and languages. The map still overlaps labels at 34 entities (#18) and below 760 px there is no navigation (#17) |

Still left from the ranked list: #8, #11, #13-#21 (except #12 in part),
#24, #26 and #27, for the reasons given above.

## What already works well

- Dead Mateo was refused in the scene while the rest of the cast stayed;
  Spanish statuses ("muerto", "desaparecido") were accepted; a Spanish
  role (`narrador`) got an actionable error listing the valid roles.
- `world_check` flagged dead Mateo acting (full and first name) and Nuño
  placed away from where he was last seen, citing the ids.
- `story_undo` brought Iria back to alive and the undone turn is struck
  through in Play and left out of the chapter.
- After 44 beats the final brief had the right place and cast, the canon
  fact about the black lantern and no dead character present.
- Accent-insensitive search, compact results (350-1,300 characters per
  `story_append`), no images in any result, and `<think>` blocks
  stripped before parsing.

## Not tested here

- A real 27B model: the narrator, the polish and the `world_check` judge
  ran against a stand-in server replaying realistic replies, or without
  a model.
- Faustus itself: its tool index was simulated (first 120 characters of
  line one, lexical match).
- Prospero's Hoard (UC6): it was not running; the Illustrate button was
  correctly hidden.
- The Windows launchers and a Windows browser.
