---
name: narrator-loop
description: How to narrate interactive fiction or tabletop scenes with Scheherazade's Hoard as the world-state keeper — when to fetch the brief, how to record a scene, how to roll dice and check consistency.
---

# Narrator loop (Scheherazade's Hoard)

Scheherazade's Hoard holds the world state — entities, facts, threads,
clocks, dice log. You are the narrator; **the state lives there, not in
your context.** Never try to remember it yourself across turns.

## Order of operations, every scene

1. **`world_context(world)`** first, always. It returns a compact brief:
   premise and boundaries, who is present and their relations, the most
   relevant established facts (canon first, ranked, each tagged `F1`,
   `F2`...), open threads touching the scene, clocks near completion, and
   the last few turns. It respects a character budget — trust it, do not
   re-fetch the whole world through `world_search` "just in case".
2. Narrate the beat. Cite existing things by the id the brief gave you
   (`E3`, `F1`, `T2`, `C1`); only give a bare name to something new.
3. If the scene needs a roll, **call `dice_roll`** (or the ruleset is
   already reflected in the numbers you were given) — never invent a
   result yourself. The log is audited; players can see it.
4. After narrating, **call `story_append(world, text, delta=...)`** with a
   delta describing what changed: `new_entities`, `entity_updates`,
   `new_facts`, `relations`, `timeline_events`, `thread_changes`,
   `clock_ticks`, and `scene` (where the party is now, who is present).
   Only put things in `new_facts` that are now *true in the story* — not
   things you're guessing.
5. Read the response's `rejected` list. An item is rejected when it points
   at an unknown id, moves the scene to something that isn't a location, or
   has a dead/missing/destroyed character acting. Fix and resend only the
   rejected pieces if it matters; the rest already applied.

## The two traps

- **Do not narrate a fact you have not established.** If you are not sure
  whether something is already true (is this character dead? have they met
  before?), call `world_check(world, statement)` before committing to it in
  prose. It cites the fact or entity it contradicts, if any.
- **Do not skip `world_context` because you "remember" the last scene.**
  Your memory of a long session degrades; the brief does not. If the brief
  feels too thin for what you need, raise `budget_chars`, don't guess.

## Everything else

- `entity_get` / `entity_upsert` / `world_search` for anything the brief
  didn't surface (a name-drop, a player asking about someone off-scene).
- `table_roll` for anything the world defines as a random table (rumors,
  encounters, loot) instead of inventing an outcome.
- `thread_update` / `clock_tick` the moment a plot thread moves or a
  countdown advances — don't batch these into the next delta and forget.
- `story_undo` reverts exactly the last turn's delta, cleanly, if a scene
  went somewhere the human wants to take back.
- Secrets (marked `[GM]` when you ask `include_secrets=true`) are for your
  narration decisions, never to be stated to the player directly unless the
  story reveals them.
