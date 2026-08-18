import { useEffect, useState, type ReactElement } from "react";
import type { FontSize } from "../../hooks/useUiPrefs";
import type { SettingsSection, ThemeMode } from "../../lib/types";
import { AboutSection } from "./AboutSection";
import { AppearanceSection } from "./AppearanceSection";
import { DataSection } from "./DataSection";
import { HUB_ITEMS, HubSection } from "./HubSection";
import { LlmSection } from "./LlmSection";
import { McpSection } from "./McpSection";
import { SkillsSection } from "./SkillsSection";
import { useLlmSection } from "./useLlmSection";
import { useMcpSection } from "./useMcpSection";
import { useSkillsSection } from "./useSkillsSection";

export type SettingsViewProps = {
  theme: ThemeMode;
  resolved: "dark" | "light";
  fontSize: FontSize;
  providerMode: string;
  dataRoot: string;
  onCycleTheme: () => void;
  onSetTheme: (mode: ThemeMode) => void;
  onSetFontSize: (size: FontSize) => void;
  focusSection?: SettingsSection;
  onProviderSaved?: (mode: string) => void;
};

export function SettingsShell({
  theme,
  resolved,
  fontSize,
  providerMode,
  dataRoot,
  onCycleTheme,
  onSetTheme,
  onSetFontSize,
  focusSection,
  onProviderSaved,
}: SettingsViewProps): ReactElement {
  const [section, setSection] = useState<SettingsSection>(
    focusSection && focusSection !== "hub" ? focusSection : "hub"
  );

  // Hooks stay mounted on the shell so hub↔detail does not reset editors.
  const llm = useLlmSection(onProviderSaved);
  const mcp = useMcpSection();
  const skills = useSkillsSection();

  useEffect(() => {
    if (focusSection) {
      setSection(focusSection);
    }
  }, [focusSection]);

  const hubStatus = (id: Exclude<SettingsSection, "hub">): string | null => {
    if (id === "llm") return providerMode || "—";
    if (id === "mcp") {
      const n = mcp.servers.length;
      return n ? `${n} 台` : "未配置";
    }
    if (id === "skills") {
      const n = skills.skills.length;
      return n ? `${n}` : null;
    }
    if (id === "appearance") {
      return `${theme} · ${fontSize}`;
    }
    return null;
  };

  const header =
    section === "hub" ? (
      <div className="settings-hub-header">
        <h1>设置</h1>
        <p className="lede">
          选择一项进入配置。当前 LLM：
          <strong className="settings-hub-mode">{providerMode}</strong>
        </p>
      </div>
    ) : (
      <div className="settings-detail-head">
        <button
          type="button"
          className="ghost-btn settings-back"
          onClick={() => setSection("hub")}
        >
          ← 全部设置
        </button>
        <h1>
          {HUB_ITEMS.find((t) => t.id === section)?.title || "设置"}
        </h1>
      </div>
    );

  return (
    <div className="view-pane view-enter settings-view">
      {header}

      {section === "hub" && (
        <HubSection
          providerMode={providerMode}
          hubStatus={hubStatus}
          onSelect={(id) => setSection(id)}
        />
      )}

      {section === "llm" && <LlmSection {...llm} />}

      {section === "mcp" && <McpSection {...mcp} />}

      {section === "skills" && <SkillsSection {...skills} />}

      {section === "appearance" && (
        <AppearanceSection
          theme={theme}
          resolved={resolved}
          fontSize={fontSize}
          onCycleTheme={onCycleTheme}
          onSetTheme={onSetTheme}
          onSetFontSize={onSetFontSize}
        />
      )}

      {section === "data" && <DataSection dataRoot={dataRoot} />}

      {section === "about" && <AboutSection />}
    </div>
  );
}
