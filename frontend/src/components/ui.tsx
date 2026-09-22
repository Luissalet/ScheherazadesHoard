import { useState, type ReactNode } from "react";
import type { Lang } from "../lib/i18n";
import { t, type DictKey } from "../lib/i18n";

export function Spinner() {
  return <span className="spinner" role="status" aria-label="loading" />;
}

export function EmptyState({ icon, children, action }: { icon?: ReactNode; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-state">
      {icon}
      <p>{children}</p>
      {action}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return <div className="error-banner">{message}</div>;
}

export function Badge({ children, kind = "default" }: { children: ReactNode; kind?: "default" | "accent" | "gold" | "danger" }) {
  const cls = kind === "default" ? "badge" : `badge badge-${kind}`;
  return <span className={cls}>{children}</span>;
}

/**
 * A "two-step" inline confirmation: the button becomes a confirm/cancel
 * pair on first click, and only fires on the second click. Never uses
 * window.confirm/alert, which block the page (and any browser automation driving it).
 */
export function ConfirmButton({
  onConfirm, children, lang, className = "btn btn-danger btn-sm", confirmLabel,
}: {
  onConfirm: () => void;
  children: ReactNode;
  lang: Lang;
  className?: string;
  confirmLabel?: DictKey;
}) {
  const [confirming, setConfirming] = useState(false);
  if (confirming) {
    return (
      <span className="two-step-confirm">
        <button
          className="btn btn-danger btn-sm"
          onClick={() => {
            setConfirming(false);
            onConfirm();
          }}
        >
          {confirmLabel ? t(confirmLabel, lang) : t("delete_confirm", lang)}
        </button>
        <button className="btn btn-sm" onClick={() => setConfirming(false)}>
          {t("cancel", lang)}
        </button>
      </span>
    );
  }
  return (
    <button className={className} onClick={() => setConfirming(true)}>
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}
