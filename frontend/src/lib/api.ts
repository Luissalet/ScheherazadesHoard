import type {
  AgentCall, BackendStatus, Clock, DiceLogEntry, DiceRollResult, Entity, Fact,
  NarrateResult, RandomTable, Relation, Session, StoryAppendResult, Thread,
  TimelineEvent, Turn, World, WorldCheckResult, WorldContextResult,
} from "./types";
import { ApiError } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    // Marks the human's own actions so they stay out of the assistant audit.
    headers: { "Content-Type": "application/json", "X-Hoard-Client": "ui", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let body: { error: string; message: string };
    try {
      body = await res.json();
    } catch {
      body = { error: "http_error", message: res.statusText };
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });

const agent = <T,>(tool: string, body: unknown) => post<T>(`/api/agent/${tool}`, body);

export const api = {
  health: () => get<{ service: string; name: string; version: string; status: string; worlds: number }>("/api/health"),
  backend: () => get<BackendStatus>("/api/backend"),
  recheckBackend: () => post<BackendStatus>("/api/backend/recheck"),
  setBackendSettings: (body: Partial<{ llm_url: string; llm_model: string; faustus_url: string; faustus_token: string; allow_load: boolean }>) =>
    post<BackendStatus>("/api/backend/settings", body),

  listWorlds: () => get<World[]>("/api/worlds"),
  getWorld: (world: string) => get<World>(`/api/worlds/${encodeURIComponent(world)}`),
  createWorld: (body: Partial<World> & { name: string }) => agent<World>("story_world_create", body),
  updateWorld: (world: string, body: Partial<World>) => patch<World>(`/api/worlds/${encodeURIComponent(world)}`, body),

  listEntities: (world: string, kind?: string) =>
    get<Entity[]>(`/api/worlds/${world}/entities${kind ? `?kind=${kind}` : ""}`),
  getEntity: (world: string, ref: string, includeSecrets = false) =>
    get<Entity>(`/api/worlds/${world}/entities/${encodeURIComponent(ref)}?include_secrets=${includeSecrets}`),
  createEntity: (world: string, body: Partial<Entity> & { kind: string; name: string }) =>
    post<Entity>(`/api/worlds/${world}/entities`, body),
  patchEntity: (world: string, ref: string, body: Partial<Entity>) =>
    patch<Entity>(`/api/worlds/${world}/entities/${encodeURIComponent(ref)}`, body),
  upsertEntity: (world: string, body: Partial<Entity> & { kind: string; name: string }) =>
    agent<Entity>("entity_upsert", { world, ...body }),

  listRelations: (world: string, entity?: string) =>
    get<Relation[]>(`/api/worlds/${world}/relations${entity ? `?entity=${entity}` : ""}`),
  createRelation: (world: string, a: string, b: string, type: string, note = "") =>
    post<Relation>(`/api/worlds/${world}/relations`, { a, b, type, note }),

  listFacts: (world: string, entity?: string) =>
    get<Fact[]>(`/api/worlds/${world}/facts${entity ? `?entity=${entity}` : ""}`),
  createFact: (world: string, text: string, entity_ids: string[] = [], canon = false) =>
    post<Fact>(`/api/worlds/${world}/facts`, { text, entity_ids, canon }),

  listTimeline: (world: string) => get<TimelineEvent[]>(`/api/worlds/${world}/timeline`),
  createTimelineEvent: (world: string, summary: string, in_world_date = "", entity_ids: string[] = []) =>
    post<TimelineEvent>(`/api/worlds/${world}/timeline`, { summary, in_world_date, entity_ids }),

  listThreads: (world: string) => get<Thread[]>(`/api/worlds/${world}/threads`),
  createThread: (world: string, title: string, status = "open", notes = "") =>
    post<Thread>(`/api/worlds/${world}/threads`, { title, status, notes }),
  updateThread: (world: string, thread: string, status?: string, note?: string) =>
    agent<Thread>("thread_update", { world, thread, status, note }),

  listClocks: (world: string) => get<Clock[]>(`/api/worlds/${world}/clocks`),
  createClock: (world: string, name: string, segments = 4, on_full = "") =>
    post<Clock>(`/api/worlds/${world}/clocks`, { name, segments, on_full }),
  tickClock: (world: string, clock: string, ticks: number) =>
    agent<Clock>("clock_tick", { world, clock, ticks }),

  listTables: (world: string) => get<RandomTable[]>(`/api/worlds/${world}/tables`),
  createTable: (world: string, name: string, entries: { text: string; weight?: number }[]) =>
    post<RandomTable>(`/api/worlds/${world}/tables`, { name, entries }),
  rollTable: (world: string, table: string) =>
    agent<{ text: string; rolls: { table: string; entry: string }[] }>("table_roll", { world, table }),

  listSessions: (world: string) => get<Session[]>(`/api/worlds/${world}/sessions`),
  startSession: (world: string, title = "") => post<Session>(`/api/worlds/${world}/sessions`, { title }),
  renameSession: (world: string, session: string, title: string) =>
    patch<Session>(`/api/worlds/${world}/sessions/${encodeURIComponent(session)}`, { title }),
  listTurns: (world: string, session: string) => get<Turn[]>(`/api/worlds/${world}/sessions/${session}/turns`),

  listDiceLog: (world: string, limit = 30) => get<DiceLogEntry[]>(`/api/worlds/${world}/dice_log?limit=${limit}`),
  rollDice: (expression: string, world?: string, reason = "", who = "user") =>
    agent<DiceRollResult>("dice_roll", { expression, world, reason, who }),

  worldContext: (world: string, opts?: { focus?: string; include_secrets?: boolean; budget_chars?: number }) =>
    agent<WorldContextResult>("world_context", { world, ...opts }),
  worldSearch: (world: string, query: string, kinds?: string[], limit = 8) =>
    agent<{ entities: Entity[]; facts: Fact[] }>("world_search", { world, query, kinds, limit }),
  worldCheck: (world: string, statement: string) => agent<WorldCheckResult>("world_check", { world, statement }),

  narrate: (world: string, action_text: string, scene?: Record<string, unknown>, budget_chars = 3000) =>
    post<NarrateResult>(`/api/worlds/${world}/narrate`, { world, action_text, scene, budget_chars }),
  storyAppend: (world: string, text: string, opts?: { role?: string; author?: string; delta?: Record<string, unknown> | null; scene?: Record<string, unknown>; rolls?: Record<string, unknown>[] }) =>
    agent<StoryAppendResult>("story_append", { world, text, ...opts }),
  storyUndo: (world: string) => agent<{ undone_turn_id: string }>("story_undo", { world }),

  chapter: (world: string, session: string, polish = false) =>
    post<{ text: string; polished: boolean; reason: string }>(
      `/api/worlds/${world}/sessions/${encodeURIComponent(session)}/chapter`, { polish }),
  worldExportJson: (world: string) => get<Record<string, unknown>>(`/api/worlds/${world}/export.json`),
  worldImportJson: (data: unknown) => post<World>("/api/worlds/import", data),
  bibleMdUrl: (world: string, includeSecrets = false) =>
    `/api/worlds/${world}/bible.md?include_secrets=${includeSecrets}`,

  prosperoAvailable: () => get<{ available: boolean }>("/api/prospero/available"),
  illustrate: (world: string, scene_brief: string, location_name = "", mood = "") =>
    post<{ image_url: string }>(`/api/worlds/${world}/illustrate`, { scene_brief, location_name, mood }),

  agentCalls: (limit = 50) => get<AgentCall[]>(`/api/agent_calls?limit=${limit}`),
};

export { ApiError };
