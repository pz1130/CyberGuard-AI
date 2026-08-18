import type { ReactElement } from "react";
import type { SettingsSection } from "../../lib/types";

const HUB_GROUPS: {
  label: string;
  items: {
    id: Exclude<SettingsSection, "hub">;
    title: string;
    desc: string;
    badge: string;
    /** Optional glyph inside the leading mark */
    mark: string;
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
        mark: "AI",
      },
      {
        id: "mcp",
        title: "数据源 MCP",
        desc: "告警 JSON/CSV、stdio 连接器",
        badge: "MCP",
        mark: "MC",
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
        mark: "SK",
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
        mark: "Aa",
      },
      {
        id: "data",
        title: "数据与安全",
        desc: "加密导出 · 卸载",
        badge: "Data",
        mark: "DB",
      },
      {
        id: "about",
        title: "关于",
        desc: "版本与开发版声明",
        badge: "Info",
        mark: "i",
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
    <div className="settings-hub">
      {HUB_GROUPS.map((group) => (
        <section key={group.label} className="settings-hub-group">
          <h2 className="settings-hub-group-label">{group.label}</h2>
          <div className="settings-hub-list" role="list">
            {group.items.map((t) => {
              const status = hubStatus(t.id);
              return (
                <button
                  key={t.id}
                  type="button"
                  className="settings-row"
                  role="listitem"
                  onClick={() => onSelect(t.id)}
                >
                  <span className="settings-row-mark" aria-hidden>
                    {t.mark}
                  </span>
                  <span className="settings-row-body">
                    <span className="settings-row-title-line">
                      <span className="settings-row-title">{t.title}</span>
                      <span className="settings-row-badge">{t.badge}</span>
                    </span>
                    <span className="settings-row-desc">{t.desc}</span>
                  </span>
                  {status ? (
                    <span
                      className={`settings-row-status${
                        t.id === "llm" && providerMode === "live"
                          ? " is-live"
                          : t.id === "llm" && providerMode === "mock"
                            ? " is-mock"
                            : ""
                      }`}
                    >
                      {status}
                    </span>
                  ) : null}
                  <span className="settings-row-chevron" aria-hidden>
                    ›
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
