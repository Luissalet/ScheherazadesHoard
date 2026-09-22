import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { api } from "./lib/api";
import { detectLang, persistLang, t, type Lang } from "./lib/i18n";
import type { World } from "./lib/types";

import { WorldsPage } from "./pages/WorldsPage";
import { PlayPage } from "./pages/PlayPage";
import { BiblePage } from "./pages/BiblePage";
import { MapPage } from "./pages/MapPage";
import { TimelinePage } from "./pages/TimelinePage";
import { ThreadsClocksPage } from "./pages/ThreadsClocksPage";
import { TablesPage } from "./pages/TablesPage";
import { SessionsPage } from "./pages/SessionsPage";
import { DiceLogPage } from "./pages/DiceLogPage";
import { BackendsPage } from "./pages/BackendsPage";
import { ActivityPage } from "./pages/ActivityPage";
import { SettingsPage } from "./pages/SettingsPage";

export type Section =
  | "worlds" | "play" | "bible" | "map" | "timeline" | "threads" | "tables"
  | "sessions" | "dice" | "backends" | "activity" | "settings";

export type Theme = "light" | "dark";

function readTheme(): Theme {
  try {
    const stored = localStorage.getItem("scheherazade.theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    /* ignore */
  }
  return "light";
}

function readWorldId(): string | null {
  try {
    return localStorage.getItem("scheherazade.currentWorld");
  } catch {
    return null;
  }
}

export default function App() {
  const [lang, setLang] = useState<Lang>(detectLang);
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [section, setSection] = useState<Section>("worlds");
  const [worlds, setWorlds] = useState<World[] | null>(null);
  const [worldId, setWorldId] = useState<string | null>(readWorldId);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("scheherazade.theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    try {
      if (worldId) localStorage.setItem("scheherazade.currentWorld", worldId);
    } catch {
      /* ignore */
    }
  }, [worldId]);

  const reloadWorlds = () => setRefreshTick((n) => n + 1);

  useEffect(() => {
    let cancelled = false;
    api.listWorlds().then((list) => {
      if (cancelled) return;
      setWorlds(list);
      if (worldId && !list.some((w) => w.id === worldId)) {
        setWorldId(null);
        setSection("worlds");
      }
      if (!worldId && list.length > 0 && section === "worlds") {
        // keep the Worlds page as the landing view; don't auto-select.
      }
    }).catch(() => setWorlds([]));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTick]);

  const currentWorld = worlds?.find((w) => w.id === worldId) ?? null;

  function selectWorld(id: string) {
    setWorldId(id);
    setSection("play");
    setMobileOpen(false);
  }

  function navigate(next: Section) {
    setSection(next);
    setMobileOpen(false);
  }

  function toggleLang() {
    const next: Lang = lang === "es" ? "en" : "es";
    setLang(next);
    persistLang(next);
  }

  const title = (() => {
    if (section === "worlds") return t("nav_worlds", lang);
    if (section === "backends") return t("nav_backends", lang);
    if (section === "activity") return t("nav_activity", lang);
    if (section === "settings") return t("nav_settings", lang);
    return currentWorld ? currentWorld.name : t("appName", lang);
  })();

  return (
    <div className="app-shell">
      <Sidebar
        world={currentWorld}
        section={section}
        onNavigate={navigate}
        lang={lang}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="main-col">
        <Header
          title={title}
          lang={lang}
          onToggleLang={toggleLang}
          theme={theme}
          onSetTheme={setTheme}
          onOpenMobile={() => setMobileOpen(true)}
        />
        <div className="content">
          {section === "worlds" && (
            <WorldsPage worlds={worlds} lang={lang} onSelect={selectWorld} onCreated={reloadWorlds} />
          )}
          {section === "backends" && <BackendsPage lang={lang} />}
          {section === "activity" && <ActivityPage lang={lang} />}
          {section === "settings" && <SettingsPage lang={lang} theme={theme} onSetTheme={setTheme} onSetLang={(l) => { setLang(l); persistLang(l); }} />}

          {currentWorld && section === "play" && <PlayPage world={currentWorld} lang={lang} onWorldChanged={reloadWorlds} />}
          {currentWorld && section === "bible" && <BiblePage world={currentWorld} lang={lang} />}
          {currentWorld && section === "map" && <MapPage world={currentWorld} lang={lang} />}
          {currentWorld && section === "timeline" && <TimelinePage world={currentWorld} lang={lang} />}
          {currentWorld && section === "threads" && <ThreadsClocksPage world={currentWorld} lang={lang} />}
          {currentWorld && section === "tables" && <TablesPage world={currentWorld} lang={lang} />}
          {currentWorld && section === "sessions" && <SessionsPage world={currentWorld} lang={lang} />}
          {currentWorld && section === "dice" && <DiceLogPage world={currentWorld} lang={lang} />}
        </div>
      </div>
    </div>
  );
}
