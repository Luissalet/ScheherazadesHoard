# Use cases

Eight concrete scenarios for Scheherazade's Hoard, written before walking
the app as its first real user. They are grounded in one persona: a
solo player and writer who runs interactive fiction with a local
language model, often building worlds in Spanish, and pastes finished
sessions into a separate manuscript or writing tool. Faustus is their AI
workspace; Prospero's Hoard is the sibling app that makes images.

The walkthroughs that exercise them are `scripts/agent_walkthrough.py`
(over MCP stdio) and `scripts/person_walkthrough.py` (Playwright). What
happened is in [USABILITY_REPORT.md](USABILITY_REPORT.md).

---

## UC1 - First evening: a world from nothing, in the interface

- **Who:** the player, on the first night after installing, no model
  running yet.
- **Goal:** create a world, its first characters and places, and play a
  first scene by hand.
- **Start:** the app open on Worlds; no world, no model server.
- **Steps:**
  1. Worlds -> "Nuevo mundo": name, genre, tone, premise, ruleset
     (`pbta_2d6`), language Español -> Crear.
  2. Biblia -> "+": a protagonist, two places, one antagonist.
  3. Hilos y relojes -> a first thread and a 6-segment clock.
  4. Jugar: set where the scene is and who is present, write the opening
     narration themself, an action, a 2d6 roll from the dice tray.
- **Done:** the Play screen shows the scene (place, cast, mood), the turns
  in order and the roll with its band; nothing asked for a model.

## UC2 - A long solo session narrated by a local model through MCP

- **Who:** the player, playing in Spanish; Faustus narrates with a 27B
  local model on llama.cpp and uses this app's tools.
- **Goal:** a 40+ turn night of play in which continuity holds: who is
  dead, where everyone is, who knows what.
- **Start:** the world "Velamar" (34 entities: 15 characters, 10 places,
  3 factions, 3 items, 2 lore entries, 1 creature, 7 relations, 2
  threads, one 6-segment clock), empty session.
- **Steps (what the model does):** `story_worlds` -> for each beat
  `world_context(world)` -> narrate -> `dice_roll(expr, reason, world)`
  when the outcome is uncertain -> `story_append(world, text, role,
  delta)` with moves, a death (Mateo, beat 19), a disappearance (Álvaro),
  facts about what Iria and Lucio learn, new threads, clock ticks. The
  model makes the mistakes a small model makes: it puts dead Mateo back
  in a scene, sends a role in Spanish (`narrador`), refers to people by
  first name, and writes one turn the player wants taken back
  (`story_undo`).
- **Done:** after 44 beats `world_context` puts the right people in the
  right place, the dead are refused in scenes and flagged by
  `world_check`, "Nuño elsewhere than last seen" is flagged, the undone
  turn is gone from state and chapter, and a question like "¿qué sabe
  Iria de la llave?" can be answered from tool results alone.

## UC3 - Export a clean chapter for the manuscript

- **Who:** the player, the morning after UC2.
- **Goal:** a chapter they can paste into their manuscript tool without
  cleaning it by hand.
- **Start:** the 44-beat session of UC2.
- **Steps:** Sesiones -> "Exportar capítulo (Markdown)" (and, as an
  agent, "Faustus, exporta el capítulo de anoche" -> `session_export`
  paged with `next_offset`); optionally "Capítulo pulido por el modelo".
- **Done:** a titled chapter with only story prose and dialogue: no ids,
  no JSON, no out-of-character lines, no dice lines, no undone turns,
  Spanish dialogue punctuation (raya) untouched; the polished version,
  if chosen, is prose too and never shorter than the story it replaces.

## UC4 - The app narrates on its own with a 27B model on llama.cpp

- **Who:** the player, without Faustus open, the model already loaded by
  llama.cpp on the same PC.
- **Goal:** press Narrar, read the proposed beat and the proposed
  changes, accept or untick them.
- **Start:** Backends pointing at the llama.cpp server (or found on
  8080-8090); the Velamar world.
- **Steps:** Jugar -> write an action -> Narrar -> read "Cambios
  propuestos" -> Aceptar / untick / Rechazar, six times. The model's
  replies are what a 27B model really produces: a `<think>` block, prose
  around the JSON, typographic quotes, trailing commas and comments, a
  reply cut at the token limit, the delta nested under a `"delta"` key,
  and a reply with no JSON at all.
- **Done:** the story text never contains JSON or reasoning; whatever
  part of the delta can be recovered is proposed item by item; what
  cannot is said plainly, and nothing unreviewed changes the world.

## UC5 - Continuity questions while writing outside the game

- **Who:** the player drafting a chapter in their manuscript tool, asking
  Faustus in Spanish.
- **Goal:** answer continuity questions without opening the app.
- **Prompts:** "Faustus, ¿quién ha muerto en Velamar?", "¿dónde vimos a
  Nuño por última vez?", "¿qué sabe Iria?", "¿puede el comisario Riera
  saber lo de la llave?", "¿es coherente que Mateo abra la puerta de la
  taberna?"
- **Tools expected:** `world_search`, `entity_get`, `world_check`,
  `world_context(focus=...)`, chosen from their descriptions by a model
  whose tool index only sees the first line of each description.
- **Done:** each question is answered from tool results in one or two
  calls, with the ids to cite, and Faustus picks the right tool for a
  Spanish request.

## UC6 - Illustrate the scene with Prospero's Hoard (combined)

- **Who:** the player, who wants a mood image for the chapter heading.
- **Goal:** one image of the current scene without describing it again.
- **Steps:** in Jugar, "Ilustrar escena" (visible only when Prospero's
  Hoard answers on 127.0.0.1:8815); or "Faustus, ilustra la escena
  actual de Velamar": `world_context` -> Prospero's image tool with the
  location, cast and mood from the brief.
- **Done:** an image of the Hospicio at night with the black lantern,
  and the story tools never returned an image to a text-only model.

## UC7 - A world from notes, by an agent

- **Who:** the player, who has a page of character and place notes.
- **Goal:** "Faustus, crea el mundo Velamar a partir de estas notas":
  entities with summaries, stats, secrets, nicknames (aliases), the
  relations between them, the opening threads and the clock.
- **Steps:** `story_world_create` -> `entity_upsert` x34 (with aliases
  such as "la Ciega") -> relations and threads -> the clock -> check the
  result with `world_search` and `entity_get`; then a backup with
  `session_export(format="json")` and an import through Mundos ->
  "Importar mundo (JSON)".
- **Done:** every note is in the world, nicknames resolve, nothing needed
  a person to click, and the backup re-imports.

## UC8 - The next evening: review and fix by hand

- **Who:** the player before the next session.
- **Goal:** fix what the model got wrong and see the shape of the story.
- **Steps:** Biblia -> find "farol", open Mateo Lür, correct a summary,
  mark someone missing; Mapa de relaciones with 34 entities; Cronología;
  Hilos y relojes (advance a thread, tick the clock); Registro de dados;
  Actividad del asistente (what did the model do last night?); undo the
  last turn with the two-step button; everything by keyboard as well;
  at 1280x800 and 1920x1080, light and dark, in Spanish and English.
- **Done:** every fix is possible without a model; the map is readable;
  the activity list says what the model did and when.
