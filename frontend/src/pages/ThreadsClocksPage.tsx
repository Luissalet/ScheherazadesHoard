import { useEffect, useState } from "react";
import { Clock as ClockIcon, Plus } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { Clock, Thread, ThreadStatus, World } from "../lib/types";
import { Badge, EmptyState, ErrorBanner, Field } from "../components/ui";

const STATUSES: ThreadStatus[] = ["open", "advanced", "resolved", "abandoned"];

function statusKind(status: ThreadStatus): "default" | "accent" | "gold" | "danger" {
  if (status === "open") return "accent";
  if (status === "advanced") return "gold";
  if (status === "resolved") return "default";
  return "danger";
}

function ClockRing({ clock }: { clock: Clock }) {
  const size = 44;
  const r = 16;
  const cx = size / 2;
  const cy = size / 2;
  const segments = Array.from({ length: clock.segments }, (_, i) => i);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {segments.map((i) => {
        const start = (2 * Math.PI * i) / clock.segments - Math.PI / 2;
        const end = (2 * Math.PI * (i + 1)) / clock.segments - Math.PI / 2;
        const x1 = cx + r * Math.cos(start);
        const y1 = cy + r * Math.sin(start);
        const x2 = cx + r * Math.cos(end);
        const y2 = cy + r * Math.sin(end);
        const large = end - start > Math.PI ? 1 : 0;
        const filled = i < clock.filled;
        return (
          <path
            key={i}
            d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`}
            fill={filled ? "var(--accent)" : "var(--bg-sunken)"}
            stroke="var(--border)"
            strokeWidth={1}
          />
        );
      })}
    </svg>
  );
}

export function ThreadsClocksPage({ world, lang }: { world: World; lang: Lang }) {
  const [threads, setThreads] = useState<Thread[] | null>(null);
  const [clocks, setClocks] = useState<Clock[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [addingThread, setAddingThread] = useState(false);
  const [threadTitle, setThreadTitle] = useState("");
  const [addingClock, setAddingClock] = useState(false);
  const [clockName, setClockName] = useState("");
  const [clockSegments, setClockSegments] = useState(4);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [t1, c1] = await Promise.all([api.listThreads(world.id), api.listClocks(world.id)]);
      setThreads(t1);
      setClocks(c1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    setThreads(null);
    setClocks(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.id]);

  async function submitThread() {
    if (!threadTitle.trim()) return;
    setBusy(true);
    try {
      await api.createThread(world.id, threadTitle);
      setThreadTitle("");
      setAddingThread(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submitClock() {
    if (!clockName.trim()) return;
    setBusy(true);
    try {
      await api.createClock(world.id, clockName, clockSegments);
      setClockName("");
      setAddingClock(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(thread: Thread, status: ThreadStatus) {
    try {
      await api.updateThread(world.id, thread.ref, status);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function tick(clock: Clock, amount: number) {
    try {
      await api.tickClock(world.id, clock.ref, amount);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div>
      {error && <div style={{ marginBottom: 12 }}><ErrorBanner message={error} /></div>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>{t("nav_threads", lang)}</h1>
      </div>

      {threads === null && <p>{t("loading", lang)}</p>}
      {threads && threads.length === 0 && !addingThread && (
        <EmptyState icon={<ClockIcon size={28} />}>{t("threads_empty", lang)}</EmptyState>
      )}

      {threads && (
        <div className="kanban" style={{ marginBottom: 24 }}>
          {STATUSES.map((status) => (
            <div key={status} className="kanban-col">
              <div className="panel-title"><Badge kind={statusKind(status)}>{t(`status_${status}`, lang)}</Badge></div>
              {threads.filter((th) => th.status === status).length === 0 && (
                <div className="kanban-empty">{t("kanban_empty", lang)}</div>
              )}
              {threads.filter((th) => th.status === status).map((th) => (
                <div key={th.id} className="card">
                  <strong style={{ fontSize: 13 }}>{th.title}</strong>
                  {th.notes && <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0" }}>{th.notes}</p>}
                  <div className="tag-row" style={{ marginTop: 6 }}>
                    {STATUSES.filter((s) => s !== status).map((s) => (
                      <button key={s} className="btn btn-sm" onClick={() => changeStatus(th, s)}>→ {t(`status_${s}`, lang)}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {addingThread ? (
        <div className="card" style={{ marginBottom: 24, maxWidth: 420 }}>
          <Field label={t("thread_title", lang)}>
            <input value={threadTitle} onChange={(e) => setThreadTitle(e.target.value)} autoFocus />
          </Field>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" disabled={busy || !threadTitle.trim()} onClick={submitThread}>{t("create", lang)}</button>
            <button className="btn btn-sm" onClick={() => setAddingThread(false)}>{t("cancel", lang)}</button>
          </div>
        </div>
      ) : (
        <button className="btn btn-sm" style={{ marginBottom: 24 }} onClick={() => setAddingThread(true)}>
          <Plus size={14} /> {t("threads_new", lang)}
        </button>
      )}

      <h1 style={{ fontSize: 18, margin: "0 0 12px" }}>{lang === "es" ? "Relojes" : "Clocks"}</h1>
      {clocks === null && <p>{t("loading", lang)}</p>}
      {clocks && clocks.length === 0 && !addingClock && (
        <EmptyState icon={<ClockIcon size={28} />}>{t("clocks_empty", lang)}</EmptyState>
      )}

      {clocks && clocks.length > 0 && (
        <div className="grid grid-cards" style={{ marginBottom: 16 }}>
          {clocks.map((c) => (
            <div key={c.id} className="card" style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <ClockRing clock={c} />
              <div style={{ flex: 1 }}>
                <strong style={{ fontSize: 13 }}>{c.name}</strong>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {c.filled}/{c.segments} {c.full && <Badge kind="danger">{lang === "es" ? "completo" : "full"}</Badge>}
                </div>
                <div className="tag-row" style={{ marginTop: 6 }}>
                  <button className="btn btn-sm" onClick={() => tick(c, 1)}>+1</button>
                  <button className="btn btn-sm" onClick={() => tick(c, -1)}>-1</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {addingClock ? (
        <div className="card" style={{ maxWidth: 420 }}>
          <Field label={t("world_name", lang)}>
            <input value={clockName} onChange={(e) => setClockName(e.target.value)} autoFocus />
          </Field>
          <Field label={lang === "es" ? "Segmentos" : "Segments"}>
            <input type="number" min={2} max={12} value={clockSegments} onChange={(e) => setClockSegments(Number(e.target.value))} />
          </Field>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" disabled={busy || !clockName.trim()} onClick={submitClock}>{t("create", lang)}</button>
            <button className="btn btn-sm" onClick={() => setAddingClock(false)}>{t("cancel", lang)}</button>
          </div>
        </div>
      ) : (
        <button className="btn btn-sm" onClick={() => setAddingClock(true)}>
          <Plus size={14} /> {t("clocks_new", lang)}
        </button>
      )}
    </div>
  );
}
