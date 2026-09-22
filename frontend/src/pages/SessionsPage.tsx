import { useEffect, useState } from "react";
import { Check, Download, Pencil, Plus, Sparkles, Users, X } from "lucide-react";
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

  function reload() {
    setSessions(null);
    return api.listSessions(world.id)
      .then((list) => setSessions([...list].sort((a, b) => b.started_at - a.started_at)))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.id]);

  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  async function createSession() {
    setBusy("new-session");
    setError(null);
    try {
      await api.startSession(world.id, newTitle.trim());
      setNewTitle("");
      setCreating(false);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function startRename(s: Session) {
    setRenamingId(s.id);
    setRenameValue(s.title || "");
  }

  async function saveRename(id: string) {
    if (!renameValue.trim()) return;
    setBusy(`${id}:rename`);
    setError(null);
    try {
      await api.renameSession(world.id, id, renameValue.trim());
      setRenamingId(null);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

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
          <button className="btn btn-sm btn-primary" disabled={busy === "new-session"} onClick={() => setCreating((v) => !v)}>
            <Plus size={13} /> {t("sessions_new", lang)}
          </button>
          <button className="btn btn-sm" disabled={busy === "bible"} onClick={exportBible}>
            <Download size={13} /> {t("export_bible", lang)}
          </button>
          <button className="btn btn-sm" disabled={busy === "world-json"} onClick={exportWorldJson}>
            <Download size={13} /> {t("export_json", lang)}
          </button>
        </div>
      </div>

      {creating && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <input
            autoFocus
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder={t("sessions_new_title_placeholder", lang)}
            onKeyDown={(e) => e.key === "Enter" && createSession()}
            style={{ flex: 1 }}
          />
          <button className="btn btn-sm btn-primary" disabled={busy === "new-session"} onClick={createSession}>
            <Check size={13} />
          </button>
          <button className="btn btn-sm" onClick={() => { setCreating(false); setNewTitle(""); }}>
            <X size={13} />
          </button>
        </div>
      )}

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
                <td>
                  {renamingId === s.id ? (
                    <div style={{ display: "flex", gap: 6 }}>
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && saveRename(s.id)}
                        style={{ flex: 1 }}
                        aria-label={t("sessions_rename_title", lang)}
                      />
                      <button className="icon-button" disabled={busy === `${s.id}:rename`} onClick={() => saveRename(s.id)}>
                        <Check size={13} />
                      </button>
                      <button className="icon-button" onClick={() => setRenamingId(null)}>
                        <X size={13} />
                      </button>
                    </div>
                  ) : (
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {s.title || s.id}
                      <button
                        className="icon-button"
                        title={t("sessions_rename", lang)}
                        aria-label={t("sessions_rename", lang)}
                        onClick={() => startRename(s)}
                      >
                        <Pencil size={12} />
                      </button>
                    </span>
                  )}
                </td>
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
