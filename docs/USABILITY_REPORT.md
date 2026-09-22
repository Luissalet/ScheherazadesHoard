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
confirmed from live tests on a real machine.

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
