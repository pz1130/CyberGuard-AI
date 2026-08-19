import { useEffect, useState, type ReactElement } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import type { SettingsSection } from "../../lib/types";
import { useEnvironment, useUiPrefsCtx } from "../../state";
import { ListRow } from "../../ui";
import { AboutSection } from "./AboutSection";
import { AppearanceSection } from "./AppearanceSection";
import { DataSection } from "./DataSection";
import {
  HUB_GROUPS,
  HubSection,
  hubSectionTitle,
} from "./HubSection";
import { LlmSection } from "./LlmSection";
import { McpSection } from "./McpSection";
import { SkillsSection } from "./SkillsSection";
import { useLlmSection } from "./useLlmSection";
import { useMcpSection } from "./useMcpSection";
import { useSkillsSection } from "./useSkillsSection";
import "./SettingsShell.css";

export type SettingsViewProps = {
  focusSection?: SettingsSection;
  onProviderSaved: (mode: string) => void;
};

export function SettingsShell({
  focusSection,
  onProviderSaved,
}: SettingsViewProps): ReactElement {
  const { t } = useI18n();
  const { theme, fontSize } = useUiPrefsCtx();
  const { providerMode } = useEnvironment();
  const [section, setSection] = useState<SettingsSection>(
    focusSection && focusSection !== "hub" ? focusSection : "hub"
  );

  // Hooks stay mounted on the shell so section switches do not reset editors.
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
      return n
        ? t("settings.hub.mcpCount", { count: n })
        : t("settings.hub.mcpNone");
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

  const title = hubSectionTitle(t, section);

  return (
    <div className="view-pane view-enter settings-shell">
      <nav className="settings-nav" aria-label={t("settings.nav.aria")}>
        <ListRow
          variant="nav"
          active={section === "hub"}
          title={t("settings.nav.overview")}
          onClick={() => setSection("hub")}
        />
        {HUB_GROUPS.map((group) => (
          <div key={group.labelKey}>
            <div className="settings-nav-label">{t(group.labelKey)}</div>
            {group.items.map((item) => (
              <ListRow
                key={item.id}
                variant="nav"
                active={section === item.id}
                title={t(item.titleKey)}
                meta={hubStatus(item.id) || undefined}
                onClick={() => setSection(item.id)}
              />
            ))}
          </div>
        ))}
      </nav>

      <div className="settings-content">
        <div className="settings-content-head">
          <h1>{title}</h1>
          {section === "hub" ? (
            <p className="settings-content-lede">
              {t("settings.hub.lede")}
              <strong>{providerMode}</strong>
            </p>
          ) : null}
        </div>

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

        {section === "appearance" && <AppearanceSection />}

        {section === "data" && <DataSection />}

        {section === "about" && <AboutSection />}
      </div>
    </div>
  );
}
