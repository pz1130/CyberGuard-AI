import type { ReactElement } from "react";
import type { Language } from "../../i18n/I18nProvider";
import { useI18n } from "../../i18n/I18nProvider";
import type { FontSize } from "../../hooks/useUiPrefs";
import type { ThemeMode } from "../../lib/types";
import { useUiPrefsCtx } from "../../state";
import { Button, Card, Field, Select } from "../../ui";

export function AppearanceSection(): ReactElement {
  const { t } = useI18n();
  const {
    theme,
    resolved,
    fontSize,
    setTheme,
    setFontSize,
    cycleTheme,
    language,
    setLanguage,
  } = useUiPrefsCtx();
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const onThemeSelect = async (next: ThemeMode) => {
    setTheme(next);
    try {
      await api?.prefsSet?.({ theme: next });
    } catch {
      /* ignore */
    }
  };

  const onFontSelect = async (next: FontSize) => {
    setFontSize(next);
    try {
      await api?.prefsSet?.({ font_size: next });
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">{t("settings.appearance.title")}</h3>
        <Field label={t("settings.appearance.theme")}>
          <Select
            ariaLabel={t("settings.appearance.theme")}
            value={theme}
            onChange={(v) => void onThemeSelect(v)}
            options={[
              { value: "dark", label: "dark" },
              { value: "light", label: "light" },
              { value: "system", label: "system" },
            ]}
          />
        </Field>
        <Field label={t("settings.appearance.fontSize")}>
          <Select
            ariaLabel={t("settings.appearance.fontSize")}
            value={fontSize}
            onChange={(v) => void onFontSelect(v)}
            options={[
              { value: "small", label: "small" },
              { value: "medium", label: "medium" },
              { value: "large", label: "large" },
            ]}
          />
        </Field>
        <Field label={t("settings.appearance.language")}>
          <Select
            ariaLabel={t("settings.appearance.language")}
            value={language}
            onChange={(v) => setLanguage(v as Language)}
            options={[
              // 语言名用母语写法，两端 locale 词条相同，不随界面语言翻
              { value: "zh", label: t("settings.appearance.langZh") },
              { value: "en", label: t("settings.appearance.langEn") },
              {
                value: "system",
                label: t("settings.appearance.followSystem"),
              },
            ]}
          />
        </Field>
        <div className="settings-actions">
          <Button variant="secondary" onClick={cycleTheme}>
            {t("settings.appearance.cycleTheme")}
          </Button>
        </div>
        <p className="settings-hint" style={{ marginTop: "var(--sp-3)" }}>
          {t("settings.appearance.hint", { resolved })}
        </p>
      </Card>
    </div>
  );
}
