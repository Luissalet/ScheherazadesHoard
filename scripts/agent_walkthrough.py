#!/usr/bin/env python3
"""Walk the agent use cases over real MCP stdio, the way a local model would.

Usage:
    python scripts/agent_walkthrough.py [--url http://127.0.0.1:18860] [--out DIR]

It spawns `scheherazades_hoard/mcp_server.py` over stdio against an app
that is already running at --url (start it with `--data-dir` pointing at
a scratch folder, never at your real `data/`), then plays the agent use
cases of docs/USE_CASES.md as a sequence of tool calls:

  1. Tool discovery: list_tools, and what a client that only indexes the
     first 120 characters of each description's first line can find
     (Spanish and English intents).
  2. UC2 world building from notes: a 34-entity Spanish noir world.
  3. UC2 long solo session: 44 scripted turns in Spanish with rolls,
     deaths, moves, secrets learned, a dead character wrongly put back
     in the scene, a wrong role, an undo - with continuity checkpoints.
  4. UC5 continuity questions mid-writing: who is dead, where is
     everyone, who knows what.
  5. UC3 clean chapter export, paged, and a check of what a manuscript
     would not want (ids, fences, OOC lines, dice lines).

The narrator is scripted (no model runs here): each turn is what a 27B
model would send after reading the brief. Every call prints the tool,
its argument summary, the size of its result and the time taken; every
continuity expectation prints PASS/FAIL; the transcript is saved to
--out. Exit code 0 even when checks fail: this is a walkthrough that
reports, not a test suite.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER = REPO_ROOT / "scheherazades_hoard" / "mcp_server.py"
WORLD = "Velamar"
INDEX_CHARS = 120  # what a tool index that keeps line one, clipped, sees


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


class Walk:
    def __init__(self, session: ClientSession, out: Path):
        self.s = session
        self.out = out
        self.log: list[dict] = []
        self.checks: list[tuple[str, bool, str]] = []
        self.refs: dict[str, str] = {}
        self.total_result_chars = 0
        self.calls = 0

    async def call(self, tool: str, quiet: bool = False, **args: Any) -> tuple[Optional[Any], Optional[str]]:
        """Call a tool; return (parsed result, error text)."""
        t0 = time.perf_counter()
        res = await self.s.call_tool(tool, args)
        ms = (time.perf_counter() - t0) * 1000
        texts = [c.text for c in res.content if getattr(c, "type", "") == "text"]
        images = [c for c in res.content if getattr(c, "type", "") == "image"]
        text = "".join(texts)
        self.calls += 1
        self.total_result_chars += len(text)
        summary = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
        status = "ERROR" if res.isError else "ok"
        if not quiet or res.isError:
            print(f"  -> {tool}({summary})  <- {status} {len(text)} chars, {ms:.0f} ms"
                  + (f", {len(images)} IMAGE(S)" if images else ""))
        if images:
            self.check(f"{tool} returns no image by default", False, f"{len(images)} image blocks")
        self.log.append({"tool": tool, "args": args, "ok": not res.isError, "chars": len(text),
                         "ms": round(ms), "images": len(images), "result": text[:4000]})
        if res.isError:
            print(f"     error: {text[:300]}")
            return None, text
        try:
            return json.loads(text), None
        except ValueError:
            return text, None

    def check(self, what: str, ok: bool, detail: str = "") -> None:
        self.checks.append((what, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {what}" + (f"  ({detail})" if detail else ""))

    def r(self, name: str) -> str:
        return self.refs.get(name, name)


def _short(v: Any) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else repr(v)
    return s if len(s) <= 60 else s[:57] + "..."


# ---------------------------------------------------------------------------
# 1. Tool discovery
# ---------------------------------------------------------------------------

# (intent a person types to Faustus, tool that should be picked)
INTENTS = [
    ("tirar dados", "dice_roll"), ("tirada de 2d6", "dice_roll"), ("roll dice", "dice_roll"),
    ("qué mundos hay", "story_worlds"), ("crear mundo nuevo", "story_world_create"),
    ("contexto de la escena", "world_context"), ("qué está pasando", "world_context"),
    ("buscar personaje", "world_search"), ("dónde está Nuño", "world_search"),
    ("ficha de personaje", "entity_get"), ("crear personaje", "entity_upsert"),
    ("registrar turno", "story_append"), ("guardar escena", "story_append"),
    ("tabla aleatoria", "table_roll"), ("resolver trama", "thread_update"),
    ("avanzar reloj", "clock_tick"), ("comprobar continuidad", "world_check"),
    ("es coherente", "world_check"), ("exportar capítulo", "session_export"),
    ("deshacer último turno", "story_undo"), ("undo", "story_undo"),
]


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_]+", fold(s)) if len(w) > 2}


def pick(index: dict[str, str], intent: str) -> Optional[str]:
    """Lexical pick, as a small retrieval index would: most shared words wins."""
    iw = _words(intent)
    scored = sorted(((len(iw & _words(name.replace("_", " ") + " " + text)), name) for name, text in index.items()), reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else None


async def discovery(w: Walk) -> list:
    print("\n== 1. Tool discovery ==")
    tools = (await w.s.list_tools()).tools
    print(f"  {len(tools)} tools")
    first_line_index, full_index = {}, {}
    for t in tools:
        desc = t.description or ""
        line1 = desc.strip().splitlines()[0] if desc.strip() else ""
        first_line_index[t.name] = line1[:INDEX_CHARS]
        full_index[t.name] = desc
        has_es = bool(re.search(r"[áéíóúñ¿]|\b(tirar|crear|buscar|registrar|deshacer|exportar|comprobar|actualizar|resolver|avanzar)\b", fold(line1) + line1))
        print(f"  {t.name:20s} line1={len(line1):3d} chars  es_trigger={'yes' if has_es else 'no '}  {line1[:70]!r}")
        w.check(f"{t.name}: first line <= 110 chars", len(line1) <= 110, f"{len(line1)}")
        w.check(f"{t.name}: first line has a Spanish trigger word", has_es)
        schema_chars = len(json.dumps(t.inputSchema))
        if schema_chars > 1500:
            print(f"     note: input schema is {schema_chars} chars")
    hits_line1 = sum(pick(first_line_index, i) == want for i, want in INTENTS)
    hits_full = sum(pick(full_index, i) == want for i, want in INTENTS)
    for intent, want in INTENTS:
        got = pick(first_line_index, intent)
        if got != want:
            print(f"     line-1 index misses {intent!r}: picked {got}, wanted {want}")
    w.check(f"line-1 index (first {INDEX_CHARS} chars) finds the right tool for all {len(INTENTS)} intents",
            hits_line1 == len(INTENTS), f"{hits_line1}/{len(INTENTS)}; full descriptions: {hits_full}/{len(INTENTS)}")
    return tools


# ---------------------------------------------------------------------------
# 2. World from notes (UC2 setup)
# ---------------------------------------------------------------------------

ENTITIES = [
    # kind, name, summary, fields, secrets
    ("character", "Iria Castro", "Periodista del Eco de Velamar que investiga los faroles apagados.", {"coraje": 1, "sagacidad": 2, "frialdad": 0}, ""),
    ("character", "Mateo Lür", "Farolero retirado, sesenta años, manos quemadas.", {"oficio": "farolero"}, "Vio al Farolero en 1911 y guardó la llave del faro."),
    ("character", "Rosalía Paz", "Tabernera del Ancla Rota; lo oye todo.", {}, ""),
    ("character", "Lucio Ferrán", "Relojero de la Torre; vive entre engranajes.", {}, "Detiene el reloj a propósito para marcar las apariciones."),
    ("character", "Nuño Vidal", "Contrabandista del muelle, cobarde y simpático.", {}, "Debe dinero a la Hermandad del Silencio."),
    ("character", "Comisario Anselmo Riera", "Jefe de la comisaría de la calle Real; no cree en fantasmas.", {}, "Cobra del Gremio de Faroleros por no investigar."),
    ("character", "Sor Benedicta", "Monja del Hospicio de San Telmo.", {}, "Es la voz de la Hermandad del Silencio."),
    ("character", "Tobías", "Niño de los recados del hospicio, nueve años.", {}, ""),
    ("character", "Marta la Ciega", "Vidente del cementerio; habla con los que no están.", {}, ""),
    ("character", "Doña Elvira Montenegro", "Aristócrata arruinada, dueña del palacio.", {}, "Su familia encargó el farol negro."),
    ("character", "Álvaro Montenegro", "Hijo de Elvira, heredero nervioso.", {}, ""),
    ("character", "Clara Ibarra", "Médica forense; escéptica y precisa.", {}, ""),
    ("character", "Padre Esteban", "Párroco del acantilado.", {}, ""),
    ("character", "Gael Sarmiento", "Poeta que escribe sobre la Noche Larga.", {}, ""),
    ("location", "Velamar", "Ciudad portuaria de faroles de gas y niebla.", {}, ""),
    ("location", "Taberna El Ancla Rota", "Taberna del puerto, humo y redes colgadas.", {}, ""),
    ("location", "Callejón de los Faroles", "Callejón estrecho donde los faroles se apagan solos.", {}, ""),
    ("location", "Torre del Reloj", "Torre con un reloj que se para a las 3:17.", {}, ""),
    ("location", "Muelle de las Ánimas", "Muelle viejo de los contrabandistas.", {}, ""),
    ("location", "Faro Viejo", "Faro abandonado en la punta norte.", {}, ""),
    ("location", "Comisaría de la calle Real", "Comisaría fría con olor a tinta.", {}, ""),
    ("location", "Hospicio de San Telmo", "Hospicio de huérfanos con capilla.", {}, ""),
    ("location", "Cementerio del Acantilado", "Cementerio sobre el mar.", {}, ""),
    ("location", "Palacio Montenegro", "Palacio decadente de la calle Alta.", {}, ""),
    ("faction", "Gremio de Faroleros", "Los que encienden Velamar cada noche.", {}, ""),
    ("faction", "Hermandad del Silencio", "Sociedad que paga para que nadie hable de 1911.", {}, ""),
    ("faction", "Policía de Velamar", "Pocos agentes, mal pagados.", {}, ""),
    ("item", "Llave de hierro del faro", "Llave antigua del Faro Viejo.", {}, ""),
    ("item", "Diario de Mateo", "Cuaderno con las horas en que se apagan los faroles.", {"portador": "Mateo Lür"}, ""),
    ("item", "Farol negro", "Farol de aceite negro que no da luz.", {}, "Quien lo lleva es seguido por el Farolero."),
    ("lore", "La Noche Larga de 1911", "La noche en que todos los faroles se apagaron y desaparecieron doce personas.", {}, ""),
    ("lore", "Los faroles que se apagan solos", "Superstición: si un farol se apaga a tu paso, alguien te sigue.", {}, ""),
    ("creature", "El Farolero", "Figura alta con un farol negro; sigue a la gente de noche, siempre a la misma distancia.", {}, "Fue un farolero del Gremio en 1911."),
    ("character", "Inés Lür", "Hija de Mateo, costurera.", {}, ""),
]


async def build_world(w: Walk) -> None:
    print("\n== 2. World from notes ==")
    worlds, _ = await w.call("story_worlds")
    existing = [x for x in (worlds or {}).get("worlds", []) if x["name"] == WORLD]
    if existing:
        print(f"  world {WORLD!r} exists; delete data dir to rerun from scratch")
    else:
        await w.call("story_world_create", name=WORLD, genre="gótico urbano", tone="inquietante, lento, nocturno",
                     premise="En Velamar los faroles se apagan solos y alguien sigue a los que investigan.",
                     ruleset="pbta_2d6", language="es")
    t0 = time.perf_counter()
    for kind, name, summary, fields, secrets in ENTITIES:
        args: dict[str, Any] = {"world": WORLD, "kind": kind, "name": name, "summary": summary}
        if fields:
            args["fields"] = fields
        if secrets:
            args["secrets"] = secrets
        res, err = await w.call("entity_upsert", quiet=True, **args)
        if res:
            w.refs[name] = res["ref"]
    print(f"  {len(ENTITIES)} entity_upsert calls in {time.perf_counter() - t0:.1f} s; refs {min(w.refs.values())}..{max(w.refs.values(), key=lambda r: int(r[1:]))}")
    # Aliases: a writer's notes give nicknames ("la Ciega", "el Comisario").
    # entity_upsert has no aliases parameter over MCP; try it the way a model would.
    res, err = await w.call("entity_upsert", world=WORLD, kind="character", name="Marta la Ciega", aliases=["la Ciega"])
    got, err2 = await w.call("entity_get", world=WORLD, ref="la Ciega")
    w.check("entity_upsert keeps aliases sent over MCP (or refuses them)", got is not None or err is not None,
            "the call succeeded but the alias was silently dropped" if got is None and err is None else "")

    # Relations from notes: no relation tool; the only way is a delta.
    rel = lambda a, b, t: {"a": w.r(a), "b": w.r(b), "type": t}
    res, err = await w.call("story_append", world=WORLD, text="", role="system", delta={
        "relations": [
            rel("Inés Lür", "Mateo Lür", "hija de"), rel("Álvaro Montenegro", "Doña Elvira Montenegro", "hijo de"),
            rel("Sor Benedicta", "Tobías", "cuida de"), rel("Comisario Anselmo Riera", "Gremio de Faroleros", "cobra de"),
            rel("Nuño Vidal", "Hermandad del Silencio", "debe dinero a"), rel("Mateo Lür", "Gremio de Faroleros", "miembro de"),
            rel("Rosalía Paz", "Mateo Lür", "amiga de"),
        ],
        "thread_changes": [{"create": True, "title": "¿Quién apaga los faroles?"},
                           {"create": True, "title": "¿Dónde está Mateo Lür?"}],
    })
    if res:
        w.check("setup relations and threads applied", not res["rejected"], json.dumps(res["rejected"], ensure_ascii=False)[:200])


# ---------------------------------------------------------------------------
# 3. The long solo session (UC2)
# ---------------------------------------------------------------------------

def turns(w: Walk) -> list[dict]:
    """44 beats. Each item: role, text, optional delta, optional roll=(expr, reason),
    optional check=callable name, optional expect_reject."""
    r = w.r
    return [
        {"role": "narration", "text": "La niebla sube del puerto y se mete en el Ancla Rota como un cliente más. Iria Castro pide un café con coñac y abre su libreta.",
         "delta": {"scene": {"location": r("Taberna El Ancla Rota"), "present": [r("Iria Castro"), r("Rosalía Paz")], "mood": "inquieto"}}},
        {"role": "dialogue", "text": "Mateo Lür no ha vuelto desde el martes —dice Rosalía, secando el mismo vaso por tercera vez—. Y su farol lleva tres noches apagado."},
        {"role": "action", "text": "Iria le pregunta a Rosalía qué sabe de las rondas de Mateo."},
        {"role": "roll", "text": "Iria tira para leer a Rosalía", "roll": ("2d6+2", "leer a una persona (sagacidad)")},
        {"role": "narration", "text": "Rosalía mira a la puerta antes de sacar de debajo de la barra un cuaderno de tapas de hule. «Me pidió que te lo diera si no volvía».",
         "delta": {"entity_updates": [{"ref": r("Diario de Mateo"), "fields": {"portador": "Iria Castro"}}],
                   "new_facts": [{"text": "Rosalía entregó a Iria el Diario de Mateo en el Ancla Rota.", "entity_ids": [r("Iria Castro"), r("Rosalía Paz"), r("Diario de Mateo")], "canon": True},
                                 {"text": "Iria sabe que Mateo anotaba la hora exacta en que se apagaba cada farol.", "entity_ids": [r("Iria Castro"), r("Diario de Mateo")]}]}},
        {"role": "narration", "text": "Al salir, Iria toma el atajo del Callejón de los Faroles. El primer farol se apaga cuando pasa a su lado. Luego el segundo.",
         "delta": {"scene": {"location": r("Callejón de los Faroles"), "present": [r("Iria Castro")], "mood": "acechante"},
                   "clock_ticks": [{"ref": "C1", "ticks": 1}]}},
        {"role": "narration", "text": "Pasos detrás de ella, siempre a la misma distancia. Cuando se detiene, se detienen."},
        {"role": "roll", "text": "Iria intenta no correr", "roll": ("2d6", "mantener la calma (frialdad)")},
        {"role": "narration", "text": "Al fondo del callejón hay una figura alta con un farol que no da luz. No se mueve. Iria sí.",
         "delta": {"scene": {"present": [r("Iria Castro"), r("El Farolero")], "mood": "terror"}, "clock_ticks": [{"ref": "C1", "ticks": 1}]}},
        {"role": "action", "text": "Iria echa a correr hacia la Torre del Reloj, donde siempre hay luz."},
        {"role": "narration", "text": "Lucio Ferrán le abre la portezuela sin preguntar. Arriba, los engranajes suenan como dientes.",
         "delta": {"scene": {"location": r("Torre del Reloj"), "present": [r("Iria Castro"), r("Lucio Ferrán")], "mood": "respiro"}}},
        {"role": "dialogue", "text": "Las campanas se paran cuando él pasa —dice Lucio—. Siempre a las tres y diecisiete."},
        {"role": "narration", "text": "El reloj marca las 3:17. Se para.",
         "delta": {"new_facts": [{"text": "El reloj de la Torre se para a las 3:17 cada vez que un farol se apaga solo.", "entity_ids": [r("Torre del Reloj"), r("Lucio Ferrán")], "canon": True}]}},
        {"role": "narration", "text": "Lucio confiesa que Mateo subió hace tres noches con una llave de hierro y le pidió que la escondiera. Él no quiso.",
         "delta": {"new_facts": [{"text": "Lucio sabe que Mateo tenía la Llave de hierro del faro hace tres noches.", "entity_ids": [r("Lucio Ferrán"), r("Mateo Lür"), r("Llave de hierro del faro")]},
                                 {"text": "Iria sabe, por Lucio, que Mateo llevaba la llave del faro.", "entity_ids": [r("Iria Castro"), r("Llave de hierro del faro")]}]}},
        {"role": "narration", "text": "Antes del alba Iria baja al Muelle de las Ánimas a buscar a Nuño Vidal, que conoce cada barca y cada deuda.",
         "delta": {"scene": {"location": r("Muelle de las Ánimas"), "present": [r("Iria Castro"), r("Nuño Vidal")], "mood": "desconfiado"}}},
        {"role": "roll", "text": "Iria presiona a Nuño", "roll": ("2d6+1", "presionar (coraje)")},
        {"role": "dialogue", "text": "Lo vi subir al Faro Viejo el martes —admite Nuño—. No bajó. Yo no subo ahí ni por todo el ron de Velamar."},
        {"role": "narration", "text": "Nuño la acompaña, a regañadientes, hasta el Faro Viejo. La puerta está abierta.",
         "delta": {"scene": {"location": r("Faro Viejo"), "present": [r("Iria Castro"), r("Nuño Vidal")], "mood": "aterrador"}}},
        {"role": "narration", "text": "Al pie de la escalera de caracol está Mateo Lür, con el cuello en un ángulo imposible y la mano cerrada sobre nada. La llave no está.",
         "delta": {"entity_updates": [{"ref": r("Mateo Lür"), "status": "muerto"}],
                   "new_facts": [{"text": "Mateo Lür murió al pie de la escalera del Faro Viejo; la llave del faro no estaba con él.", "entity_ids": [r("Mateo Lür"), r("Faro Viejo")], "canon": True}],
                   "timeline_events": [{"summary": "Iria y Nuño encuentran muerto a Mateo Lür", "in_world_date": "Noche del 3 de noviembre", "entity_ids": [r("Mateo Lür"), r("Iria Castro")]}],
                   "thread_changes": [{"ref": "T2", "status": "resolved", "note": "Muerto en el Faro Viejo."}]},
         "checkpoint": "after_death"},
        {"role": "narration", "text": "Arriba, en la linterna del faro, algo sostiene un farol negro. Nuño grita y huye por el espigón. Iria se queda sola.",
         "delta": {"scene": {"present": [r("Iria Castro")], "mood": "soledad"}}},
        {"role": "roll", "text": "Iria huye del faro", "roll": ("2d6+1", "escapar (coraje)")},
        {"role": "narration", "text": "Ya de día, Iria entra en la Comisaría de la calle Real con la ropa húmeda y el diario bajo el brazo.",
         "delta": {"scene": {"location": r("Comisaría de la calle Real"), "present": [r("Iria Castro"), r("Comisario Anselmo Riera")], "mood": "frío"}}},
        {"role": "dialogue", "text": "Un viejo borracho que se cae por una escalera no es un caso, señorita Castro —dice el comisario Riera sin levantar la vista.",
         "delta": {"relations": [{"a": r("Comisario Anselmo Riera"), "b": r("Iria Castro"), "type": "desconfía de"}]}},
        {"role": "ooc", "text": "Pausa para cenar; seguimos en diez minutos."},
        {"role": "narration", "text": "Por la tarde, Iria visita el Hospicio de San Telmo. Sor Benedicta la recibe en la capilla; Tobías barre sin quitarle ojo.",
         "delta": {"scene": {"location": r("Hospicio de San Telmo"), "present": [r("Iria Castro"), r("Sor Benedicta"), r("Tobías")], "mood": "tenso"}}},
        {"role": "dialogue", "text": "Hay cosas en esta ciudad que es mejor dejar dormir, hija —dice Sor Benedicta, y cierra el misal con demasiada fuerza."},
        {"role": "dialogue", "text": "Anoche el hombre del farol me preguntó por usted —susurra Tobías—. Sabía su nombre.",
         "delta": {"new_facts": [{"text": "El Farolero preguntó a Tobías por Iria y sabía su nombre.", "entity_ids": [r("Tobías"), r("El Farolero"), r("Iria Castro")]}],
                   "clock_ticks": [{"ref": "C1", "ticks": 1}]}},
        {"role": "narration", "text": "Al anochecer, Iria sube al Cementerio del Acantilado. Marta la Ciega está sentada sobre una lápida, de cara al mar.",
         "delta": {"scene": {"location": r("Cementerio del Acantilado"), "present": [r("Iria Castro"), r("Marta la Ciega")], "mood": "espectral"}}},
        {"role": "dialogue", "text": "Te sigue desde que leíste el diario —dice Marta—. Mateo también lo leía en voz alta. Mira cómo acabó."},
        # The model forgets Mateo is dead and puts him in the scene: must be rejected.
        {"role": "narration", "text": "Una silueta conocida se acerca entre las tumbas: Mateo Lür, con su farol de siempre.",
         "delta": {"scene": {"present": [r("Iria Castro"), r("Marta la Ciega"), r("Mateo Lür")]}},
         "expect_reject": "scene"},
        # A 27B model sends a role in Spanish once.
        {"role": "narrador", "text": "Iria parpadea y la silueta ya no está.", "expect_error": True},
        {"role": "narration", "text": "Iria parpadea y la silueta ya no está. Solo queda Marta, sonriendo a nadie."},
        {"role": "narration", "text": "Esa noche, Iria llama a la puerta del Palacio Montenegro. Doña Elvira la recibe con un chal y Álvaro detrás, pálido.",
         "delta": {"scene": {"location": r("Palacio Montenegro"), "present": [r("Iria Castro"), r("Doña Elvira Montenegro"), r("Álvaro Montenegro")], "mood": "decadente"}}},
        {"role": "dialogue", "text": "No pronuncie ese nombre en mi casa —dice Doña Elvira cuando Iria menciona al Farolero.",
         "delta": {"relations": [{"a": r("Doña Elvira Montenegro"), "b": r("El Farolero"), "type": "teme a"}]}},
        {"role": "roll", "text": "Iria insiste con Álvaro", "roll": ("2d6+2", "leer a una persona (sagacidad)")},
        {"role": "narration", "text": "Álvaro, a solas en el pasillo, confiesa que el Gremio paga a la Hermandad del Silencio desde 1911 para que nadie hable de la Noche Larga.",
         "delta": {"new_facts": [{"text": "El Gremio de Faroleros paga a la Hermandad del Silencio desde 1911.", "entity_ids": [r("Gremio de Faroleros"), r("Hermandad del Silencio")]},
                                 {"text": "Iria sabe, por Álvaro, que el Gremio paga a la Hermandad.", "entity_ids": [r("Iria Castro"), r("Álvaro Montenegro")]}],
                   "thread_changes": [{"create": True, "title": "La deuda del Gremio"}]}},
        {"role": "narration", "text": "Todas las lámparas del palacio se apagan a la vez. Cuando vuelven a encenderlas, Álvaro no está.",
         "delta": {"entity_updates": [{"ref": r("Álvaro Montenegro"), "status": "desaparecido"}],
                   "scene": {"present": [r("Iria Castro"), r("Doña Elvira Montenegro")], "mood": "pánico"}},
         "checkpoint": "after_missing"},
        {"role": "narration", "text": "Iria sale a la calle. El Callejón de los Faroles está a oscuras entero y, al fondo, él la espera.",
         "delta": {"scene": {"location": r("Callejón de los Faroles"), "present": [r("Iria Castro"), r("El Farolero")], "mood": "terror"}}},
        {"role": "roll", "text": "Iria le sostiene la mirada", "roll": ("2d6", "mantener la calma (frialdad)")},
        {"role": "narration", "text": "El Farolero se inclina y le susurra su nombre completo, el de su madre, el de la calle donde nació.",
         "delta": {"clock_ticks": [{"ref": "C1", "ticks": 1}]}},
        # A bad turn the writer wants taken back.
        {"role": "narration", "text": "Iria cae al suelo y no vuelve a levantarse.",
         "delta": {"entity_updates": [{"ref": r("Iria Castro"), "status": "dead"}]}, "undo": True},
        {"role": "narration", "text": "Iria despierta en una cama del Hospicio de San Telmo. Clara Ibarra le toma el pulso; Sor Benedicta reza en la puerta.",
         "delta": {"scene": {"location": r("Hospicio de San Telmo"), "present": [r("Iria Castro"), r("Clara Ibarra"), r("Sor Benedicta")], "mood": "desconcierto"}}},
        {"role": "dialogue", "text": "Nadie te trajo —dice Clara—. Llegaste sola, a las tres y diecisiete, con ese farol negro en la mano.",
         "delta": {"entity_updates": [{"ref": r("Farol negro"), "fields": {"portador": "Iria Castro"}}],
                   "new_facts": [{"text": "Iria llegó sola al Hospicio a las 3:17 con el Farol negro en la mano.", "entity_ids": [r("Iria Castro"), r("Farol negro"), r("Hospicio de San Telmo")], "canon": True}]}},
        {"role": "narration", "text": "El farol está en la mesilla. No da luz, pero la habitación se enfría a su alrededor.",
         "delta": {"thread_changes": [{"ref": "T1", "status": "advanced", "note": "Iria tiene el farol negro."}]}},
        {"role": "narration", "text": "Fuera, en la calle, un farol se apaga. Luego otro. Iria cuenta los pasos que se acercan y abre el diario por la última página.",
         "checkpoint": "end"},
    ]


async def ensure_clock(w: Walk, url: str) -> None:
    """No MCP tool creates a clock; a writer would add it on the Threads & clocks page."""
    import httpx
    with httpx.Client(trust_env=False, timeout=10) as c:
        worlds = c.get(f"{url}/api/worlds").json()
        wid = next(x["id"] for x in worlds if x["name"] == WORLD)
        if not c.get(f"{url}/api/worlds/{wid}/clocks").json():
            c.post(f"{url}/api/worlds/{wid}/clocks", json={"name": "La Noche Larga vuelve", "segments": 6,
                                                            "on_full": "Todos los faroles de Velamar se apagan."},
                   headers={"X-Hoard-Client": "ui"})
            print("  (clock C1 created through the UI route: there is no MCP tool for it)")


async def session(w: Walk) -> None:
    print("\n== 3. Long solo session (44 beats) ==")
    ctx_sizes = []
    for i, beat in enumerate(turns(w), 1):
        print(f" beat {i:2d} [{beat['role']}] {beat['text'][:70]}")
        if beat["role"] in ("narration", "dialogue") and i % 4 == 1:
            ctx, _ = await w.call("world_context", world=WORLD)
            if ctx:
                ctx_sizes.append((len(json.dumps(ctx, ensure_ascii=False)), len(ctx.get("brief", ""))))
        rolls = None
        if "roll" in beat:
            expr, reason = beat["roll"]
            res, _ = await w.call("dice_roll", expression=expr, reason=reason, world=WORLD)
            if res:
                rolls = [{"expression": res["expression"], "total": res["total"], "band": res.get("band")}]
                w.check(f"beat {i}: pbta roll has a band", "band" in res, str(res.get("band")))
                if res.get("band") == "miss":
                    beat.setdefault("delta", {}).setdefault("clock_ticks", []).append({"ref": "C1", "ticks": 1})
        args: dict[str, Any] = {"world": WORLD, "text": beat["text"], "role": beat["role"]}
        if beat.get("delta"):
            args["delta"] = beat["delta"]
        if rolls:
            # story_append over MCP has no `rolls` argument: the roll is only in the text.
            args["text"] = f"{beat['text']} ({rolls[0]['expression']} = {rolls[0]['total']}, {rolls[0]['band']})"
        res, err = await w.call("story_append", **args)
        if beat.get("expect_error"):
            w.check(f"beat {i}: wrong role refused with an actionable message", err is not None and "one of" in (err or ""), (err or "")[:120])
            continue
        if res and res["rejected"] and not beat.get("expect_reject"):
            w.check(f"beat {i}: nothing rejected", False, json.dumps(res["rejected"], ensure_ascii=False)[:200])
        if beat.get("expect_reject"):
            cats = [x["category"] for x in (res or {}).get("rejected", [])]
            w.check(f"beat {i}: dead Mateo refused in the scene", any(c.startswith(beat["expect_reject"]) for c in cats),
                    json.dumps((res or {}).get("rejected"), ensure_ascii=False)[:200])
            present = [p["name"] for p in (res or {}).get("scene", {}).get("present", [])]
            w.check(f"beat {i}: the rest of the scene still applies (Marta stays)", "Marta la Ciega" in present, str(present))
        if beat.get("undo"):
            u, err = await w.call("story_undo", world=WORLD)
            e, _ = await w.call("entity_get", world=WORLD, ref=w.r("Iria Castro"))
            w.check(f"beat {i}: undo brings Iria back to alive", (e or {}).get("status") == "alive", str((e or {}).get("status")))
        if beat.get("checkpoint"):
            await checkpoint(w, beat["checkpoint"])
    if ctx_sizes:
        biggest = max(ctx_sizes)
        print(f"  world_context: result {min(ctx_sizes)[0]}..{biggest[0]} chars, brief up to {max(b for _, b in ctx_sizes)} (budget 3000)")
        w.check("world_context result stays near its budget (<= 1.3x 3000 chars)", biggest[0] <= 3900,
                f"{biggest[0]} chars: the brief plus the same content again as scene/lore/threads/recent_turns")


async def checkpoint(w: Walk, name: str) -> None:
    print(f"  -- checkpoint {name}")
    if name == "after_death":
        res, _ = await w.call("world_check", world=WORLD, statement="Mateo Lür abre la puerta de la taberna y pide un vino.")
        w.check("world_check: dead Mateo acting is a conflict", res is not None and not res["consistent"],
                json.dumps((res or {}).get("conflicts"), ensure_ascii=False)[:160])
        res, _ = await w.call("world_check", world=WORLD, statement="Mateo abre la puerta de la taberna.")
        w.check("world_check: dead 'Mateo' (first name only) is a conflict", res is not None and not res["consistent"])
    if name == "after_missing":
        res, _ = await w.call("world_check", world=WORLD, statement="Nuño Vidal bebe tranquilo en la Taberna El Ancla Rota.")
        w.check("world_check: Nuño elsewhere than last seen (Faro Viejo) is flagged", res is not None and not res["consistent"],
                json.dumps((res or {}).get("conflicts"), ensure_ascii=False)[:160])
        e, _ = await w.call("entity_get", world=WORLD, ref="Álvaro Montenegro")
        w.check("Álvaro is missing ('desaparecido' accepted)", (e or {}).get("status") == "missing", str((e or {}).get("status")))
    if name == "end":
        ctx, _ = await w.call("world_context", world=WORLD)
        scene = (ctx or {}).get("scene", {})
        present = [p["name"] for p in scene.get("present", [])]
        w.check("scene at the end is the Hospicio", (scene.get("location") or {}).get("name") == "Hospicio de San Telmo", str(scene.get("location")))
        w.check("present: Iria, Clara, Sor Benedicta", sorted(present) == sorted(["Iria Castro", "Clara Ibarra", "Sor Benedicta"]), str(present))
        brief = (ctx or {}).get("brief", "")
        w.check("brief never mentions Mateo as present", "Mateo" not in brief.split("PRESENT:")[-1].split("MOOD:")[0])
        w.check("brief includes the canon fact about the black lantern", "Farol negro" in brief or "farol negro" in brief.lower())
        print("  brief (first 900 chars):\n    " + brief[:900].replace("\n", "\n    "))


# ---------------------------------------------------------------------------
# 4. Continuity questions (UC5)
# ---------------------------------------------------------------------------

async def questions(w: Walk) -> None:
    print("\n== 4. Continuity questions ==")
    # "¿Quién ha muerto?" - no status filter in world_search; a model searches words.
    res, _ = await w.call("world_search", world=WORLD, query="muerto")
    names = [e["name"] for e in (res or {}).get("entities", [])]
    w.check("'¿quién ha muerto?' finds Mateo via world_search", "Mateo Lür" in names or any("Mateo" in f["text"] for f in (res or {}).get("facts", [])),
            f"entities={names}")
    res, _ = await w.call("world_search", world=WORLD, query="dead")
    w.check("world_search 'dead' finds entities by status", any(e["status"] == "dead" for e in (res or {}).get("entities", [])),
            str([e["name"] for e in (res or {}).get("entities", [])]))
    # "¿Dónde está Nuño?" - last seen location. A model uses the first name.
    e, err = await w.call("entity_get", world=WORLD, ref="Nuño")
    w.check("entity_get accepts a first name (or the error names the match)", e is not None or "Nuño Vidal" in (err or ""), (err or "")[:100])
    if e is None:
        e, _ = await w.call("entity_get", world=WORLD, ref="Nuño Vidal")
    has_loc = bool(e) and any(k in e for k in ("last_seen", "location", "last_location"))
    w.check("entity_get says where Nuño was last seen", has_loc, "keys=" + ",".join(sorted((e or {}).keys()))[:160])
    # "¿Qué sabe Iria?" - knowledge lives only in fact text
    res, _ = await w.call("world_search", world=WORLD, query="Iria sabe")
    facts = [f["text"] for f in (res or {}).get("facts", [])]
    w.check("'¿qué sabe Iria?' returns the three 'Iria sabe' facts", sum("Iria sabe" in f for f in facts) >= 3, f"{len(facts)} facts")
    # "¿Sabe Riera lo de la llave?" - no knowledge model to answer 'no'
    res, _ = await w.call("world_check", world=WORLD, statement="El comisario Riera le enseña a Iria la llave del faro que encontró junto a Mateo.")
    why = [c["why"] for c in (res or {}).get("conflicts", [])]
    w.check("world_check objects to Riera knowing about the key for a knowledge reason",
            bool(why) and not all("muert" in x or "dead" in x for x in why),
            f"conflicts={why}, llm_judge={(res or {}).get('llm_judge')}")
    # A dead character only mentioned, not acting, must not be a conflict.
    res, _ = await w.call("world_check", world=WORLD, statement="Iria deja flores en la tumba de Mateo Lür.")
    w.check("mentioning dead Mateo (his grave) is not a conflict", res is not None and res["consistent"],
            json.dumps((res or {}).get("conflicts"), ensure_ascii=False)[:160])
    e, _ = await w.call("entity_get", world=WORLD, ref="Iria Castro")
    print(f"  entity_get Iria: {len(json.dumps(e, ensure_ascii=False))} chars, {len((e or {}).get('facts', []))} facts, facts_has_more={(e or {}).get('facts_has_more')}")


# ---------------------------------------------------------------------------
# 5. Chapter export (UC3)
# ---------------------------------------------------------------------------

async def chapter(w: Walk) -> None:
    print("\n== 5. Chapter export ==")
    worlds, _ = await w.call("story_worlds")
    cur = next(x for x in worlds["worlds"] if x["name"] == WORLD)["current_session"]
    session_ref = cur["id"] if isinstance(cur, dict) else cur
    text, offset, pages = "", 0, 0
    while True:
        res, err = await w.call("session_export", world=WORLD, session=session_ref, offset=offset, max_chars=4000)
        if not res:
            break
        text += res["text"]
        pages += 1
        if not res["truncated"]:
            break
        offset = res["next_offset"]
    out = w.out / "chapter.md"
    out.write_text(text, encoding="utf-8")
    print(f"  {pages} pages, {len(text)} chars -> {out}")
    w.check("chapter has no short ids (E12, F3)", not re.search(r"\b[EFTC]\d+\b", text))
    w.check("chapter has no JSON fences", "```" not in text)
    w.check("chapter leaves out OOC lines", "OOC" not in text and "Pausa para cenar" not in text)
    w.check("chapter leaves out dice lines", "\U0001f3b2" not in text and "2d6" not in text)
    w.check("chapter has no undone turn", "no vuelve a levantarse" not in text)
    w.check("chapter has no raw 'action' blockquotes", not re.search(r"^> ", text, re.M))
    w.check("Spanish dialogue keeps its raya, no English quotes added", "“" not in text)
    w.check("chapter title is not a generic 'Session N'", not re.search(r"^# Session \d+", text, re.M), text.splitlines()[0] if text else "")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("SCHEHERAZADE_URL", "http://127.0.0.1:18860"))
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data-uxtest" / "agent-walk")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)],
                                   env={**os.environ, "SCHEHERAZADE_URL": args.url})
    t0 = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            init = await s.initialize()
            print(f"server: {init.serverInfo.name}; instructions: {len(init.instructions or '')} chars")
            w = Walk(s, args.out)
            await discovery(w)
            await build_world(w)
            await ensure_clock(w, args.url)
            await session(w)
            await questions(w)
            await chapter(w)
    failed = [c for c in w.checks if not c[1]]
    print(f"\n{w.calls} calls, {w.total_result_chars} result chars, {time.perf_counter() - t0:.1f} s")
    print(f"{len(w.checks) - len(failed)}/{len(w.checks)} checks passed")
    for what, _, detail in failed:
        print(f"  FAIL {what}" + (f"  ({detail})" if detail else ""))
    (args.out / "transcript.json").write_text(json.dumps({"calls": w.log, "checks": w.checks}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
