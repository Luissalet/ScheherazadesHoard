import { test } from "node:test";
import assert from "node:assert/strict";
import {
  addRefreshHandler, buildContext, changedFields, collectEditors, entityPatchBody, filledFields, installCopilot, publicFields, rebaseForm, setView,
} from "./src/lib/copilot-context.js";

const world = { id: "w_1", name: "Salt Archipelago", genre: "fantasy", ruleset: "pbta_2d6", language: "en", premise: "x".repeat(400), current_session: { id: "s_1", title: "Night one" } };
const maria = { ref: "E1", name: "Maria", kind: "character", status: "alive", summary: "A smuggler", aliases: ["Mari"], tags: [], secrets: "THE SECRET" };
const deps = {
  getWorld: async (id) => { if (id !== "w_1") throw new Error("not found"); return world; },
  getEntity: async (_w, ref) => { if (ref !== "E1") throw new Error("not found"); return maria; },
  getWorldContext: async () => ({ scene: { location: { ref: "E9", name: "The Pier" }, present: [{ ref: "E1", name: "Maria", kind: "character", status: "alive" }], mood: "tense" } }),
  getThreads: async () => [{ ref: "T1", title: "Find the map", status: "open" }, { ref: "T2", title: "Old", status: "resolved" }],
  getClocks: async () => [{ ref: "C1", name: "Storm", filled: 2, segments: 6 }],
};

test("only the fields the user changed are sent, including manual clears", () => {
  assert.deepEqual(changedFields({ name: "A", summary: "x", tags: "a" }, { name: "A", summary: "", tags: "a, b" }), { summary: "", tags: "a, b" });
  assert.deepEqual(entityPatchBody({ summary: "", tags: "a; b, c", aliases: "" }, false), { summary: "", tags: ["a; b", "c"], aliases: [] });
  assert.deepEqual(entityPatchBody({ secrets: "s", status: "dead" }, false), { status: "dead" });
  assert.deepEqual(entityPatchBody({ secrets: "s" }, true), { secrets: "s" });
  assert.deepEqual(publicFields({ secrets: "s", name: "n" }), { name: "n" });
  assert.deepEqual(filledFields({ name: "N", genre: "", ruleset: "freeform", entries: [] }, { ruleset: "freeform" }), { name: "N" });
});

test("a reload keeps what the user typed and updates the rest", () => {
  const before = { name: "Old", summary: "", present: ["E1"] };
  const form = { name: "Old", summary: "typed", present: ["E1"] };
  const after = { name: "Agent name", summary: "", present: ["E1", "E2"] };
  assert.deepEqual(rebaseForm(before, after, form), { name: "Agent name", summary: "typed", present: ["E1", "E2"] });
  assert.deepEqual(changedFields(before, form), { summary: "typed" });
});

test("bible view returns the world as project, the real entity and the editor, without secrets", async () => {
  const editors = [{ kind: "entity-form", object_id: "E1", dirty: true, fields: { summary: "x" } }];
  const ctx = await buildContext({ view: { section: "bible", worldId: "w_1", entityRef: "E1" }, editors, deps });
  assert.deepEqual(ctx.project, { external_project_id: "w_1", title: "Salt Archipelago" });
  assert.deepEqual(ctx.active_objects.map((o) => `${o.kind}:${o.object_id}`), ["world:w_1", "entity:E1"]);
  assert.equal(ctx.view.page, "bible");
  assert.equal(ctx.view.object_id, "E1");
  assert.deepEqual(ctx.view.editor.fields, { summary: "x" });
  assert.ok(!JSON.stringify(ctx).includes("THE SECRET"));
  assert.ok(ctx.active_objects[0].premise.length < 260);
});

test("play view lists the session and the scene cast", async () => {
  const ctx = await buildContext({ view: { section: "play", worldId: "w_1", entityRef: null }, editors: [], deps });
  assert.deepEqual(ctx.active_objects.map((o) => `${o.kind}:${o.object_id}`), ["world:w_1", "session:s_1", "entity:E9", "entity:E1"]);
  assert.equal(ctx.view.scene_mood, "tense");
});

test("threads view lists live threads and clocks only", async () => {
  const ctx = await buildContext({ view: { section: "threads", worldId: "w_1", entityRef: null }, editors: [], deps });
  assert.deepEqual(ctx.active_objects.map((o) => `${o.kind}:${o.object_id}`), ["world:w_1", "thread:T1", "clock:C1"]);
});

