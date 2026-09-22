import { useEffect, useState } from "react";
import { Dices, Plus, Table as TableIcon } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { RandomTable, World } from "../lib/types";
import { EmptyState, ErrorBanner, Field } from "../components/ui";

export function TablesPage({ world, lang }: { world: World; lang: Lang }) {
  const [tables, setTables] = useState<RandomTable[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [entriesText, setEntriesText] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setTables(await api.listTables(world.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    setTables(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.id]);

  async function submit() {
    const entries = entriesText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((text) => ({ text }));
    if (!name.trim() || entries.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await api.createTable(world.id, name, entries);
      setName("");
      setEntriesText("");
      setCreating(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function roll(table: RandomTable) {
    try {
      const result = await api.rollTable(world.id, table.name);
      setResults((r) => ({ ...r, [table.id]: result.text }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>{t("nav_tables", lang)}</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setCreating((v) => !v)}>
          <Plus size={14} /> {t("tables_new", lang)}
        </button>
      </div>

      {creating && (
        <div className="card" style={{ marginBottom: 16, maxWidth: 480 }}>
          <Field label={t("world_name", lang)}>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </Field>
          <Field label={lang === "es" ? "Entradas (una por línea)" : "Entries (one per line)"}>
            <textarea rows={6} value={entriesText} onChange={(e) => setEntriesText(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" disabled={busy || !name.trim()} onClick={submit}>{t("create", lang)}</button>
            <button className="btn btn-sm" onClick={() => setCreating(false)}>{t("cancel", lang)}</button>
          </div>
        </div>
      )}

      {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}
      {tables === null && <p>{t("loading", lang)}</p>}
      {tables && tables.length === 0 && <EmptyState icon={<TableIcon size={28} />}>{t("tables_empty", lang)}</EmptyState>}

      {tables && tables.length > 0 && (
        <div className="grid grid-cards">
          {tables.map((table) => (
            <div key={table.id} className="card">
              <strong style={{ fontSize: 14 }}>{table.name}</strong>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 10px" }}>
                {table.entries.length} {lang === "es" ? "entradas" : "entries"}
              </p>
              <button className="btn btn-sm" onClick={() => roll(table)}>
                <Dices size={13} /> {t("tables_roll", lang)}
              </button>
              {results[table.id] && (
                <p style={{ marginTop: 10, fontFamily: "var(--font-story)", fontSize: 15 }}>{results[table.id]}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
