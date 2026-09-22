export type Lang = "es" | "en";

const dict = {
  appName: { es: "Scheherazade's Hoard", en: "Scheherazade's Hoard" },
  nav_worlds: { es: "Mundos", en: "Worlds" },
  nav_play: { es: "Jugar", en: "Play" },
  nav_bible: { es: "Biblia", en: "Bible" },
  nav_map: { es: "Mapa de relaciones", en: "Map of relations" },
  nav_timeline: { es: "Cronología", en: "Timeline" },
  nav_threads: { es: "Hilos y relojes", en: "Threads & clocks" },
  nav_tables: { es: "Tablas", en: "Tables" },
  nav_sessions: { es: "Sesiones", en: "Sessions" },
  nav_dice: { es: "Registro de dados", en: "Dice log" },
  nav_backends: { es: "Backends", en: "Backends" },
  nav_activity: { es: "Actividad del asistente", en: "Assistant activity" },
  nav_settings: { es: "Ajustes", en: "Settings" },

  worlds_title: { es: "Tus mundos", en: "Your worlds" },
  worlds_empty: { es: "Aún no has creado ningún mundo. Crea el primero para empezar a narrar.", en: "You haven't created a world yet. Create your first one to start narrating." },
  worlds_new: { es: "Nuevo mundo", en: "New world" },
  worlds_open: { es: "Abrir", en: "Open" },
  worlds_entity_one: { es: "entidad", en: "entity" },
  worlds_entity_many: { es: "entidades", en: "entities" },
  worlds_open_thread_one: { es: "hilo abierto", en: "open thread" },
  worlds_open_thread_many: { es: "hilos abiertos", en: "open threads" },
  worlds_session_one: { es: "sesión", en: "session" },
  worlds_session_many: { es: "sesiones", en: "sessions" },
  status_open: { es: "Abierto", en: "Open" },
  status_advanced: { es: "Avanzado", en: "Advanced" },
  status_resolved: { es: "Resuelto", en: "Resolved" },
  status_abandoned: { es: "Abandonado", en: "Abandoned" },
  thread_title: { es: "Título del hilo", en: "Thread title" },
  kanban_empty: { es: "Nada aquí todavía", en: "Nothing here yet" },
  world_name: { es: "Nombre", en: "Name" },
  world_genre: { es: "Género", en: "Genre" },
  world_tone: { es: "Tono", en: "Tone" },
  world_premise: { es: "Premisa", en: "Premise" },
  world_ruleset: { es: "Sistema de reglas", en: "Ruleset" },
  world_language: { es: "Idioma del mundo", en: "World language" },
  create: { es: "Crear", en: "Create" },
  cancel: { es: "Cancelar", en: "Cancel" },
  save: { es: "Guardar", en: "Save" },

  play_input_placeholder: { es: "¿Qué haces?", en: "What do you do?" },
  play_mode_narration: { es: "Narración", en: "Narration" },
  play_mode_action: { es: "Acción", en: "Action" },
  play_mode_dialogue: { es: "Diálogo", en: "Dialogue" },
  play_mode_ooc: { es: "Fuera de personaje", en: "Out of character" },
  play_send: { es: "Enviar", en: "Send" },
  play_narrate: { es: "Narrar", en: "Narrate" },
  play_narrating: { es: "Narrando…", en: "Narrating…" },
  play_undo: { es: "Deshacer último turno", en: "Undo last turn" },
  play_illustrate: { es: "Ilustrar escena", en: "Illustrate scene" },
  play_gm_view: { es: "Vista de Guardián", en: "GM view" },
  play_player_view: { es: "Vista de jugador", en: "Player view" },
  play_scene: { es: "Escena", en: "Scene" },
  play_location: { es: "Lugar", en: "Location" },
  play_present: { es: "Presentes", en: "Present" },
  play_mood: { es: "Ambiente", en: "Mood" },
  play_proposed_delta: { es: "Cambios propuestos", en: "Proposed changes" },
  play_accept: { es: "Aceptar", en: "Accept" },
  play_reject: { es: "Rechazar", en: "Reject" },
  play_dice_tray: { es: "Dados", en: "Dice" },
  play_check: { es: "Comprobar continuidad", en: "Continuity check" },
  play_check_placeholder: { es: "p. ej. Ulla ordena zarpar", en: "e.g. Ulla orders them to sail" },
  play_check_ok: { es: "Nada lo contradice", en: "Nothing contradicts it" },
  play_check_judge_used: { es: "revisado también por el modelo", en: "also reviewed by the model" },
  play_check_judge_off: { es: "solo reglas; el modelo no ha intervenido", en: "rules only; the model did not review it" },
  play_roll: { es: "Tirar", en: "Roll" },
  play_empty: { es: "Aún no ha pasado nada. Escribe una acción o pulsa Narrar para empezar la escena.", en: "Nothing has happened yet. Write an action or press Narrate to start the scene." },
  play_no_backend: { es: "No hay ningún modelo disponible. Conecta uno en Backends para narrar automáticamente — mientras tanto puedes seguir jugando escribiendo tú la narración.", en: "No model is available. Connect one under Backends to narrate automatically — meanwhile you can keep playing by writing the narration yourself." },
  play_rejected_items: { es: "elementos rechazados", en: "rejected items" },

  bible_search: { es: "Buscar…", en: "Search…" },
  bible_new_entity: { es: "Nueva entidad", en: "New entity" },
  bible_empty: { es: "Este mundo aún no tiene entidades. Crea la primera.", en: "This world has no entities yet. Create the first one." },
  bible_secrets: { es: "Secretos", en: "Secrets" },
  bible_show_secrets: { es: "Mostrar secretos", en: "Show secrets" },
  bible_facts: { es: "Hechos establecidos", en: "Established facts" },
  bible_relations: { es: "Relaciones", en: "Relations" },
  bible_kind_character: { es: "Personaje", en: "Character" },
  bible_kind_location: { es: "Lugar", en: "Location" },
  bible_kind_faction: { es: "Facción", en: "Faction" },
  bible_kind_item: { es: "Objeto", en: "Item" },
  bible_kind_lore: { es: "Saber", en: "Lore" },
  bible_kind_creature: { es: "Criatura", en: "Creature" },
  bible_edit: { es: "Editar", en: "Edit" },
  bible_field_status: { es: "Estado", en: "Status" },
  bible_field_summary: { es: "Resumen", en: "Summary" },
  bible_field_description: { es: "Descripción", en: "Description" },
  bible_field_aliases: { es: "Apodos (separados por comas)", en: "Aliases (comma-separated)" },
  bible_field_tags: { es: "Etiquetas (separadas por comas)", en: "Tags (comma-separated)" },
  entity_status_alive: { es: "vivo", en: "alive" },
  entity_status_dead: { es: "muerto", en: "dead" },
  entity_status_missing: { es: "desaparecido", en: "missing" },
  entity_status_destroyed: { es: "destruido", en: "destroyed" },
  entity_status_active: { es: "activo", en: "active" },
  entity_status_unknown: { es: "desconocido", en: "unknown" },
  play_scene_edit: { es: "Cambiar escena", en: "Change scene" },
  play_scene_apply: { es: "Aplicar escena", en: "Apply scene" },
  play_scene_no_location: { es: "(sin lugar)", en: "(no location)" },
  play_scene_empty: { es: "Aún no hay escena: elige el lugar y quién está presente.", en: "No scene yet: choose the place and who is present." },
  play_scene_turn: { es: "Escena", en: "Scene" },

  timeline_empty: { es: "Aún no hay eventos en la cronología.", en: "No timeline events yet." },
  threads_empty: { es: "No hay hilos abiertos.", en: "No open threads." },
  clocks_empty: { es: "No hay relojes.", en: "No clocks." },
  clocks_new: { es: "Nuevo reloj", en: "New clock" },
  threads_new: { es: "Nuevo hilo", en: "New thread" },
  tables_empty: { es: "Este mundo no tiene tablas aleatorias.", en: "This world has no random tables yet." },
  tables_new: { es: "Nueva tabla", en: "New table" },
  tables_roll: { es: "Tirar en la tabla", en: "Roll on table" },
  sessions_empty: { es: "Todavía no hay sesiones.", en: "No sessions yet." },
  sessions_new: { es: "Nueva sesión", en: "New session" },
  sessions_new_title_placeholder: { es: "Título de la sesión (opcional)", en: "Session title (optional)" },
  sessions_rename: { es: "Renombrar", en: "Rename" },
  sessions_rename_title: { es: "Nuevo título de la sesión", en: "New session title" },
  export_chapter: { es: "Exportar capítulo (Markdown)", en: "Export chapter (Markdown)" },
  export_bible: { es: "Exportar biblia del mundo", en: "Export world bible" },
  export_json: { es: "Exportar mundo (JSON)", en: "Export world (JSON)" },
  export_polish: { es: "Capítulo pulido por el modelo", en: "Chapter polished by the model" },
  export_polish_fallback: { es: "Se descargó sin pulir", en: "Downloaded unpolished" },
  worlds_import: { es: "Importar mundo (JSON)", en: "Import world (JSON)" },

  dice_empty: { es: "Aún no se ha tirado ningún dado.", en: "No dice rolled yet." },
  dice_roll_button: { es: "Tirar dados", en: "Roll dice" },
  dice_expression: { es: "Expresión (ej. 2d6+3)", en: "Expression (e.g. 2d6+3)" },
  dice_reason: { es: "Motivo (opcional)", en: "Reason (optional)" },

  backend_title: { es: "Backend de modelos compartido", en: "Shared model backend" },
  backend_llm: { es: "Modelo de lenguaje", en: "Language model" },
  backend_state_resolved: { es: "Conectado", en: "Connected" },
  backend_state_unavailable: { es: "No disponible", en: "Unavailable" },
  backend_recheck: { es: "Volver a comprobar", en: "Re-check" },
  backend_manual: { es: "Configuración manual", en: "Manual configuration" },
  backend_llm_url: { es: "URL del modelo", en: "Model URL" },
  backend_llm_model: { es: "Nombre del modelo", en: "Model name" },
  backend_faustus_url: { es: "URL de Faustus", en: "Faustus URL" },
  backend_faustus_token: { es: "Token de Faustus", en: "Faustus token" },
  backend_token_set: { es: "Token guardado", en: "Token saved" },
  backend_token_clear: { es: "Quitar token", en: "Remove token" },
  backend_manual_hint: {
    es: "Déjalo vacío para usar lo que ya sirve Faustus o un servidor local (llama.cpp, Ollama con un modelo cargado, un servidor compatible con OpenAI). Nunca se carga un modelo propio.",
    en: "Leave empty to use what Faustus or a local server (llama.cpp, Ollama with a loaded model, an OpenAI-compatible server) already serves. This app never loads a model of its own.",
  },
  backend_config_error: { es: "backend.json no es válido; se usan los valores por defecto", en: "backend.json is invalid; defaults are in use" },

  activity_empty: { es: "El asistente aún no ha hecho nada en este servidor.", en: "The assistant hasn't done anything on this server yet." },
  activity_tool: { es: "Herramienta", en: "Tool" },
  activity_duration: { es: "Duración", en: "Duration" },
  activity_result: { es: "Resultado", en: "Result" },
  activity_ok: { es: "correcto", en: "ok" },
  activity_error: { es: "error", en: "error" },

  settings_title: { es: "Ajustes", en: "Settings" },
  settings_theme: { es: "Tema", en: "Theme" },
  settings_theme_light: { es: "Claro", en: "Light" },
  settings_theme_dark: { es: "Oscuro", en: "Dark" },
  settings_theme_system: { es: "Sistema", en: "System" },
  settings_language: { es: "Idioma de la interfaz", en: "Interface language" },

  undo_confirm: { es: "¿Deshacer el último turno? Esta acción revierte todos sus cambios.", en: "Undo the last turn? This reverts everything it changed." },
  delete_confirm: { es: "¿Seguro? Pulsa de nuevo para confirmar.", en: "Are you sure? Click again to confirm." },
  loading: { es: "Cargando…", en: "Loading…" },
} as const;

export type DictKey = keyof typeof dict;

export function detectLang(): Lang {
  try {
    const stored = localStorage.getItem("scheherazade.lang");
    if (stored === "es" || stored === "en") return stored;
  } catch {
    /* private browsing / blocked storage: fall through */
  }
  return typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("es") ? "es" : "en";
}

export function persistLang(lang: Lang): void {
  try {
    localStorage.setItem("scheherazade.lang", lang);
  } catch {
    /* ignore */
  }
}

export function t(key: DictKey, lang: Lang): string {
  return dict[key][lang];
}
