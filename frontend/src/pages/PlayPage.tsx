import { useEffect, useState, useCallback } from "react";
import { Dices, Eye, EyeOff, Image as ImageIcon, MapPin, ShieldCheck, Sparkles, Undo2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { Entity, NarrateResult, Session, Turn, TurnRole, World, WorldCheckResult, WorldContextResult } from "../lib/types";
import { Badge, ConfirmButton, ErrorBanner } from "../components/ui";

const QUICK_ROLLS = ["1d20", "2d6", "1d100", "4dF", "1d6"];

// Only the four roles a person types themselves have a mode tab — "roll"
// and "system" turns are written by the app, never chosen from here.
const MODE_LABEL_KEY: Record<"narration" | "action" | "dialogue" | "ooc", "play_mode_narration" | "play_mode_action" | "play_mode_dialogue" | "play_mode_ooc"> = {
  narration: "play_mode_narration", action: "play_mode_action", dialogue: "play_mode_dialogue", ooc: "play_mode_ooc",
};

function turnClass(role: TurnRole, undone: boolean): string {
  return `turn turn-${role}${undone ? " turn-undone" : ""}`;
}

function TurnView({ turn }: { turn: Turn }) {
  if (turn.role === "roll") {
    const roll = turn.rolls?.[0] as { expression?: string; total?: number; natural?: number } | undefined;
    return (
      <div className={turnClass(turn.role, turn.undone)}>
        <Dices size={13} />
        {turn.text} {roll?.total !== undefined ? `→ ${roll.total}` : ""}
      </div>
    );
  }
  return <div className={turnClass(turn.role, turn.undone)}>{turn.text}</div>;
}

const GONE = new Set(["dead", "destroyed", "missing"]);

/** Set the scene by hand — where it is, who is present, the mood — with
 * no model. It is written as a system turn carrying a scene delta, so it
 * is undoable like any other turn and never reaches the chapter. */
function SceneEditor({ world, lang, ctx, onApplied, onCancel }: {
  world: World; lang: Lang; ctx: WorldContextResult | null;
  onApplied: () => Promise<void>; onCancel: () => void;
}) {
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [location, setLocation] = useState(ctx?.scene.location?.ref ?? "");
  const [present, setPresent] = useState<string[]>(ctx?.scene.present.map((e) => e.ref) ?? []);
  const [mood, setMood] = useState(ctx?.scene.mood ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listEntities(world.id).then(setEntities).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [world.id]);

  const places = (entities ?? []).filter((e) => e.kind === "location");
  const cast = (entities ?? []).filter((e) => (e.kind === "character" || e.kind === "creature") && !GONE.has(e.status));

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      const byRef = new Map((entities ?? []).map((e) => [e.ref, e.name]));
      const parts = [
        location ? byRef.get(location) ?? location : t("play_scene_no_location", lang),
        present.map((r) => byRef.get(r) ?? r).join(", "),
        mood.trim(),
      ].filter(Boolean);
      await api.storyAppend(world.id, `${t("play_scene_turn", lang)}: ${parts.join(" · ")}`, {
        role: "system", author: "user", delta: { scene: { location: location || null, present, mood: mood.trim() } },
      });
      await onApplied();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="scene-editor" style={{ marginTop: 8 }}>
      {error && <div style={{ marginBottom: 8 }}><ErrorBanner message={error} /></div>}
      <label className="field-inline">
        <span>{t("play_location", lang)}</span>
        <select value={location} onChange={(e) => setLocation(e.target.value)} aria-label={t("play_location", lang)}>
          <option value="">{t("play_scene_no_location", lang)}</option>
          {places.map((e) => <option key={e.ref} value={e.ref}>{e.name}</option>)}
        </select>
      </label>
      <div className="panel-title" style={{ marginTop: 8 }}>{t("play_present", lang)}</div>
      <div className="scene-cast">
        {cast.map((e) => (
          <label key={e.ref} className="scene-cast-item">
            <input
              type="checkbox"
              checked={present.includes(e.ref)}
              onChange={(ev) => setPresent((p) => ev.target.checked ? [...p, e.ref] : p.filter((r) => r !== e.ref))}
            />
            <span>{e.name}</span>
          </label>
        ))}
      </div>
      <label className="field-inline" style={{ marginTop: 8 }}>
        <span>{t("play_mood", lang)}</span>
        <input value={mood} onChange={(e) => setMood(e.target.value)} aria-label={t("play_mood", lang)} />
      </label>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary btn-sm" disabled={busy || entities === null} onClick={apply}>{t("play_scene_apply", lang)}</button>
        <button className="btn btn-sm" onClick={onCancel}>{t("cancel", lang)}</button>
      </div>
    </div>
  );
}