test("unknown world, unknown entity, list views and fetch errors yield no object and never throw", async () => {
  const none = await buildContext({ view: { section: "bible", worldId: "w_gone", entityRef: "E1" }, editors: [], deps });
  assert.deepEqual(none.active_objects, []);
  assert.equal(none.project, undefined);
  const worlds = await buildContext({ view: { section: "worlds", worldId: null, entityRef: null }, editors: [], deps });
  assert.deepEqual(worlds.active_objects, []);
  assert.equal(worlds.view.page, "worlds");
  const gone = await buildContext({ view: { section: "bible", worldId: "w_1", entityRef: "E404" }, editors: [], deps });
  assert.deepEqual(gone.active_objects.map((o) => o.kind), ["world"]);
  const broken = await buildContext({ view: { section: "play", worldId: "w_1", entityRef: null }, editors: [], deps: { ...deps, getWorldContext: async () => { throw new Error("down"); } } });
  assert.deepEqual(broken.active_objects.map((o) => o.kind), ["world", "session"]);
  const empty = await buildContext({ view: { section: "bible", worldId: "w_1", entityRef: null }, editors: [], deps: {} });
  assert.deepEqual(empty.active_objects, []);
});

test("an open entity editor adds its entity; creation forms add none", async () => {
  const ctx = await buildContext({ view: { section: "bible", worldId: "w_1", entityRef: null }, deps, editors: [
    { kind: "entity-form", object_id: "E1", dirty: true, fields: { name: "M" } },
    { kind: "entity-new", object_id: null, dirty: true, fields: { name: "New" } },
    { kind: "entity-form", object_id: "E404", dirty: false, fields: {} },
  ] });
  assert.deepEqual(ctx.active_objects.map((o) => o.object_id), ["w_1", "E1"]);
  assert.equal(ctx.view.editors.length, 3);
  assert.equal(ctx.view.editor.fields.name, "M");
});

test("forms answer the context request and edit forms come before creation forms", () => {
  const target = new EventTarget();
  target.addEventListener("scheherazade:context-request", (e) => e.detail.provide({ kind: "world-new", object_id: null }));
  target.addEventListener("scheherazade:context-request", (e) => e.detail.provide({ kind: "entity-form", object_id: "E1" }));
  assert.deepEqual(collectEditors(target).map((e) => e.kind), ["entity-form", "world-new"]);
});

test("turn end (event and callback) refreshes every screen once; installing twice keeps the first", async () => {
  const target = new EventTarget();
  installCopilot(target, deps);
  const first = target.hoardCopilot;
  installCopilot(target, deps);
  assert.equal(target.hoardCopilot, first);
  let a = 0;
  let b = 0;
  const off = addRefreshHandler(() => { a += 1; });
  addRefreshHandler(() => { b += 1; throw new Error("a broken screen must not stop the others"); });
  target.dispatchEvent(new Event("hoard:copilot-turn-end"));
  target.hoardCopilot.onTurnEnd();
  await new Promise((r) => setTimeout(r, 400));
  assert.deepEqual([a, b], [1, 1]);
  off();
});

test("context() reads the current view and the open forms", async () => {
  const target = new EventTarget();
  target.addEventListener("scheherazade:context-request", (e) => e.detail.provide({ kind: "scene-form", object_id: null, dirty: true, fields: { mood: "calm" } }));
  installCopilot(target, deps);
  setView({ section: "play", worldId: "w_1", entityRef: null });
  const ctx = await target.hoardCopilot.context();
  assert.equal(ctx.project.external_project_id, "w_1");
  assert.equal(ctx.view.page, "play");
  assert.deepEqual(ctx.view.editor.fields, { mood: "calm" });
});

test("navigating while the world loads does not mix two views in one context", async () => {
  const worlds = { w_1: world, w_2: { id: "w_2", name: "Other" } };
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const calls = [];
  const slow = {
    ...deps,
    getWorld: async (id) => { await gate; return worlds[id]; },
    getEntity: async (w, ref) => { calls.push(`${w}/${ref}`); return { ...maria, ref }; },
  };
  const target = new EventTarget();
  setView({ section: "bible", worldId: "w_1", entityRef: "E1" });
  installCopilot(target, slow);
  const pending = target.hoardCopilot.context();
  setView({ section: "bible", worldId: "w_2", entityRef: "E2" });
  release();
  const ctx = await pending;
  assert.equal(ctx.project.external_project_id, "w_1");
  assert.deepEqual(ctx.active_objects.map((o) => `${o.kind}:${o.object_id}`), ["world:w_1", "entity:E1"]);
  assert.deepEqual(calls, ["w_1/E1"]);
});
