# hoard.world/1

A small, neutral JSON format for moving a story world between apps of the Hoard
family: the cast, the places, the factions, how they relate and what happened
when. Scheherazade's Hoard writes it (`world_export`) and reads it
(`world_import`); Writer Desktop reads and writes it too (`wh_world_to_scheherazade`,
`wh_world_from_scheherazade`, see its `docs/AI-BRIDGE.md`). The format carries no
secrets and no pictures, and it never asks the receiver to delete anything.

## Document

```json
{
  "schema": "hoard.world/1",
  "source": {
    "app": "scheherazade",
    "ref": "hoard://scheherazade/world/w_9315dc3fa931",
    "revision": "sha256:…",
    "exported_at": 1790912972.37
  },
  "world": {"name": "Archipiélago", "genre": "fantasía", "tone": "melancólico", "premise": "Un reino hundido", "language": "es"},
  "characters": [ Entity… ],
  "places":     [ Entity… ],
  "factions":   [ Entity… ],
  "things":     [ Entity… ],
  "relations":  [ Relation… ],
  "events":     [ Event… ]
}
```

Every list is optional and may be empty. `source` and `world` are optional on import
(without `source.ref` the document is not remembered, so importing it again with no
target world makes another world). At most 5000 records per document.

### Entity

```json
{
  "ref": "hoard://scheherazade/entity/e_6bc175db451c",
  "revision": "sha256:…",
  "same_as": ["hoard://writer/codex/char_1"],
  "name": "Ana",
  "aliases": ["la capitana"],
  "summary": "Capitana del faro",
  "description": "Alta y seria.",
  "status": "alive",
  "tags": ["marina"],
  "fields": {"edad": "34", "rango": "capitana"},
  "parent_ref": "hoard://scheherazade/entity/e_…"
}
```

- `characters`, `places` and `factions` are what the section says. `things` holds
  everything else and each one names its `kind`: `item`, `lore` or `creature`
  (Writer's `concept`, `magic` and `custom` arrive as `lore`).
- `status` is `alive`, `dead`, `missing`, `destroyed`, `active` or `unknown`; anything
  else is read as `unknown`.
- `fields` is a flat map of text to text (a number, a flag or a nested object is
  written as text). `parent_ref` (for a place inside a place, say) is optional.
- Never present: GM secrets, images, facts, threads, clocks, sessions, dice.

### Relation

```json
{"ref": "hoard://scheherazade/relation/r_…", "revision": "sha256:…",
 "from": "<entity ref>", "to": "<entity ref>", "type": "mentor", "note": "le enseñó a navegar", "since": "año 3"}
```

`from` and `to` are the `ref` (or a `same_as`) of two entities of the document.
`type` is free text ("ally", "member of"); `since` is free text.

### Event

```json
{"ref": "hoard://scheherazade/event/t_…", "revision": "sha256:…",
 "date": "Año 1", "summary": "Se enciende el faro", "entities": ["<entity ref>", "…"]}
```

`date` is the in-world date as free text (it may be empty). The list order is the
timeline order.

## Refs, revisions and `same_as`

- `ref` identifies a record in the app that wrote it: `hoard://<app>/<kind>/<id>`.
  It never changes for that record.
- `revision` is `sha256:` plus the hash of the record's content (every field except
  `ref`, `revision` and `same_as`, keys sorted, UTF-8). A receiver treats it as an opaque
  string: equal means "nothing changed at the source".
- `same_as` lists refs the same record has in other apps (a character Scheherazade
  took from Writer carries the Writer ref), so a record that travels A → B → A is
  recognised and not duplicated. The writer of the document may leave it out.

## What a receiver does

Import is idempotent and never destructive:

| State | When |
| --- | --- |
| `created` | The ref (and its `same_as`) is new and the name is free: the record is created and remembered with its `ref` and `revision`. |
| `unchanged` | Imported before with the same `revision`. |
| `updated` | The source's `revision` changed and the record has not been edited since it was imported: it takes the new content. |
| `local_modified` | The source changed but the record was edited after the import: left alone and reported. |
| `linked_existing` | A record of the same name and kind already existed and was not imported: it is linked to the ref, not duplicated and not changed; a later revision of the source will not overwrite it either. |
| `name_collision` | The name exists as another kind: nothing is written. |
| `own` | The ref names a record of the receiving world itself (a document coming back): nothing to do. |
| `skipped` | Unusable record (`bad_ref`, `no_name`, `no_summary`, `invalid`, `endpoint_missing`) or one the person deleted (`deleted_locally`, which is never brought back). |

Nothing is ever deleted, and a document that lacks a record does not remove it. A
relation or event whose entity is not in the document or the world is skipped.
Revisions of relations and events follow the same rule as entities.

## Where it lives

- Scheherazade: `scheherazades_hoard/exchange.py` (export, import, hashes), the
  `family_links` table (ref, revision and a hash of the local row at import time),
  `world_export {world_id}` and `world_import {data, world_id?}` on `/api/agent/*` and over MCP.
- Writer: `src/services/familyBridge/` and `src/services/aiBridge/tools/family.ts`.
