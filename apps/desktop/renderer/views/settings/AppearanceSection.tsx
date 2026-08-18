import type { ReactElement } from "react";
import type { FontSize } from "../../hooks/useUiPrefs";
import type { ThemeMode } from "../../lib/types";
import { useUiPrefsCtx } from "../../state";
import { Button, Card, Field, Select } from "../../ui";

export function AppearanceSection(): ReactElement {
  const { theme, resolved, fontSize, setTheme, setFontSize, cycleTheme } =
    useUiPrefsCtx();
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
        <h3 className="settings-card-title">主题与字号</h3>
        <Field label="Theme">
          <Select
            ariaLabel="Theme"
            value={theme}
            onChange={(v) => void onThemeSelect(v)}
            options={[
              { value: "dark", label: "dark" },
              { value: "light", label: "light" },
              { value: "system", label: "system" },
            ]}
          />
        </Field>
        <Field label="Font size">
          <Select
            ariaLabel="Font size"
            value={fontSize}
            onChange={(v) => void onFontSelect(v)}
            options={[
              { value: "small", label: "small" },
              { value: "medium", label: "medium" },
              { value: "large", label: "large" },
            ]}
          />
        </Field>
        <div className="settings-actions">
          <Button variant="secondary" onClick={cycleTheme}>
            循环主题
          </Button>
        </div>
        <p className="settings-hint" style={{ marginTop: "var(--sp-3)" }}>
          resolved: {resolved} · ⌘1 Workbench · ⌘2 Evidence · ⌘, Settings
        </p>
      </Card>
    </div>
  );
}
