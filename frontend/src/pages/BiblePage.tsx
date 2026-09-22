import { useEffect, useMemo, useState } from "react";
import { BookOpen, Eye, EyeOff, Lock, Pencil, Plus, Search } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { DictKey, Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { Entity, EntityKind, EntityStatus, World } from "../lib/types";
import { Badge, EmptyState, ErrorBanner, Field } from "../components/ui";

const KINDS: EntityKind[] = ["character", "location", "faction", "item", "lore", "creature"];

const STATUSES: EntityStatus[] = ["alive", "dead", "missing", "destroyed", "active", "unknown"];

function kindLabel(kind: EntityKind, lang: Lang): string {
  return t(`bible_kind_${kind}` as DictKey, lang);
}

export function statusLabel(status: EntityStatus, lang: Lang): string {
  return STATUSES.includes(status) ? t(`entity_status_${status}` as DictKey, lang) : status;
}

const splitList = (text: string) => text.split(",").map((x) => x.trim()).filter(Boolean);

type EditDraft = {
  name: string; status: EntityStatus; summary: string; description: string;
  aliases: string; tags: string; secrets: string;
};

function draftOf(e: Entity): EditDraft {
  return {
    name: e.name, status: e.status, summary: e.summary, description: e.description,
    aliases: e.aliases.join(", "), tags: e.tags.join(", "), secrets: e.secrets ?? "",
  };
}

/** Edit an existing entity by hand: the same PATCH route the agent's
 * entity_upsert ends in, so a person can fix what the model got wrong. */
function EntityEditForm({ world, entity, lang, withSecrets, onSaved, onCancel }: {
  world: World; entity: Entity; lang: Lang; withSecrets: boolean;
  onSaved: (e: Entity) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState<EditDraft>(() => draftOf(entity));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof EditDraft) => (ev: { target: { value: string } }) =>
    setDraft((d) => ({ ...d, [key]: ev.target.value }));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Partial<Entity> = {
        name: draft.name, status: draft.status, summary: draft.summary, description: draft.description,
        aliases: splitList(draft.aliases), tags: splitList(draft.tags),
      };
      if (withSecrets) body.secrets = draft.secrets;
      onSaved(await api.patchEntity(world.id, entity.ref, body));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="entity-edit" onSubmit={(ev) => { ev.preventDefault(); save(); }}>
      {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}
      <Field label={t("world_name", lang)}>
        <input value={draft.name} onChange={set("name")} autoFocus />
      </Field>
      <Field label={t("bible_field_status", lang)}>
        <select value={draft.status} onChange={set("status")}>
          {STATUSES.map((st) => <option key={st} value={st}>{statusLabel(st, lang)}</option>)}
        </select>
      </Field>
      <Field label={t("bible_field_summary", lang)}>
        <textarea rows={2} value={draft.summary} onChange={set("summary")} />
      </Field>
      <Field label={t("bible_field_description", lang)}>
        <textarea rows={4} value={draft.description} onChange={set("description")} />
      </Field>
      <Field label={t("bible_field_aliases", lang)}>
        <input value={draft.aliases} onChange={set("aliases")} />
      </Field>
      <Field label={t("bible_field_tags", lang)}>
        <input value={draft.tags} onChange={set("tags")} />
      </Field>
      {withSecrets && (
        <Field label={t("bible_secrets", lang)}>
          <textarea rows={2} value={draft.secrets} onChange={set("secrets")} />
        </Field>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !draft.name.trim()}>{t("save", lang)}</button>
        <button type="button" className="btn btn-sm" onClick={onCancel}>{t("cancel", lang)}</button>
      </div>
    </form>
  );
}

export function BiblePage({ world, lang }: { world: World; lang: Lang }) {
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
  const [detail, setDetail] = useState<Entity | null>(null);
  const [showSecrets, setShowSecrets] = useState(false);
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<EntityKind | "all">("all");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newKind, setNewKind] = useState<EntityKind>("character");
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  async function loadList() {
    try {
      const list = await api.listEntities(world.id);
      setEntities(list);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    setEntities(null);
    setSelectedRef(null);
    setDetail(null);
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.id]);

  useEffect(() => {
    setEditing(false);
    if (!selectedRef) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api.getEntity(world.id, selectedRef, showSecrets).then((e) => {
      if (!cancelled) setDetail(e);
    }).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [world.id, selectedRef, showSecrets]);

  const filtered = useMemo(() => {
    if (!entities) return [];
    // accent- and case-insensitive, like the server's search ("corazon" finds "Corazón")
    const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
    const q = fold(search.trim());
    return entities.filter((e) => {
      if (kindFilter !== "all" && e.kind !== kindFilter) return false;
      if (!q) return true;
      return [e.name, e.summary, ...e.aliases, ...e.tags].some((text) => fold(text).includes(q));
    });
  }, [entities, search, kindFilter]);

  async function submitCreate() {
    if (!newName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createEntity(world.id, { kind: newKind, name: newName });
      setNewName("");
      setCreating(false);
      await loadList();
      setSelectedRef(created.ref);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bible-layout">
      <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <div style={{ position: "relative", flex: 1 }}>
            <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
            <input
              style={{ paddingLeft: 26, width: "100%" }}
              placeholder={t("bible_search", lang)}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button className="icon-button" title={t("bible_new_entity", lang)} onClick={() => setCreating((v) => !v)}>
            <Plus size={16} />
          </button>
        </div>

        <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value as EntityKind | "all")} style={{ marginBottom: 8 }}>
          <option value="all">{lang === "es" ? "Todas las clases" : "All kinds"}</option>
          {KINDS.map((k) => <option key={k} value={k}>{kindLabel(k, lang)}</option>)}
        </select>

        {creating && (
          <div className="card" style={{ marginBottom: 8 }}>
            <Field label={t("world_name", lang)}>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} autoFocus />
            </Field>
            <Field label={lang === "es" ? "Clase" : "Kind"}>
              <select value={newKind} onChange={(e) => setNewKind(e.target.value as EntityKind)}>
                {KINDS.map((k) => <option key={k} value={k}>{kindLabel(k, lang)}</option>)}
              </select>
            </Field>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary btn-sm" disabled={busy || !newName.trim()} onClick={submitCreate}>{t("create", lang)}</button>
              <button className="btn btn-sm" onClick={() => setCreating(false)}>{t("cancel", lang)}</button>
            </div>
          </div>
        )}

        {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}

        {entities === null && <p>{t("loading", lang)}</p>}
        {entities && entities.length === 0 && (
          <EmptyState icon={<BookOpen size={28} />}>{t("bible_empty", lang)}</EmptyState>
        )}

        <div className="entity-list">
          {filtered.map((e) => (
            <button
              key={e.ref}
              className={`entity-list-item${selectedRef === e.ref ? " active" : ""}`}
              onClick={() => setSelectedRef(e.ref)}
            >
              <strong style={{ fontSize: 13 }}>{e.name}</strong>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{kindLabel(e.kind, lang)} · {e.ref}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="card" style={{ overflowY: "auto" }}>
        {!detail && <EmptyState icon={<BookOpen size={28} />}>{lang === "es" ? "Selecciona una entidad." : "Select an entity."}</EmptyState>}
        {detail && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <h2 style={{ margin: "0 0 4px" }}>{detail.name}</h2>
                <div className="tag-row">
                  <Badge>{kindLabel(detail.kind, lang)}</Badge>
                  <Badge kind="accent">{detail.ref}</Badge>
                  {detail.status !== "unknown" && <Badge kind={detail.status === "dead" || detail.status === "missing" ? "danger" : "gold"}>{statusLabel(detail.status, lang)}</Badge>}
                </div>
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                <button className="icon-button" onClick={() => setEditing((v) => !v)} title={t("bible_edit", lang)} aria-label={t("bible_edit", lang)}>
                  <Pencil size={15} />
                </button>
                <button className="icon-button" onClick={() => setShowSecrets((v) => !v)} title={t("bible_show_secrets", lang)} aria-label={t("bible_show_secrets", lang)}>
                  {showSecrets ? <Eye size={16} /> : <EyeOff size={16} />}
                </button>
              </div>
            </div>

            {editing && (
              <EntityEditForm
                key={detail.ref + String(showSecrets)}
                world={world} entity={detail} lang={lang} withSecrets={showSecrets}
                onCancel={() => setEditing(false)}
                onSaved={async (saved) => {
                  setEditing(false);
                  await loadList();
                  setDetail(await api.getEntity(world.id, saved.ref, showSecrets));
                }}
              />
            )}

            {detail.aliases.length > 0 && (
              <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{detail.aliases.join(", ")}</p>
            )}
            {detail.summary && <p style={{ fontFamily: "var(--font-story)", fontSize: 16 }}>{detail.summary}</p>}
            {detail.description && <p>{detail.description}</p>}

            {detail.tags.length > 0 && (
              <div className="tag-row" style={{ margin: "8px 0" }}>
                {detail.tags.map((tag) => <span key={tag} className="chip">{tag}</span>)}
              </div>
            )}

            {showSecrets && detail.secrets && (
              <div className="card" style={{ background: "var(--bg-sunken)", marginTop: 12 }}>
                <div className="panel-title"><Lock size={11} /> {t("bible_secrets", lang)}</div>
                <p style={{ margin: 0 }}>{detail.secrets}</p>
              </div>
            )}

            {detail.relations && detail.relations.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="panel-title">{t("bible_relations", lang)}</div>
                {detail.relations.map((r) => (
                  <div key={r.id} style={{ fontSize: 13, marginBottom: 4 }}>
                    {/* read as a sentence: "Marisol trusts Tomás" / "Tomás protects Marisol" */}
                    {r.direction === "out" ? (
                      <>{detail.name} <em>{r.type}</em> <button className="link-button" onClick={() => setSelectedRef(r.other_ref ?? r.other_id)}>{r.other_name}</button></>
                    ) : (
                      <><button className="link-button" onClick={() => setSelectedRef(r.other_ref ?? r.other_id)}>{r.other_name}</button> <em>{r.type}</em> {detail.name}</>
                    )}
                    {r.note && <span style={{ color: "var(--text-muted)" }}> ({r.note})</span>}
                  </div>
                ))}
              </div>
            )}

            {detail.facts && detail.facts.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="panel-title">{t("bible_facts", lang)}</div>
                {detail.facts.map((f) => (
                  <div key={f.id} style={{ fontSize: 13, marginBottom: 6 }}>
                    {f.canon && <Badge kind="gold">canon</Badge>} {f.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
