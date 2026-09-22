import {
  Activity, BookOpen, Clock, Dices, Feather, Globe, ListTree,
  Network, Server, Settings, Table as TableIcon, Users, X,
} from "lucide-react";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { World } from "../lib/types";
import type { Section } from "../App";

export function Sidebar({
  world, section, onNavigate, lang, mobileOpen, onCloseMobile,
}: {
  world: World | null;
  section: Section;
  onNavigate: (s: Section) => void;
  lang: Lang;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const worldItems: { id: Section; icon: typeof BookOpen; label: string }[] = [
    { id: "play", icon: Feather, label: t("nav_play", lang) },
    { id: "bible", icon: BookOpen, label: t("nav_bible", lang) },
    { id: "map", icon: Network, label: t("nav_map", lang) },
    { id: "timeline", icon: ListTree, label: t("nav_timeline", lang) },
    { id: "threads", icon: Clock, label: t("nav_threads", lang) },
    { id: "tables", icon: TableIcon, label: t("nav_tables", lang) },
    { id: "sessions", icon: Users, label: t("nav_sessions", lang) },
    { id: "dice", icon: Dices, label: t("nav_dice", lang) },
  ];
  const globalItems: { id: Section; icon: typeof BookOpen; label: string }[] = [
    { id: "worlds", icon: Globe, label: t("nav_worlds", lang) },
    { id: "backends", icon: Server, label: t("nav_backends", lang) },
    { id: "activity", icon: Activity, label: t("nav_activity", lang) },
    { id: "settings", icon: Settings, label: t("nav_settings", lang) },
  ];

  return (
    <nav className={`sidebar${mobileOpen ? " open" : ""}`}>
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <Feather size={16} />
        </div>
        <div className="sidebar-brand-name">{t("appName", lang)}</div>
        <button className="icon-button sidebar-close" style={{ marginLeft: "auto" }} onClick={onCloseMobile} aria-label="close">
          <X size={16} />
        </button>
      </div>

      {world && (
        <>
          <div className="sidebar-section-label">{world.name}</div>
          {worldItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item${section === item.id ? " active" : ""}`}
              onClick={() => onNavigate(item.id)}
            >
              <item.icon size={16} />
              {item.label}
            </button>
          ))}
        </>
      )}

      <div className="sidebar-section-label">{lang === "es" ? "General" : "Global"}</div>
      {globalItems.map((item) => (
        <button
          key={item.id}
          className={`nav-item${section === item.id ? " active" : ""}`}
          onClick={() => onNavigate(item.id)}
        >
          <item.icon size={16} />
          {item.label}
        </button>
      ))}
    </nav>
  );
}
