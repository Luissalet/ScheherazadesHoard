import { useEffect, useState } from "react";
import { Download, Sparkles, Users } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { Session, World } from "../lib/types";
import { EmptyState, ErrorBanner } from "../components/ui";

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function SessionsPage({ world, lang }: { world: World; lang: Lang }) {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setSessions(null);
    api.listSessions(world.id)
      .then((list) => setSessions([...list].sort((a, b) => b.started_at - a.started_at)))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [world.id]);

  const [notice, setNotice] = useState<string | null>(null);

  async function exportChapter(session: Session, polish = false) {
    setBusy(polish ? `${session.id}:polish` : session.id);
    setNotice(null);
    setError(null);
    try {
      const result = await api.chapter(world.id, session.id, polish);
      downloadText(`${session.title || session.id}${result.polished ? " (pulido)" : ""}.md`, result.text);
      // Say plainly when the model was not used, and why.
      if (polish && !result.polished) setNotice(`${t("export_polish_fallback", lang)}: ${result.reason}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function exportBible() {
    setBusy("bible");
    try {
      window.open(api.bibleMdUrl(world.id, false), "_blank");
    } finally {
      setBusy(null);
    }
  }

  async function exportWorldJson() {
    setBusy("world-json");
    try {
      const data = await api.worldExportJson(world.id);
      downloadJson(`${world.name || world.id}.json`, data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>{t("nav_sessions", lang)}</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-sm" disabled={busy === "bible"} onClick={exportBible}>
            <Download size={13} /> {t("export_bible", lang)}
          </button>
          <button className="btn btn-sm" disabled={busy === "world-json"} onClick={exportWorldJson}>
            <Download size={13} /> {t("export_json", lang)}
          </button>
        </div>
      </div>

      {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}
      {notice && <p className="notice" style={{ marginBottom: 8 }}>{notice}</p>}
      {sessions === null && <p>{t("loading", lang)}</p>}
      {sessions && sessions.length === 0 && <EmptyState icon={<Users size={28} />}>{t("sessions_empty", lang)}</EmptyState>}

      {sessions && sessions.length > 0 && (
        <table className="simple">
          <thead>
            <tr>
              <th>{lang === "es" ? "Título" : "Title"}</th>
              <th>{lang === "es" ? "Inicio" : "Started"}</th>
              <th>{lang === "es" ? "Fin" : "Ended"}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>{s.title || s.id}</td>
                <td>{new Date(s.started_at * 1000).toLocaleString(lang === "es" ? "es-ES" : "en-US")}</td>
                <td>{s.ended_at ? new Date(s.ended_at * 1000).toLocaleString(lang === "es" ? "es-ES" : "en-US") : "—"}</td>
                <td>
                  <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                    <button className="btn btn-sm" disabled={busy === s.id} onClick={() => exportChapter(s)}>
                      <Download size={13} /> {t("export_chapter", lang)}
                    </button>
                    <button className="btn btn-sm" disabled={busy === `${s.id}:polish`} onClick={() => exportChapter(s, true)}
                      title={t("export_polish", lang)}>
                      <Sparkles size={13} className={busy === `${s.id}:polish` ? "spin" : ""} /> {t("export_polish", lang)}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
