// What the shared copilot launcher asks this app for: the real objects open in the current view and the unsaved form fields,
// plus a way to refresh the open view when the assistant finishes a turn. Nothing here renders anything and nothing here
// imports the app (dependencies are injected), so the whole file runs under node --test.

const PAGE_NAMES = {
  worlds: "worlds", play: "play", bible: "bible", map: "map", timeline: "timeline", threads: "threads", tables: "tables",
  sessions: "sessions", dice: "dice_log", backends: "backends", activity: "assistant_activity", settings: "settings",
};
const EDITOR_ORDER = { "scene-form": 0, "entity-form": 0, "session-form": 0, "entity-new": 1, "world-new": 1 };
const MAX_CAST = 8;
const MAX_THREADS = 8;
const MAX_CLOCKS = 6;
const PREVIEW = 240;

// ---- form diffing ---------------------------------------------------------------------------------------------------------

// Fields of `draft` whose value differs from `initial` (compared as JSON, so arrays and "" clears count).
export function changedFields(initial, draft) {
  const base = initial || {};
  return Object.fromEntries(Object.entries(draft || {}).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(base[key])));
}

// A refreshed baseline arrives while the user is editing: fields the user did not touch follow the new baseline, touched ones stay.
export function rebaseForm(previousBase, nextBase, form) {
  const out = { ...nextBase };
  for (const key of Object.keys(form)) {
    if (JSON.stringify(form[key]) !== JSON.stringify(previousBase?.[key])) out[key] = form[key];
  }
  return out;
}

const splitList = (text) => String(text ?? "").split(",").map((s) => s.trim()).filter(Boolean);

// The PATCH body for the fields the user changed in the entity editor; secrets only travel when the editor shows them.
export function entityPatchBody(changed, withSecrets) {
  const body = {};
  for (const [key, value] of Object.entries(changed || {})) {
    if (["name", "status", "summary", "description"].includes(key)) body[key] = value;
    else if (key === "aliases" || key === "tags") body[key] = splitList(value);
    else if (key === "secrets" && withSecrets) body.secrets = value;
  }
  return body;
}

// A snapshot must never carry the GM's secrets, whatever the form holds.
export function publicFields(fields) {
  const { secrets: _secrets, ...rest } = fields || {};
  return rest;
}

// For creation forms: only the fields that hold something.
export function filledFields(draft, defaults = {}) {
  return Object.fromEntries(Object.entries(draft || {}).filter(([key, value]) => {
    if (Array.isArray(value)) return value.length > 0;
    if (value === "" || value === null || value === undefined) return false;
    return value !== defaults[key];
  }));
}

// ---- what the app is showing ----------------------------------------------------------------------------------------------

const view = { section: "worlds", worldId: null, entityRef: null };

export function setView(patch) {
  Object.assign(view, patch);
}

export function getView() {
  return { ...view };
}

// Every open form answers this event with a snapshot of what the user has typed: { kind, object_id, dirty, fields }.
export function collectEditors(target = globalThis.window) {
  const found = [];
  if (!target?.dispatchEvent) return found;
  target.dispatchEvent(new CustomEvent("scheherazade:context-request", { detail: { provide: (snapshot) => { if (snapshot) found.push(snapshot); } } }));
  return found.sort((a, b) => (EDITOR_ORDER[a.kind] ?? 9) - (EDITOR_ORDER[b.kind] ?? 9));
}

const pick = (source, keys) => Object.fromEntries(keys.filter((k) => source?.[k] !== undefined && source[k] !== null && source[k] !== "" && !(Array.isArray(source[k]) && source[k].length === 0)).map((k) => [k, source[k]]));
const preview = (text) => { const s = String(text ?? "").trim(); return s.length > PREVIEW ? `${s.slice(0, PREVIEW)}...` : s; };

const worldObject = (w) => ({ kind: "world", object_id: w.id, title: w.name || w.id, ...pick(w, ["genre", "tone", "ruleset", "language"]), ...(w.premise ? { premise: preview(w.premise) } : {}) });
// Secrets are never read for the context: the entity is always fetched without them.
const entityObject = (e) => ({
  kind: "entity", object_id: e.ref || e.id, title: e.name || e.ref || e.id,
  ...(e.kind ? { entity_kind: e.kind } : {}), ...pick(e, ["status", "aliases", "tags"]), ...(e.summary ? { summary: preview(e.summary) } : {}),
});
const sessionObject = (s) => ({ kind: "session", object_id: s.id, title: s.title || s.id });
const threadObject = (th) => ({ kind: "thread", object_id: th.ref || th.id, title: th.title || th.ref, ...pick(th, ["status"]) });
const clockObject = (c) => ({ kind: "clock", object_id: c.ref || c.id, title: c.name || c.ref, filled: c.filled, segments: c.segments });

