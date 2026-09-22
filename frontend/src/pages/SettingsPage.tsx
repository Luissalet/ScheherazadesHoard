import { Moon, Sun } from "lucide-react";
import type { Theme } from "../App";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import { Field } from "../components/ui";

export function SettingsPage({
  lang, theme, onSetTheme, onSetLang,
}: {
  lang: Lang;
  theme: Theme;
  onSetTheme: (t: Theme) => void;
  onSetLang: (l: Lang) => void;
}) {
  return (
    <div>
      <h1 style={{ fontSize: 18, margin: "0 0 16px" }}>{t("settings_title", lang)}</h1>

      <div className="card" style={{ maxWidth: 420 }}>
        <Field label={t("settings_theme", lang)}>
          <div className="tag-row">
            <button className={`btn btn-sm${theme === "light" ? " btn-primary" : ""}`} onClick={() => onSetTheme("light")}>
              <Sun size={13} /> {t("settings_theme_light", lang)}
            </button>
            <button className={`btn btn-sm${theme === "dark" ? " btn-primary" : ""}`} onClick={() => onSetTheme("dark")}>
              <Moon size={13} /> {t("settings_theme_dark", lang)}
            </button>
          </div>
        </Field>

        <Field label={t("settings_language", lang)}>
          <select value={lang} onChange={(e) => onSetLang(e.target.value as Lang)}>
            <option value="es">Español</option>
            <option value="en">English</option>
          </select>
        </Field>
      </div>
    </div>
  );
}
