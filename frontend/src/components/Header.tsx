import { Languages, Menu, Moon, Sun } from "lucide-react";
import type { Lang } from "../lib/i18n";
import type { Theme } from "../App";

export function Header({
  title, lang, onToggleLang, theme, onSetTheme, onOpenMobile,
}: {
  title: string;
  lang: Lang;
  onToggleLang: () => void;
  theme: Theme;
  onSetTheme: (t: Theme) => void;
  onOpenMobile: () => void;
}) {
  const nextTheme = theme === "dark" ? "light" : "dark";
  return (
    <header className="header">
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button className="icon-button mobile-only" onClick={onOpenMobile} aria-label="menu" style={{ display: "none" }}>
          <Menu size={16} />
        </button>
        <div className="header-title">{title}</div>
      </div>
      <div className="header-actions">
        <button className="icon-button" onClick={onToggleLang} title={lang === "es" ? "English" : "Español"}>
          <Languages size={16} />
        </button>
        <button className="icon-button" onClick={() => onSetTheme(nextTheme)} title={nextTheme}>
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  );
}
