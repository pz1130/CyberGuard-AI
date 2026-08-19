import type { ReactElement } from "react";
import { useI18n, type TFunc } from "../../i18n/I18nProvider";
import type { SettingsSection } from "../../lib/types";
import { Card, ListRow } from "../../ui";

type HubItem = {
  id: Exclude<SettingsSection, "hub">;
  titleKey: string;
  descKey: string;
  badge: string;
};

type HubGroup = { labelKey: string; items: HubItem[] };

const HUB_GROUPS_DEF: HubGroup[] = [
  {
    labelKey: "settings.group.core",
    items: [
      {
        id: "llm",
        titleKey: "settings.section.llm",
        descKey: "settings.section.llm.desc",
        badge: "LLM",
      },
      {
        id: "mcp",
        titleKey: "settings.section.mcp",
        descKey: "settings.section.mcp.desc",
        badge: "MCP",
      },
    ],
  },
  {
    labelKey: "settings.group.workflow",
    items: [
      {
        id: "skills",
        titleKey: "settings.section.skills",
        descKey: "settings.section.skills.desc",
        badge: "Skills",
      },
    ],
  },
  {
    labelKey: "settings.group.prefs",
    items: [
      {
        id: "appearance",
        titleKey: "settings.section.appearance",
        descKey: "settings.section.appearance.desc",
        badge: "UI",
      },
      {
        id: "data",
        titleKey: "settings.section.data",
        descKey: "settings.section.data.desc",
        badge: "Data",
      },
      {
        id: "about",
        titleKey: "settings.section.about",
        descKey: "settings.section.about.desc",
        badge: "Info",
      },
    ],
  },
];

const HUB_ITEMS = HUB_GROUPS_DEF.flatMap((g) => g.items);

export { HUB_GROUPS_DEF as HUB_GROUPS, HUB_ITEMS };

export function hubSectionTitle(t: TFunc, section: SettingsSection): string {
  if (section === "hub") return t("settings.title");
  const item = HUB_ITEMS.find((x) => x.id === section);
  return item ? t(item.titleKey) : t("settings.title");
}

export type HubSectionProps = {
  providerMode: string;
  hubStatus: (id: Exclude<SettingsSection, "hub">) => string | null;
  onSelect: (id: Exclude<SettingsSection, "hub">) => void;
};

export function HubSection({
  hubStatus,
  onSelect,
}: HubSectionProps): ReactElement {
  const { t } = useI18n();

  return (
    <div className="settings-detail">
      {HUB_GROUPS_DEF.map((group) => (
        <Card key={group.labelKey}>
          <h3 className="settings-card-title">{t(group.labelKey)}</h3>
          <div className="settings-list" role="list">
            {group.items.map((item) => {
              const status = hubStatus(item.id);
              const metaParts = [t(item.descKey)];
              if (status) metaParts.push(status);
              return (
                <ListRow
                  key={item.id}
                  title={`${t(item.titleKey)} · ${item.badge}`}
                  meta={metaParts.join(" · ")}
                  onClick={() => onSelect(item.id)}
                />
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}
