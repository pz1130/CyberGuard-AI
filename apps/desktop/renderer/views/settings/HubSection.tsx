import type { ReactElement } from "react";
import type { SettingsSection } from "../../lib/types";
import { Card, ListRow } from "../../ui";

const HUB_GROUPS: {
  label: string;
  items: {
    id: Exclude<SettingsSection, "hub">;
    title: string;
    desc: string;
    badge: string;
  }[];
}[] = [
  {
    label: "核心",
    items: [
      {
        id: "llm",
        title: "语言模型",
        desc: "云厂商 / 本地 Ollama · LM Studio · vLLM",
        badge: "LLM",
      },
      {
        id: "mcp",
        title: "数据源 MCP",
        desc: "告警 JSON/CSV、stdio 连接器",
        badge: "MCP",
      },
    ],
  },
  {
    label: "工作流",
    items: [
      {
        id: "skills",
        title: "技能 SOP",
        desc: "内置分诊 / CVE / 取证 等 catalog",
        badge: "Skills",
      },
    ],
  },
  {
    label: "偏好",
    items: [
      {
        id: "appearance",
        title: "外观",
        desc: "主题与字号",
        badge: "UI",
      },
      {
        id: "data",
        title: "数据与安全",
        desc: "加密导出 · 卸载",
        badge: "Data",
      },
      {
        id: "about",
        title: "关于",
        desc: "版本与开发版声明",
        badge: "Info",
      },
    ],
  },
];

const HUB_ITEMS = HUB_GROUPS.flatMap((g) => g.items);

export { HUB_GROUPS, HUB_ITEMS };

export type HubSectionProps = {
  providerMode: string;
  hubStatus: (id: Exclude<SettingsSection, "hub">) => string | null;
  onSelect: (id: Exclude<SettingsSection, "hub">) => void;
};

export function HubSection({
  providerMode,
  hubStatus,
  onSelect,
}: HubSectionProps): ReactElement {
  return (
    <div className="settings-detail">
      {HUB_GROUPS.map((group) => (
        <Card key={group.label}>
          <h3 className="settings-card-title">{group.label}</h3>
          <div className="settings-list" role="list">
            {group.items.map((t) => {
              const status = hubStatus(t.id);
              const metaParts = [t.desc];
              if (status) {
                const liveHint =
                  t.id === "llm" && providerMode === "live"
                    ? status
                    : t.id === "llm" && providerMode === "mock"
                      ? status
                      : status;
                metaParts.push(liveHint);
              }
              return (
                <ListRow
                  key={t.id}
                  title={`${t.title} · ${t.badge}`}
                  meta={metaParts.join(" · ")}
                  onClick={() => onSelect(t.id)}
                />
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}
