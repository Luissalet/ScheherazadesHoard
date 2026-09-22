import { useEffect, useState } from "react";
import { RefreshCw, Server } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { BackendStatus } from "../lib/types";
import { Badge, ErrorBanner, Field } from "../components/ui";

export function BackendsPage({ lang }: { lang: Lang }) {
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [llmUrl, setLlmUrl] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [faustusUrl, setFaustusUrl] = useState("");
  const [faustusToken, setFaustusToken] = useState("");

  async function load() {
    try {
      const s = await api.backend();
      setStatus(s);
      setLlmUrl(s.config.llm_url ?? "");
      setLlmModel(s.config.llm_model ?? "");
      setFaustusUrl(s.config.faustus_url ?? "");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function recheck() {
    setBusy(true);
    setError(null);
    try {
      setStatus(await api.recheckBackend());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = {};
      if (llmUrl) body.llm_url = llmUrl;
      if (llmModel) body.llm_model = llmModel;
      if (faustusUrl) body.faustus_url = faustusUrl;
      if (faustusToken) body.faustus_token = faustusToken;
      setStatus(await api.setBackendSettings(body));
      setFaustusToken("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 18, margin: "0 0 16px" }}>{t("backend_title", lang)}</h1>
      {error && <div style={{ marginBottom: 12 }}><ErrorBanner message={error} /></div>}

      <div className="card" style={{ maxWidth: 560, marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div className="panel-title" style={{ margin: 0 }}><Server size={12} /> {t("backend_llm", lang)}</div>
          <button className="icon-button" disabled={busy} onClick={recheck} title={t("backend_recheck", lang)}>
            <RefreshCw size={14} className={busy ? "spin" : ""} />
          </button>
        </div>
        {status === null && <p>{t("loading", lang)}</p>}
        {status && (
          <div>
            <div className="tag-row" style={{ marginBottom: 8 }}>
              <Badge kind={status.llm.state === "resolved" ? "accent" : "danger"}>
                {status.llm.state === "resolved" ? t("backend_state_resolved", lang) : t("backend_state_unavailable", lang)}
              </Badge>
              {status.llm.provider && <Badge>{status.llm.provider}</Badge>}
              {status.llm.model && <Badge kind="gold">{status.llm.model}</Badge>}
            </div>
            {status.llm.url && <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "2px 0" }}>{status.llm.url}</p>}
            {status.llm.state === "unavailable" && status.llm.reason && (
              <p style={{ fontSize: 12, color: "var(--text-muted)" }}>{status.llm.reason}</p>
            )}
          </div>
        )}
      </div>

      <div className="card" style={{ maxWidth: 560 }}>
        <div className="panel-title">{t("backend_manual", lang)}</div>
        <Field label={t("backend_llm_url", lang)}>
          <input value={llmUrl} onChange={(e) => setLlmUrl(e.target.value)} placeholder="http://127.0.0.1:11434" />
        </Field>
        <Field label={t("backend_llm_model", lang)}>
          <input value={llmModel} onChange={(e) => setLlmModel(e.target.value)} placeholder="qwen2.5:14b" />
        </Field>
        <Field label={t("backend_faustus_url", lang)}>
          <input value={faustusUrl} onChange={(e) => setFaustusUrl(e.target.value)} placeholder="http://127.0.0.1:8800" />
        </Field>
        <Field label={t("backend_faustus_token", lang)}>
          <input
            type="password"
            value={faustusToken}
            onChange={(e) => setFaustusToken(e.target.value)}
            placeholder={status?.config.token_set ? t("backend_token_set", lang) : ""}
          />
        </Field>
        <button className="btn btn-primary btn-sm" disabled={busy} onClick={saveSettings}>{t("save", lang)}</button>
      </div>
    </div>
  );
}
