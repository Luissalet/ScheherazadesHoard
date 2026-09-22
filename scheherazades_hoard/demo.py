"""Seed data for `--demo`: an original setting, "El Archipiélago de Sal"
(The Salt Archipelago) — invented names, no real people or franchises.
Deterministic (seeded dice) so screenshots and manual runs are reproducible.

Idempotent: if a world with this name already exists, seeding is skipped.
"""
from __future__ import annotations

from . import delta as delta_mod
from . import dice, store

WORLD_NAME = "El Archipiélago de Sal"


def seed_demo_world(conn) -> dict:
    existing = [w for w in store.list_worlds(conn) if w["name"] == WORLD_NAME]
    if existing:
        return existing[0]

    world = store.create_world(
        conn, WORLD_NAME,
        genre="fantasía de aventuras", tone="melancólico, salino, esperanzado a pesar de todo",
        premise=(
            "Un reino se hundió hace una generación. Sus torres asoman entre las olas, "
            "sus campanas suenan bajo el agua con la marea, y quienes sobrevivieron "
            "construyeron una vida nueva sobre los restos de la antigua. Todos buscan "
            "el Corazón de Sal, la reliquia que dicen podría contener la marea para siempre "
            "— o hundir lo que queda del mundo por completo."
        ),
        ruleset="pbta_2d6", language="es",
        rules_text=(
            "Powered by the Apocalypse simplificado: tira 2d6 + estadística. "
            "6- fallo con complicación, 7-9 éxito parcial, 10+ éxito total."
        ),
        content_lines=["sin violencia sexual", "sin daño a menores"],
        content_veils=["la muerte por ahogamiento se narra sin detalle gráfico"],
        style_notes="Prosa corta, sensorial, con sal y sonido de campanas lejanas. Segunda persona para las acciones del jugador.",
        calendar={"months": ["Bruma", "Marejada", "Calma", "Tormenta"], "current": "Marejada 12"},
    )
    wid = world["id"]

    # -- locations ----------------------------------------------------------
    puerto = store.create_entity(
        conn, wid, "location", "Puerto Salado",
        summary="Un muelle a medio hundir, remendado con maderos de barcos naufragados.",
        description="La única base de operaciones que queda en pie tras la Inundación. Huele a brea y a sal vieja.",
        tags=["base", "puerto"],
    )
    aguablanca = store.create_entity(
        conn, wid, "location", "Aguablanca",
        summary="La ciudad sumergida a medias, corte de la Reina Ulla.",
        description="Las plantas altas de sus torres siguen habitadas; las bajas pertenecen a los peces.",
        tags=["ciudad", "corte"],
    )
    faro = store.create_entity(
        conn, wid, "location", "El Faro Hundido",
        summary="Una torre que ya no guía barcos, sino secretos.",
        description="Sede de los Guardianes del Faro, tallada en la roca que sobrevivió a la Inundación.",
        parent_id=None, tags=["orden", "secreto"],
    )
    bancos = store.create_entity(
        conn, wid, "location", "Los Bancos de Hueso",
        summary="Un arrecife traicionero sembrado de cascos rotos.",
        description="Nombrado por los huesos de barco que asoman en la bajamar. Nadie navega ahí de noche.",
        tags=["peligro", "arrecife"],
    )

    # -- factions -------------------------------------------------------------
    guardianes = store.create_entity(
        conn, wid, "faction", "Los Guardianes del Faro",
        summary="Una orden secreta que protege lo que queda del Corazón de Sal.",
        description="Visten de gris ceniza y no revelan su rostro fuera del Faro.",
        tags=["orden", "secreto"],
    )
    cabildo = store.create_entity(
        conn, wid, "faction", "El Cabildo de Aguablanca",
        summary="El consejo que gobierna la ciudad sumergida junto a la Reina.",
        description="Seis familias que sobrevivieron a la Inundación con sus fortunas casi intactas.",
        tags=["gobierno", "politica"],
    )

    # -- items & lore ---------------------------------------------------------
    corazon = store.create_entity(
        conn, wid, "item", "El Corazón de Sal",
        summary="Una reliquia legendaria que, se dice, puede contener la marea.",
        description="Nadie vivo lo ha visto. Los mapas que lo señalan se contradicen entre sí.",
        tags=["reliquia", "macguffin"],
    )
    brujula = store.create_entity(
        conn, wid, "item", "Brújula de Hueso",
        summary="Una brújula tallada en hueso de ballena que no señala al norte, sino al peligro más cercano.",
        fields={"uso": "advierte de amenazas inminentes, no de direcciones"},
        tags=["reliquia", "herramienta"],
    )
    inundacion = store.create_entity(
        conn, wid, "lore", "La Inundación Primera",
        summary="El mito fundacional: el mar se tragó el reino en una sola noche de tormenta.",
        description="Algunos dicen que fue un castigo. Otros, que fue un trato que salió mal. Nadie se pone de acuerdo.",
        tags=["mito", "historia"],
    )

    # -- characters (each with a secret) ---------------------------------------
    marisol = store.create_entity(
        conn, wid, "character", "Marisol Vega", aliases=["La Contramaestre"],
        summary="Capitana pirata, antigua oficial de la armada hundida.",
        description="Lleva el pelo trenzado con anzuelos de plata. Nunca duerme sin un cuchillo cerca.",
        fields={"coraje": 2, "sagacidad": 1, "corazon": 0, "brutalidad": 1},
        secrets="Trabaja en secreto para los Guardianes del Faro a cambio de un mapa hacia el Corazón de Sal.",
        status="alive", tags=["capitana", "protagonista"],
    )
    tomas = store.create_entity(
        conn, wid, "character", "Tomás Ferro",
        summary="Primer oficial de Marisol, leal hasta la terquedad.",
        description="Manos grandes, voz baja. Fue herrero antes de la Inundación.",
        fields={"coraje": 1, "sagacidad": 0, "corazon": 2, "brutalidad": 1},
        secrets="Tose sangre por las noches. Tiene la fiebre gris y lo oculta para no preocupar a la tripulación.",
        status="alive", tags=["oficial", "leal"],
    )
    reina_ulla = store.create_entity(
        conn, wid, "character", "Reina Ulla",
        summary="Gobernante de Aguablanca desde antes de la Inundación.",
        description="No ha salido de su torre en veinte años. Habla como si el agua aún no hubiera subido.",
        fields={"coraje": 1, "sagacidad": 2, "corazon": 0, "brutalidad": 0},
        secrets="Hizo un pacto con una criatura de las profundidades para salvar a su hija — un pacto que aún no ha pagado.",
        status="alive", tags=["realeza", "corte"],
    )
    cato = store.create_entity(
        conn, wid, "character", "Doctor Emeric Cato",
        summary="Erudito exiliado del Cabildo, obsesionado con el Corazón de Sal.",
        description="Lleva consigo cuadernos que nadie más puede leer, escritos en una taquigrafía propia.",
        fields={"coraje": 0, "sagacidad": 2, "corazon": 0, "brutalidad": 0},
        secrets="Robó el mapa original del Corazón de Sal del archivo del Cabildo antes de su exilio.",
        status="alive", tags=["erudito", "exiliado"],
    )
    vela = store.create_entity(
        conn, wid, "character", "Vela Nocturna",
        summary="Contrabandista joven que conoce los Bancos de Hueso mejor que nadie.",
        description="Nunca se quita los guantes. Silba canciones que nadie más recuerda.",
        fields={"coraje": 2, "sagacidad": 1, "corazon": 1, "brutalidad": 0},
        secrets="Es la hija perdida de la Reina Ulla, entregada en secreto la noche de la Inundación.",
        status="alive", tags=["contrabandista", "joven"],
    )

    # -- relations --------------------------------------------------------------
    store.create_relation(conn, wid, tomas["id"], marisol["id"], "protege a")
    store.create_relation(conn, wid, marisol["id"], tomas["id"], "confia en")
    store.create_relation(conn, wid, marisol["id"], reina_ulla["id"], "negocia con")
    store.create_relation(conn, wid, reina_ulla["id"], cabildo["id"], "gobierna con")
    store.create_relation(conn, wid, vela["id"], marisol["id"], "trabaja para")
    store.create_relation(conn, wid, cato["id"], guardianes["id"], "enemigo de")
    store.create_relation(conn, wid, marisol["id"], guardianes["id"], "aliado de")

    # -- established facts --------------------------------------------------------
    store.create_fact(conn, wid, "Marisol perdió su barco original, el Argento, hace tres años en Los Bancos de Hueso.",
                       entity_ids=[marisol["id"], bancos["id"]], canon=True)
    store.create_fact(conn, wid, "El Corazón de Sal puede, según la leyenda, contener la marea para siempre.",
                       entity_ids=[corazon["id"]], canon=True)
    store.create_fact(conn, wid, "La Reina Ulla no ha salido de Aguablanca en veinte años.",
                       entity_ids=[reina_ulla["id"], aguablanca["id"]], canon=True)
    store.create_fact(conn, wid, "Los Guardianes del Faro no revelan su rostro fuera del Faro Hundido.",
                       entity_ids=[guardianes["id"], faro["id"]], canon=True)
    store.create_fact(conn, wid, "El Cabildo de Aguablanca exilió al Doctor Cato hace dos años sin explicar por qué en público.",
                       entity_ids=[cato["id"], cabildo["id"]], canon=True)

    # -- timeline --------------------------------------------------------------
    store.create_timeline_event(conn, wid, "Bruma 3 (hace veinte años)", "La Inundación Primera se traga el reino en una noche.",
                                 entity_ids=[inundacion["id"]])
    store.create_timeline_event(conn, wid, "Tormenta 9 (hace tres años)", "El Argento naufraga en Los Bancos de Hueso.",
                                 entity_ids=[marisol["id"], bancos["id"]])

    # -- threads --------------------------------------------------------------
    store.create_thread(conn, wid, "¿Quién hundió el Argento?", status="open",
                         notes="Marisol sospecha que no fue una tormenta cualquiera.")
    store.create_thread(conn, wid, "El pacto de la Reina Ulla", status="open",
                         notes="Algo se le debe a las profundidades, y el plazo se acerca.")
    store.create_thread(conn, wid, "La fiebre de Tomás", status="open",
                         notes="Empeora. Marisol aún no lo sabe.")

    # -- clocks --------------------------------------------------------------
    marea = store.create_clock(conn, wid, "Marea de Sal", segments=6,
                                on_full="La marea cubre Puerto Salado por completo durante tres días.")
    store.tick_clock(conn, wid, marea["ref"], 2)
    sospecha = store.create_clock(conn, wid, "Sospecha del Cabildo", segments=4,
                                   on_full="El Cabildo ordena arrestar a Marisol la próxima vez que atraque en Aguablanca.")
    store.tick_clock(conn, wid, sospecha["ref"], 1)

    # -- random tables --------------------------------------------------------
    store.create_table(conn, wid, "Rumores del Puerto", [
        {"text": "un pescador jura haber visto luces bajo el agua cerca del Faro Hundido", "weight": 2},
        {"text": "el Cabildo ha subido el precio de la sal otra vez", "weight": 2},
        {"text": "alguien pregunta por Marisol usando su nombre de antes de la Inundación", "weight": 1},
        {"text": "[[Encuentros en los Bancos de Hueso]]", "weight": 1},
    ])
    store.create_table(conn, wid, "Encuentros en los Bancos de Hueso", [
        {"text": "un casco medio hundido, aún no saqueado", "weight": 2},
        {"text": "una patrulla del Cabildo, lejos de su territorio habitual", "weight": 1},
        {"text": "el canto de algo grande, justo bajo la quilla", "weight": 1},
    ])

    # -- one played session (~12 turns), with rolls and applied deltas ---------
    session = store.start_session(conn, wid, title="Primera noche en el Puerto Salado")
    sid = session["id"]

    def add(role, author, text, rolls=None, scene=None, delta=None):
        # The same single-transaction path story_append uses, so the demo's
        # turns carry normalised scenes and undo snapshots like real ones.
        d = dict(delta or {})
        if scene is not None:
            d["scene"] = scene
        turn, _result, rejected = delta_mod.record_turn(conn, wid, sid, d, role, author, text=text, rolls=rolls)
        if rejected:  # the seed data is ours; a rejection is a bug here
            raise RuntimeError(f"demo delta rejected: {rejected}")
        return turn

    def logged_move(stat_name: str, seed: int, reason: str) -> dict:
        """A 2d6+stat move rolled and written to the audited dice log."""
        stat = marisol["fields"][stat_name]
        expression = f"2d6+{stat}"
        result = dice.roll(expression, seed=seed)
        store.log_dice(conn, expression, result.total, [d.to_dict() for d in result.dice],
                       seed=seed, reason=reason, who="agent", world_id=wid)
        return {"expression": expression, "total": result.total, "band": dice.band_2d6(result.total),
                "rolls": [d.value for d in result.dice], "seed": seed}

    scene0 = {"location": puerto["ref"], "present": [marisol["ref"], tomas["ref"]], "mood": "tenso, expectante"}
    add("narration", "narrator",
        "La niebla se cierra sobre Puerto Salado como una manta mojada. Marisol cuenta las velas "
        "que quedan en el Argento II y no le gusta el número. Tomás repara una red que ya no sirve, "
        "solo para tener las manos ocupadas.",
        scene=scene0)
    add("dialogue", "user", "«Deberíamos zarpar antes de que suba la marea», le digo a Tomás.")
    add("dialogue", "narrator", "Tomás no levanta la vista de la red. «La marea siempre sube. La pregunta es adónde vamos.»")
    r1 = logged_move("sagacidad", 101, "Marisol recuerda el rumbo de la Brújula de Hueso")
    add("roll", "agent", "Marisol intenta recordar el rumbo que la Brújula de Hueso señaló anoche (2d6+sagacidad).",
        rolls=[r1])
    add("narration", "narrator",
        "Un golpe parcial: recuerda casi todo, salvo un detalle que se le escapa entre la niebla — "
        "la brújula señaló dos veces hacia los Bancos de Hueso esta semana. Eso nunca había pasado.",
        delta={"new_facts": [{"text": "La Brújula de Hueso ha señalado dos veces hacia Los Bancos de Hueso esta semana.",
                               "entity_ids": [brujula["ref"], bancos["ref"]]}]})
    add("action", "user", "Reviso el casco en busca de daños antes de decidir nada.")
    r2 = logged_move("brutalidad", 201, "Marisol revisa el casco del Argento II")
    add("roll", "agent", "Marisol revisa el casco palmo a palmo (2d6+brutalidad).",
        rolls=[r2])
    add("narration", "narrator",
        "El casco aguanta, pero por poco. Tomás señala una vía de agua nueva cerca de la quilla — "
        "nada urgente todavía, pero tampoco algo para ignorar dos semanas más.")
    add("ooc", "user", "¿Podemos repararlo en el puerto o necesitamos ir a Aguablanca?")
    add("system", "narrator", "Puede repararse en Puerto Salado, pero tardará medio día y llamará la atención.")
    add("dialogue", "user", "«Vamos a arriesgarnos con los Bancos de Hueso. La brújula señaló algo por algo.»")
    add("narration", "narrator",
        "Tomás guarda la red sin decir nada, pero endereza los hombros como quien ya conoce esa mirada "
        "en Marisol y sabe que discutir no sirve de nada.",
        delta={"clock_ticks": [{"ref": marea["ref"], "ticks": 1}],
               "scene": {"location": puerto["ref"], "present": [marisol["ref"], tomas["ref"]], "mood": "decidido"}})
    add("narration", "narrator",
        "Zarpan con la marea baja, hacia los huesos de barcos que nadie más se atreve a nombrar de noche.")

    return world