type DeltaSelection = Record<string, boolean[]>;

function initSelection(delta: Record<string, unknown> | null): DeltaSelection {
  const sel: DeltaSelection = {};
  if (!delta) return sel;
  for (const [key, value] of Object.entries(delta)) {
    if (Array.isArray(value)) sel[key] = value.map(() => true);
  }
  return sel;
}

function itemLabel(category: string, item: unknown): string {
  const obj = item as Record<string, unknown>;
  switch (category) {
    case "new_entities": return `+ ${obj.kind}: ${obj.name}`;
    case "entity_updates": return `~ ${obj.ref}: ${Object.keys(obj).filter((k) => k !== "ref").join(", ")}`;
    case "new_facts": return `fact: ${String(obj.text).slice(0, 80)}`;
    case "relations": return `${obj.a} ${obj.type} ${obj.b}`;
    case "timeline_events": return `${obj.in_world_date ?? ""} ${obj.summary}`;
    case "thread_changes": return `hilo ${obj.ref ?? obj.title}: ${obj.status ?? ""}`;
    case "clock_ticks": return `reloj ${obj.ref}: +${obj.ticks ?? 1}`;
    default: return JSON.stringify(item);
  }
}

export function PlayPage({ world, lang, onWorldChanged }: { world: World; lang: Lang; onWorldChanged: () => void }) {
  const [session, setSession] = useState<Session | null>(null);
  const [turns, setTurns] = useState<Turn[] | null>(null);
  const [ctx, setCtx] = useState<WorldContextResult | null>(null);
  const [gmView, setGmView] = useState(true);
  const [mode, setMode] = useState<TurnRole>("action");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<NarrateResult | null>(null);
  const [selection, setSelection] = useState<DeltaSelection>({});
  const [prospero, setProspero] = useState(false);
  const [diceExpr, setDiceExpr] = useState("1d20");
  const [illustrating, setIllustrating] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const [editingScene, setEditingScene] = useState(false);

  const refresh = useCallback(async () => {
    const [sessions, context] = await Promise.all([
      api.listSessions(world.id),
      api.worldContext(world.id, { include_secrets: gmView }),
    ]);
    const current = sessions[sessions.length - 1] ?? null;
    setSession(current);
    setCtx(context);
    if (current) setTurns(await api.listTurns(world.id, current.id));
    else setTurns([]);
  }, [world.id, gmView]);

  useEffect(() => {
    refresh().catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    api.prosperoAvailable().then((r) => setProspero(r.available)).catch(() => setProspero(false));
  }, [refresh]);

  async function sendTurn(role: TurnRole, text: string) {
    if (!text.trim()) return;
    await api.storyAppend(world.id, text, { role, author: "user" });
    setInput("");
    await refresh();
  }

  async function handleSend() {
    setBusy(true);
    setError(null);
    try {
      await sendTurn(mode, input);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleNarrate() {
    const actionText = input.trim();
    setBusy(true);
    setError(null);
    try {
      if (actionText) await sendTurn(mode, actionText);
      const result = await api.narrate(world.id, actionText || "Continúa la escena.");
      setProposal(result);
      setSelection(initSelection(result.delta));
    } catch (e) {
      if (e instanceof ApiError && e.code === "llm_unavailable") {
        setError(t("play_no_backend", lang));
      } else {
        setError(e instanceof ApiError ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  function buildFilteredDelta(): Record<string, unknown> | null {
    if (!proposal?.delta) return null;
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(proposal.delta)) {
      if (Array.isArray(value)) {
        const keep = value.filter((_, i) => selection[key]?.[i] !== false);
        if (keep.length) out[key] = keep;
      } else if (value) {
        out[key] = value;
      }
    }
    return out;
  }

  async function acceptProposal() {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.storyAppend(world.id, proposal.narration, {
        role: "narration", author: "narrator", delta: buildFilteredDelta(),
      });
      setProposal(null);
      if (result.rejected.length) {
        setError(`${result.rejected.length} ${t("play_rejected_items", lang)}: ${result.rejected.map((r) => r.reason).join("; ")}`);
      }
      await refresh();
      onWorldChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function rejectProposal() {
    setProposal(null);
  }

  async function handleUndo() {
    setBusy(true);
    setError(null);
    try {
      await api.storyUndo(world.id);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function rollQuick(expr: string) {
    try {
      const roll = await api.rollDice(expr, world.id, "", "user");
      await api.storyAppend(world.id, `Tirada ${roll.detail}`, { role: "roll", author: "user", rolls: [{ ...roll }] });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  const [checkText, setCheckText] = useState("");
  const [check, setCheck] = useState<WorldCheckResult | null>(null);
  const [checking, setChecking] = useState(false);

  async function runCheck() {
    if (!checkText.trim()) return;
    setChecking(true);
    setError(null);
    try {
      setCheck(await api.worldCheck(world.id, checkText));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  }

  async function handleIllustrate() {
    if (!ctx) return;
    setIllustrating(true);
    setError(null);
    try {
      const result = await api.illustrate(
        world.id,
        ctx.recent_turns.map((r) => r.text).join(" "),
        ctx.scene.location?.name ?? "",
        ctx.scene.mood,
      );
      setImage(result.image_url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setIllustrating(false);
    }
  }

  return (
    <div className="play-layout">
      <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        {error && <div style={{ marginBottom: 10 }}><ErrorBanner message={error} /></div>}
        {session && (
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>{session.title || session.id}</div>
        )}
        <div className="transcript">
          {turns === null && <p>{t("loading", lang)}</p>}
          {turns && turns.length === 0 && <p style={{ color: "var(--text-muted)" }}>{t("play_empty", lang)}</p>}
          {turns?.map((turn) => <TurnView key={turn.id} turn={turn} />)}
        </div>

        {proposal && (
          <div className="delta-card" style={{ margin: "10px 0" }}>
            <strong>{t("play_proposed_delta", lang)}</strong>
            <p style={{ fontFamily: "var(--font-story)", fontSize: 16 }}>{proposal.narration}</p>
            {proposal.unparsed && <Badge kind="gold">{lang === "es" ? "sin cambios estructurados" : "no structured changes"}</Badge>}
            {Object.entries(proposal.delta ?? {}).map(([category, value]) => {
              if (!Array.isArray(value) || value.length === 0) return null;
              return (
                <div key={category}>
                  {value.map((item, i) => (
                    <label key={i} className="delta-item">
                      <span>{itemLabel(category, item)}</span>
                      <input
                        type="checkbox"
                        checked={selection[category]?.[i] !== false}
                        onChange={(e) => {
                          setSelection((s) => {
                            const arr = [...(s[category] ?? value.map(() => true))];
                            arr[i] = e.target.checked;
                            return { ...s, [category]: arr };
                          });
                        }}
                      />
                    </label>
                  ))}
                </div>
              );
            })}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary btn-sm" disabled={busy} onClick={acceptProposal}>{t("play_accept", lang)}</button>
              <button className="btn btn-sm" disabled={busy} onClick={rejectProposal}>{t("play_reject", lang)}</button>
            </div>
          </div>
        )}

        <div className="play-input-box">
          <div className="mode-tabs">
            {(["narration", "action", "dialogue", "ooc"] as const).map((m) => (
              <button key={m} className={`mode-tab${mode === m ? " active" : ""}`} onClick={() => setMode(m)}>
                {t(MODE_LABEL_KEY[m], lang)}
              </button>
            ))}
          </div>
          <div className="play-input-row">
            <textarea
              placeholder={t("play_input_placeholder", lang)}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <button className="btn" disabled={busy || !input.trim()} onClick={handleSend}>{t("play_send", lang)}</button>
            <button className="btn btn-primary" disabled={busy} onClick={handleNarrate}>
              <Sparkles size={14} /> {busy ? t("play_narrating", lang) : t("play_narrate", lang)}
            </button>
          </div>
        </div>
      </div>

      <div className="side-panel">
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div className="panel-title" style={{ margin: 0 }}>{t("play_scene", lang)}</div>
            <div style={{ display: "flex", gap: 4 }}>
              <button className="icon-button" onClick={() => setEditingScene((v) => !v)} title={t("play_scene_edit", lang)} aria-label={t("play_scene_edit", lang)}>
                <MapPin size={14} />
              </button>
              <button className="icon-button" onClick={() => setGmView((v) => !v)} title={gmView ? t("play_gm_view", lang) : t("play_player_view", lang)}>
                {gmView ? <Eye size={14} /> : <EyeOff size={14} />}
              </button>
            </div>
          </div>
          {ctx && !ctx.scene.location && ctx.scene.present.length === 0 && !ctx.scene.mood && !editingScene && (
            <p style={{ margin: "4px 0", fontSize: 12, color: "var(--text-muted)" }}>{t("play_scene_empty", lang)}</p>
          )}
          {editingScene && (
            <SceneEditor
              world={world} lang={lang} ctx={ctx}
              onCancel={() => setEditingScene(false)}
              onApplied={async () => { setEditingScene(false); await refresh(); onWorldChanged(); }}
            />
          )}
          {ctx?.scene.location && <p style={{ margin: "4px 0" }}><strong>{t("play_location", lang)}:</strong> {ctx.scene.location.name}</p>}
          {ctx?.scene.mood && <p style={{ margin: "4px 0" }}><strong>{t("play_mood", lang)}:</strong> {ctx.scene.mood}</p>}
          <div className="tag-row" style={{ marginTop: 8 }}>
            {ctx?.scene.present.map((e) => (
              <span key={e.ref} className="chip" title={e.summary}>{e.name}</span>
            ))}
          </div>
          {prospero && (
            <button className="btn btn-sm" style={{ marginTop: 10 }} disabled={illustrating} onClick={handleIllustrate}>
              <ImageIcon size={13} /> {t("play_illustrate", lang)}
            </button>
          )}
          {image && <img src={image} alt="" style={{ width: "100%", borderRadius: 8, marginTop: 8 }} />}
        </div>

        <div className="card">
          <div className="panel-title">{t("play_dice_tray", lang)}</div>
          <div className="tag-row" style={{ marginBottom: 8 }}>
            {QUICK_ROLLS.map((expr) => (
              <button key={expr} className="btn btn-sm" onClick={() => rollQuick(expr)}>{expr}</button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <input value={diceExpr} onChange={(e) => setDiceExpr(e.target.value)} />
            <button className="btn btn-sm" onClick={() => rollQuick(diceExpr)}><Dices size={13} /></button>
          </div>
        </div>

        <div className="card">
          <div className="panel-title">{t("play_check", lang)}</div>
          <div style={{ display: "flex", gap: 6 }}>
            <input value={checkText} placeholder={t("play_check_placeholder", lang)}
              onChange={(e) => setCheckText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runCheck(); }} />
            <button className="btn btn-sm" disabled={checking || !checkText.trim()} onClick={runCheck}>
              <ShieldCheck size={13} />
            </button>
          </div>
          {check && (
            <div style={{ fontSize: 12, marginTop: 8 }}>
              {check.consistent ? (
                <Badge kind="accent">{t("play_check_ok", lang)}</Badge>
              ) : (
                check.conflicts.map((c) => (
                  <p key={c.fact_id} style={{ margin: "4px 0" }}>
                    <Badge kind="danger">{c.fact_id}</Badge> {c.why}
                  </p>
                ))
              )}
              <p style={{ margin: "6px 0 0", color: "var(--text-muted)" }}>
                {check.llm_judge === "used" ? t("play_check_judge_used", lang) : t("play_check_judge_off", lang)}
              </p>
            </div>
          )}
        </div>

        {ctx && (ctx.threads.length > 0 || ctx.clocks.length > 0) && (
          <div className="card">
            <div className="panel-title">{lang === "es" ? "Hilos y relojes" : "Threads & clocks"}</div>
            {ctx.threads.map((th) => <div key={th.ref} className="chip" style={{ marginBottom: 4 }}>{th.title}</div>)}
            {ctx.clocks.map((c) => (
              <div key={c.ref} style={{ fontSize: 12, marginTop: 4 }}>{c.name}: {c.filled}/{c.segments}</div>
            ))}
          </div>
        )}

        <ConfirmButton lang={lang} onConfirm={handleUndo} className="btn btn-sm" confirmLabel="play_undo">
          <Undo2 size={13} /> {t("play_undo", lang)}
        </ConfirmButton>
      </div>
    </div>
  );
}
