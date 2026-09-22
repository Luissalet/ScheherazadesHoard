import { useEffect, useState } from "react";
import { Activity as ActivityIcon } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { AgentCall } from "../lib/types";
import { Badge, EmptyState, ErrorBanner } from "../components/ui";

export function ActivityPage({ lang }: { lang: Lang }) {
  const [calls, setCalls] = useState<AgentCall[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.agentCalls(100)
      .then((list) => setCalls([...list].sort((a, b) => b.created_at - a.created_at)))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 18, margin: "0 0 16px" }}>{t("nav_activity", lang)}</h1>
      {error && <div style={{ marginBottom: 12 }}><ErrorBanner message={error} /></div>}
      {calls === null && <p>{t("loading", lang)}</p>}
      {calls && calls.length === 0 && <EmptyState icon={<ActivityIcon size={28} />}>{t("activity_empty", lang)}</EmptyState>}

      {calls && calls.length > 0 && (
        <table className="simple">
          <thead>
            <tr>
              <th>{lang === "es" ? "Hora" : "Time"}</th>
              <th>{t("activity_tool", lang)}</th>
              <th>{lang === "es" ? "Argumentos" : "Arguments"}</th>
              <th>{t("activity_duration", lang)}</th>
              <th>{t("activity_result", lang)}</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.id}>
                <td>{new Date(c.created_at * 1000).toLocaleTimeString(lang === "es" ? "es-ES" : "en-US")}</td>
                <td>{c.tool}</td>
                <td style={{ fontSize: 11, color: "var(--text-muted)" }}>{c.args_summary}</td>
                <td>{Math.round(c.duration_ms)} ms</td>
                <td>
                  {c.ok ? <Badge kind="accent">{t("activity_ok", lang)}</Badge> : <Badge kind="danger">{t("activity_error", lang)}</Badge>}
                  {c.error && <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 6 }}>{c.error}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
