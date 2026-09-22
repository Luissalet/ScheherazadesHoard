// Shapes mirrored from the Python API (scheherazades_hoard/store.py,
// context.py, delta.py, backend.py). Kept intentionally loose (extra
// backend fields are just ignored) rather than fighting pydantic 1:1.

export type Ruleset = "freeform" | "d20" | "pbta_2d6";
export type EntityKind = "character" | "location" | "faction" | "item" | "lore" | "creature";
export type EntityStatus = "alive" | "dead" | "missing" | "destroyed" | "active" | "unknown";
export type ThreadStatus = "open" | "advanced" | "resolved" | "abandoned";
export type TurnRole = "narration" | "action" | "dialogue" | "ooc" | "roll" | "system";
export type TurnAuthor = "user" | "narrator" | "agent";

export interface World {
  id: string;
  name: string;
  genre: string;
  tone: string;
  premise: string;
  rules_text: string;
  ruleset: Ruleset;
  content_lines: string[];
  content_veils: string[];
  calendar: Record<string, unknown>;
  style_notes: string;
  language: string;
  current_session_id: string | null;
  created_at: number;
  updated_at: number;
  counts?: { entities: number; open_threads: number; sessions: number };
  current_session?: { id: string; title: string } | null;
}

export interface Relation {
  id: string;
  world_id: string;
  a_id: string;
  b_id: string;
  type: string;
  note: string;
  since: string;
  created_at: number;
}

/** A relation as seen from one entity (the entity detail endpoint). */
export interface EntityRelation {
  id: string;
  type: string;
  direction: "out" | "in";
  other_id: string;
  other_ref: string | null;
  other_name: string;
  note: string;
  since: string;
}

export interface EntityBrief {
  ref: string;
  with?: string;
  type?: string;
}

export interface Entity {
  id: string;
  world_id: string;
  seq: number;
  ref: string;
  kind: EntityKind;
  name: string;
  aliases: string[];
  summary: string;
  description: string;
  fields: Record<string, unknown>;
  secrets?: string;
  status: EntityStatus;
  tags: string[];
  parent_id: string | null;
  images: string[];
  created_at: number;
  updated_at: number;
  relations?: EntityRelation[];
  facts?: Fact[];
}

export interface Fact {
  id: string;
  world_id: string;
  seq: number;
  ref: string;
  text: string;
  session_id: string | null;
  turn_id: string | null;
  entity_ids: string[];
  canon: boolean;
  created_at: number;
}

export interface TimelineEvent {
  id: string;
  world_id: string;
  in_world_date: string;
  summary: string;
  entity_ids: string[];
  session_id: string | null;
  turn_id: string | null;
  created_at: number;
}

export interface Thread {
  id: string;
  world_id: string;
  seq: number;
  ref: string;
  title: string;
  status: ThreadStatus;
  notes: string;
  created_at: number;
  updated_at: number;
}

export interface Clock {
  id: string;
  world_id: string;
  seq: number;
  ref: string;
  name: string;
  segments: number;
  filled: number;
  full: boolean;
  on_full: string;
  created_at: number;
  updated_at: number;
}

export interface RandomTable {
  id: string;
  world_id: string;
  name: string;
  entries: { text: string; weight: number }[];
  created_at: number;
  updated_at: number;
}

export interface Session {
  id: string;
  world_id: string;
  title: string;
  started_at: number;
  ended_at: number | null;
}

export interface Turn {
  id: string;
  world_id: string;
  session_id: string;
  idx: number;
  role: TurnRole;
  author: TurnAuthor;
  text: string;
  rolls: Record<string, unknown>[];
  scene: { location?: string | null; present?: string[]; mood?: string };
  delta: Record<string, unknown> | null;
  applied: boolean;
  undone: boolean;
  created_at: number;
}

export interface DiceRollResult {
  expression: string;
  total: number;
  kept: number[];
  dropped: number[];
  seed: number | null;
  detail: string;
  log_id: string;
  band?: "miss" | "weak_hit" | "strong_hit";
  natural?: number;
  crit?: "success" | "fail" | null;
}

export interface DiceLogEntry {
  id: string;
  world_id: string | null;
  expression: string;
  result: number;
  dice: Record<string, unknown>[];
  seed: number | null;
  reason: string;
  who: string;
  created_at: number;
}

export interface WorldContextResult {
  world_id: string;
  brief: string;
  scene: { location: { ref: string; name: string } | null; present: Entity[]; mood: string };
  lore: { ref: string; canon: boolean; text: string }[];
  threads: { ref: string; title: string; status: ThreadStatus }[];
  clocks: { ref: string; name: string; filled: number; segments: number }[];
  recent_turns: { role: string; author: string; text: string }[];
  budget_chars: number;
  used_chars: number;
  truncated: boolean;
}

export interface NarrateResult {
  narration: string;
  delta: Record<string, unknown> | null;
  unparsed: boolean;
  raw: string;
  context: WorldContextResult;
  model: string;
  provider: string;
  usage: Record<string, unknown>;
  elapsed_ms: number;
}

export interface StoryAppendResult {
  turn_id: string;
  turn_index: number;
  session_id: string;
  role: TurnRole;
  scene: { location: { ref: string; name: string } | null; present: { ref: string; name: string }[]; mood: string };
  applied: Record<string, unknown>;
  rejected: { category: string; item: string; reason: string }[];
}

export interface BackendStatus {
  llm: {
    capability: string;
    state: "resolved" | "unavailable";
    provider: string | null;
    url: string | null;
    model: string | null;
    api: string | null;
    reason: string;
  };
  config: {
    llm_url: string | null;
    llm_model: string | null;
    faustus_url: string | null;
    token_set: boolean;
    allow_load: boolean;
    only_resident: boolean;
  };
  checked_at: number;
  config_error?: string;
}

export interface AgentCall {
  id: string;
  tool: string;
  args_summary: string;
  duration_ms: number;
  ok: boolean;
  error: string | null;
  created_at: number;
}

export interface WorldCheckResult {
  consistent: boolean;
  conflicts: { fact_id: string; text: string; why: string }[];
  checked: string;
  rules_checked: string[];
  llm_judge: "used" | "unavailable" | "not_configured" | "no_candidates";
}

export interface ApiErrorBody {
  error: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.error || `HTTP ${status}`);
    this.status = status;
    this.code = body.error || "error";
  }
}
