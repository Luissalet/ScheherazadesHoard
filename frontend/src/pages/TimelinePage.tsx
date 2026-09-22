import { useEffect, useState } from "react";
import { ListTree, Plus } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { TimelineEvent, World } from "../lib/types";
import { Badge, EmptyState, ErrorBanner, Field } from "../components/ui";

export function TimelinePage({ world, lang }: { world: World; lang: Lang }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [summary, setSummary] = useState("");
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const list = await api.listTimeline(world.id);
      setEvents([...list].sort((a, b) => a.created_at - b.created_at));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    setEvents(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.id]);

  async function submit() {
    if (!summary.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createTimelineEvent(world.id, summary, date);
      setSummary("");
      setDate("");
      setCreating(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>{t("nav_timeline", lang)}</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setCreating((v) => !v)}>
          <Plus size={14} /> {t("create", lang)}
        </button>
      </div>

      {creating && (
        <div className="card" style={{ marginBottom: 16, maxWidth: 480 }}>
          <Field label={lang === "es" ? "Fecha en el mundo" : "In-world date"}>
            <input value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label={lang === "es" ? "Resumen" : "Summary"}>
            <textarea rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} autoFocus />
          </Field>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" disabled={busy || !summary.trim()} onClick={submit}>{t("create", lang)}</button>
            <button className="btn btn-sm" onClick={() => setCreating(false)}>{t("cancel", lang)}</button>
          </div>
        </div>
      )}

      {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}
      {events === null && <p>{t("loading", lang)}</p>}
      {events && events.length === 0 && <EmptyState icon={<ListTree size={28} />}>{t("timeline_empty", lang)}</EmptyState>}

      {events && events.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 720 }}>
          {events.map((ev) => (
            <div key={ev.id} className="card" style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              {ev.in_world_date && <Badge kind="gold">{ev.in_world_date}</Badge>}
              <p style={{ margin: 0 }}>{ev.summary}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
