import type { ReactElement } from "react";
import type { FontSize } from "../../hooks/useUiPrefs";
import type { ThemeMode } from "../../lib/types";

export type AppearanceSectionProps = {
  theme: ThemeMode;
  resolved: "dark" | "light";
  fontSize: FontSize;
  onCycleTheme: () => void;
  onSetTheme: (mode: ThemeMode) => void;
  onSetFontSize: (size: FontSize) => void;
};

export function AppearanceSection({
  theme,
  resolved,
  fontSize,
  onCycleTheme,
  onSetTheme,
  onSetFontSize,
}: AppearanceSectionProps): ReactElement {
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const onThemeSelect = async (next: ThemeMode) => {
    onSetTheme(next);
    try {
      await api?.prefsSet?.({ theme: next });
    } catch {
      /* ignore */
    }
  };

  const onFontSelect = async (next: FontSize) => {
    onSetFontSize(next);
    try {
      await api?.prefsSet?.({ font_size: next });
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="settings-detail">
      <div className="settings-card">
        <h3>主题与字号</h3>
        <label className="field-label">
          Theme
          <select
            value={theme}
            onChange={(e) => void onThemeSelect(e.target.value as ThemeMode)}
          >
            <option value="dark">dark</option>
            <option value="light">light</option>
            <option value="system">system</option>
          </select>
        </label>
        <label className="field-label">
          Font size
          <select
            value={fontSize}
            onChange={(e) => void onFontSelect(e.target.value as FontSize)}
          >
            <option value="small">small</option>
            <option value="medium">medium</option>
            <option value="large">large</option>
          </select>
        </label>
        <div className="empty-actions mt-10">
          <button type="button" className="secondary" onClick={onCycleTheme}>
            循环主题
          </button>
        </div>
        <p className="muted-copy mt-10">
          resolved: {resolved} · ⌘1 Workbench · ⌘2 Evidence · ⌘, Settings
        </p>
      </div>
    </div>
  );
}
