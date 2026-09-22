import { useEffect, useState } from "react";
import { Dices } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { DiceLogEntry, World } from "../lib/types";
import { EmptyState, ErrorBanner, Field } from "../components/ui";

export function DiceLogPage({ world, lang }: { world: World; lang: Lang }) {
  const [entries, setEntries] = useState<DiceLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expr, setExpr] = useState("1d20");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setEntries(await api.listDiceLog(world.id, 50));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    setEntries(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world.id]);

  async function roll() {
    if (!expr.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.rollDice(expr, world.id, reason, "user");
      setReason("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 18, margin: "0 0 16px" }}>{t("nav_dice", lang)}</h1>

      <div className="card" style={{ marginBottom: 16, maxWidth: 480 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <Field label={t("dice_expression", lang)}>
            <input value={expr} onChange={(e) => setExpr(e.target.value)} />
          </Field>
          <Field label={t("dice_reason", lang)}>
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
        <button className="btn btn-primary btn-sm" disabled={busy || !expr.trim()} onClick={roll}>
          <Dices size={13} /> {t("dice_roll_button", lang)}
        </button>
      </div>

      {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}
      {entries === null && <p>{t("loading", lang)}</p>}
      {entries && entries.length === 0 && <EmptyState icon={<Dices size={28} />}>{t("dice_empty", lang)}</EmptyState>}

      {entries && entries.length > 0 && (
        <table className="simple">
          <thead>
            <tr>
              <th>{lang === "es" ? "Expresión" : "Expression"}</th>
              <th>{lang === "es" ? "Resultado" : "Result"}</th>
              <th>{lang === "es" ? "Motivo" : "Reason"}</th>
              <th>{lang === "es" ? "Quién" : "Who"}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{e.expression}</td>
                <td>{e.result}</td>
                <td>{e.reason || "—"}</td>
                <td>{e.who}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
