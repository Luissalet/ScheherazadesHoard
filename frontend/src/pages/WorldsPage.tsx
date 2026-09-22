import { useState } from "react";
import { BookOpen, GitBranch, Plus, Upload, Users } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { Ruleset, World } from "../lib/types";
import { EmptyState, ErrorBanner, Field } from "../components/ui";

export function WorldsPage({
  worlds, lang, onSelect, onCreated,
}: {
  worlds: World[] | null;
  lang: Lang;
  onSelect: (id: string) => void;
  onCreated: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("");
  const [tone, setTone] = useState("");
  const [premise, setPremise] = useState("");
  const [ruleset, setRuleset] = useState<Ruleset>("freeform");
  const [language, setLanguage] = useState(lang);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const world = await api.createWorld({ name, genre, tone, premise, ruleset, language });
      setCreating(false);
      setName(""); setGenre(""); setTone(""); setPremise("");
      onCreated();
      onSelect(world.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const data = JSON.parse(await file.text());
      const world = await api.worldImportJson(data);
      onCreated();
      onSelect(world.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>{t("worlds_title", lang)}</h1>
        {!creating && (
          <div style={{ display: "flex", gap: 8 }}>
            <label className="btn" style={{ cursor: busy ? "default" : "pointer" }}>
              <Upload size={14} /> {t("worlds_import", lang)}
              <input type="file" accept="application/json,.json" hidden disabled={busy}
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importFile(f); }} />
            </label>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <Plus size={14} /> {t("worlds_new", lang)}
            </button>
          </div>
        )}
      </div>
      {!creating && error && <div style={{ marginBottom: 12 }}><ErrorBanner message={error} /></div>}

      {creating && (
        <div className="card" style={{ marginBottom: 16, maxWidth: 480 }}>
          <Field label={t("world_name", lang)}>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </Field>
          <Field label={t("world_genre", lang)}>
            <input value={genre} onChange={(e) => setGenre(e.target.value)} />
          </Field>
          <Field label={t("world_tone", lang)}>
            <input value={tone} onChange={(e) => setTone(e.target.value)} />
          </Field>
          <Field label={t("world_premise", lang)}>
            <textarea rows={3} value={premise} onChange={(e) => setPremise(e.target.value)} />
          </Field>
          <Field label={t("world_ruleset", lang)}>
            <select value={ruleset} onChange={(e) => setRuleset(e.target.value as Ruleset)}>
              <option value="freeform">freeform</option>
              <option value="d20">d20</option>
              <option value="pbta_2d6">pbta_2d6</option>
            </select>
          </Field>
          <Field label={t("world_language", lang)}>
            <select value={language} onChange={(e) => setLanguage(e.target.value as Lang)}>
              <option value="es">Español</option>
              <option value="en">English</option>
            </select>
          </Field>
          {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" disabled={busy || !name.trim()} onClick={submit}>
              {t("create", lang)}
            </button>
            <button className="btn" onClick={() => setCreating(false)}>{t("cancel", lang)}</button>
          </div>
        </div>
      )}

      {worlds === null && <p>{t("loading", lang)}</p>}

      {worlds && worlds.length === 0 && !creating && (
        <EmptyState icon={<BookOpen size={28} />}>{t("worlds_empty", lang)}</EmptyState>
      )}

      {worlds && worlds.length > 0 && (
        <div className="grid grid-cards">
          {worlds.map((w) => (
            <div key={w.id} className="card">
              <h3 style={{ margin: "0 0 4px", fontSize: 15 }}>{w.name}</h3>
              <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--text-muted)" }}>
                {[w.genre, w.tone].filter(Boolean).join(" · ") || w.ruleset}
              </p>
              {w.counts && (
                <div className="tag-row" style={{ marginBottom: 12 }}>
                  <span className="badge" title={t(w.counts.entities === 1 ? "worlds_entity_one" : "worlds_entity_many", lang)}>
                    <Users size={11} /> {w.counts.entities} {t(w.counts.entities === 1 ? "worlds_entity_one" : "worlds_entity_many", lang)}
                  </span>
                  <span className="badge badge-gold" title={t(w.counts.open_threads === 1 ? "worlds_open_thread_one" : "worlds_open_thread_many", lang)}>
                    <GitBranch size={11} /> {w.counts.open_threads} {t(w.counts.open_threads === 1 ? "worlds_open_thread_one" : "worlds_open_thread_many", lang)}
                  </span>
                  <span className="badge">{w.counts.sessions} {t(w.counts.sessions === 1 ? "worlds_session_one" : "worlds_session_many", lang)}</span>
                  <span className="badge">{w.ruleset}</span>
                </div>
              )}
              <button className="btn btn-primary btn-sm" onClick={() => onSelect(w.id)}>
                {t("worlds_open", lang)}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
