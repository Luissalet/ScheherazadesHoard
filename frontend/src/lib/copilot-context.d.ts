export type Fields = Record<string, unknown>;
export interface EditorSnapshot {
  kind: string;
  object_id: string | null;
  dirty: boolean;
  fields: Fields;
}
export interface ViewState {
  section: string;
  worldId: string | null;
  entityRef: string | null;
}
export interface CopilotDeps {
  getWorld?: (id: string) => Promise<any>;
  getEntity?: (world: string, ref: string) => Promise<any>;
  getWorldContext?: (world: string) => Promise<any>;
  getThreads?: (world: string) => Promise<any[]>;
  getClocks?: (world: string) => Promise<any[]>;
}

export function changedFields(initial: Fields | null | undefined, draft: Fields): Fields;
export function rebaseForm<T extends Fields>(previousBase: Fields | null | undefined, nextBase: T, form: Fields): T;
export function entityPatchBody(changed: Fields, withSecrets: boolean): Record<string, unknown>;
export function publicFields(fields: Fields): Fields;
export function filledFields(draft: Fields, defaults?: Fields): Fields;
export function setView(patch: Partial<ViewState>): void;
export function getView(): ViewState;
export function collectEditors(target?: EventTarget): EditorSnapshot[];
export function buildContext(args: { view?: Partial<ViewState>; editors?: EditorSnapshot[]; deps?: CopilotDeps }): Promise<Record<string, any>>;
export function scheduleRefresh(): void;
export function addRefreshHandler(fn: () => unknown): () => void;
export function onTurnEnd(): void;
export function installCopilot(target?: any, deps?: CopilotDeps): void;
