// React side of the shared copilot contract: wires the API into the context builder and gives screens three small hooks.
import { useEffect, useRef } from "react";
import { api } from "./api";
import { addRefreshHandler, installCopilot as install, publicFields, setView, type Fields, type ViewState } from "./copilot-context";

export function installCopilot() {
  install(window, {
    getWorld: (id) => api.getWorld(id),
    getEntity: (world, ref) => api.getEntity(world, ref, false),
    getWorldContext: (world) => api.worldContext(world, { include_secrets: false }),
    getThreads: (world) => api.listThreads(world),
    getClocks: (world) => api.listClocks(world),
  });
}

/** Tell the context builder what is open. */
export function useCopilotView(patch: Partial<ViewState>) {
  const { section, worldId, entityRef } = patch;
  useEffect(() => {
    setView({ ...(section !== undefined && { section }), ...(worldId !== undefined && { worldId }), ...(entityRef !== undefined && { entityRef }) });
  }, [section, worldId, entityRef]);
}

/** The entity open in the Bible; cleared when the Bible closes. */
export function useOpenEntity(ref: string | null) {
  useEffect(() => {
    setView({ entityRef: ref });
  }, [ref]);
  useEffect(() => () => setView({ entityRef: null }), []);
}

/** Register how this screen reloads its data in place when the assistant finishes a turn. */
export function useCopilotRefresh(reload: () => unknown) {
  const latest = useRef(reload);
  latest.current = reload;
  useEffect(() => addRefreshHandler(() => latest.current()), []);
}

/** Answer the launcher's context request for an open form. `getFields` returns only what the user changed (null: nothing to say). */
export function useFormSnapshot(kind: string, objectId: string | null, getFields: () => Fields | null) {
  const latest = useRef(getFields);
  latest.current = getFields;
  useEffect(() => {
    const onRequest = (ev: Event) => {
      const provide = (ev as CustomEvent<{ provide?: (s: unknown) => void }>).detail?.provide;
      let fields: Fields | null = null;
      try { fields = latest.current(); } catch { fields = null; }
      if (!provide || !fields) return;
      const shown = publicFields(fields);
      provide({ kind, object_id: objectId, dirty: Object.keys(shown).length > 0, fields: shown });
    };
    window.addEventListener("scheherazade:context-request", onRequest);
    return () => window.removeEventListener("scheherazade:context-request", onRequest);
  }, [kind, objectId]);
}