async function safe(fn) {
  try { return await fn(); } catch { return null; }
}

// Pure core (dependencies injected so it can be tested): never throws; unknown or "new" ids yield no object.
// deps: getWorld(id), getEntity(world, ref), getWorldContext(world), getThreads(world), getClocks(world)
export async function buildContext({ view: v = view, editors = [], deps = {} }) {
  const section = v.section || "worlds";
  const page = PAGE_NAMES[section] || section;
  const out = { active_objects: [], view: { page } };
  const seen = new Set();
  const add = (object) => { const key = `${object.kind}:${object.object_id}`; if (!seen.has(key)) { seen.add(key); out.active_objects.push(object); } };

  const world = v.worldId ? await safe(() => deps.getWorld(v.worldId)) : null;
  if (world?.id) {
    out.project = { external_project_id: world.id, title: world.name || world.id };
    add(worldObject(world));

    if (section === "bible" && v.entityRef) {
      const e = await safe(() => deps.getEntity(world.id, v.entityRef));
      if (e?.ref) { add(entityObject(e)); out.view.object_id = e.ref; }
    }
    if (section === "play") {
      const ctx = await safe(() => deps.getWorldContext(world.id));
      if (world.current_session?.id) add(sessionObject(world.current_session));
      const scene = ctx?.scene;
      if (scene?.location?.ref) add({ kind: "entity", object_id: scene.location.ref, title: scene.location.name || scene.location.ref, entity_kind: "location", role_in_scene: "location" });
      for (const e of (scene?.present || []).slice(0, MAX_CAST)) if (e?.ref) add({ ...entityObject(e), role_in_scene: "present" });
      if (scene?.mood) out.view.scene_mood = preview(scene.mood);
    }
    if (section === "sessions" && world.current_session?.id) add(sessionObject(world.current_session));
    if (section === "threads") {
      const threads = (await safe(() => deps.getThreads(world.id))) || [];
      for (const th of threads.filter((x) => x.status === "open" || x.status === "advanced").slice(0, MAX_THREADS)) add(threadObject(th));
      const clocks = (await safe(() => deps.getClocks(world.id))) || [];
      for (const c of clocks.slice(0, MAX_CLOCKS)) add(clockObject(c));
    }
    for (const ed of editors) {
      if (ed.kind !== "entity-form" || !ed.object_id || ed.object_id === "new" || seen.has(`entity:${ed.object_id}`)) continue;
      const e = await safe(() => deps.getEntity(world.id, ed.object_id));
      if (e?.ref) add(entityObject(e));
    }
  }

  const editor = editors.find((e) => e.dirty) || editors[0];
  if (editor) out.view.editor = editor;
  if (editors.length > 1) out.view.editors = editors;
  return out;
}

// ---- refresh when the assistant finishes a turn -------------------------------------------------------------------------
const handlers = new Set();
let timer = null;

function runRefresh() {
  for (const fn of [...handlers]) {
    try { Promise.resolve(fn()).catch(() => {}); } catch { /* a refresh must never break the page */ }
  }
}

export function scheduleRefresh() {
  clearTimeout(timer);
  timer = setTimeout(runRefresh, 250);
}

// Each screen registers what "reload what is on screen" means for it (it must keep the forms the user is editing untouched).
export function addRefreshHandler(fn) {
  handlers.add(fn);
  return () => { handlers.delete(fn); };
}

export const onTurnEnd = () => scheduleRefresh();

// Once at start: the object the launcher looks for, and the window event it dispatches on turn end (the debounce merges the two).
export function installCopilot(target = globalThis.window, deps = {}) {
  if (!target || target.hoardCopilot) return;
  target.hoardCopilot = {
    context: () => buildContext({ view, editors: collectEditors(target), deps }),
    onTurnEnd,
  };
  target.addEventListener("hoard:copilot-turn-end", scheduleRefresh);
}
