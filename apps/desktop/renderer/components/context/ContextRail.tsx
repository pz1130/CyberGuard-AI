import type { SettingsSection } from "../../lib/types";
import { useI18n } from "../../i18n/I18nProvider";
import { useEnvironment, useRun } from "../../state";
import { Button, Tooltip } from "../../ui";
import "./ContextRail.css";

/**
 * 从时间线事件里数出「发现」——工具返回的高危计数与证据登记数。
 *
 * ⚠️ 高危计数是**正则匹配工具摘要文本**的权宜做法，不严谨：
 * 摘要文案一改就失效，中英文枚举也覆盖不全。
 *
 * 之所以这么写：当前事件流没有结构化的 findings 计数，而右栏「本次调查
 * 的事实」区必须有内容。正确解法要 sidecar 发结构化 finding 事件，属
 * 服务端侧改动。
 *
 * 决策登记在 docs/desktop/11-OPEN-QUESTIONS.md §I，M1.5 自用验证后收敛。
 * **改动工具摘要文案前先看这里** —— 此处与文案有隐式耦合。
 */
function useFindings() {
  const { events } = useRun();
  const evidenceIds: string[] = [];
  let highCount = 0;

  for (const ev of events) {
    if (
      (ev.type === "evidence_register" || ev.type === "evidence_registered") &&
      typeof ev.evidence_id === "string"
    ) {
      evidenceIds.push(ev.evidence_id);
    }
    if (ev.type === "tool_call_end") {
      const text = String(ev.result_preview || ev.summary || "");
      const m = /(\d+)\s*(?:条)?\s*(?:high|critical|高危)/i.exec(text);
      if (m) highCount += Number(m[1]);
    }
  }
  return { evidenceIds, highCount };
}

export type ContextRailProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (s?: SettingsSection) => void;
};

export function ContextRail({
  onViewEvidence,
  onOpenSettings,
}: ContextRailProps) {
  const env = useEnvironment();
  const { evidenceIds, highCount } = useFindings();
  const { t } = useI18n();

  return (
    <aside className="wb-rail ctxrail" aria-label={t("rail.aria")}>
      <div className="ctxrail-head">
        <h2 className="ctxrail-title">{t("rail.title")}</h2>
      </div>

      <div className="ctxrail-body">
        <section className="ctxsec">
          <h3 className="ctxsec-h">{t("rail.findings")}</h3>
          {highCount > 0 ? (
            <p className="ctxsec-stat ctxsec-stat--danger">
              {t("rail.findings.high", { count: highCount })}
            </p>
          ) : (
            <p className="ctxsec-empty">{t("rail.findings.none")}</p>
          )}
        </section>

        <section className="ctxsec">
          <div className="ctxsec-hrow">
            <h3 className="ctxsec-h">{t("rail.evidence")}</h3>
            <Button size="sm" variant="ghost" onClick={() => onViewEvidence()}>
              {t("rail.evidence.all")}
            </Button>
          </div>
          {evidenceIds.length > 0 ? (
            <ul className="ctxsec-list">
              {evidenceIds.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    className="ctxsec-link"
                    onClick={() => onViewEvidence(id)}
                  >
                    {id.slice(0, 12)}…
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ctxsec-empty">
              {t("rail.evidence.inLibrary", { count: env.evidenceCount })}
            </p>
          )}
        </section>

        <section className="ctxsec">
          <div className="ctxsec-hrow">
            <h3 className="ctxsec-h">{t("rail.tools")}</h3>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onOpenSettings("mcp")}
            >
              {t("rail.tools.sources")}
            </Button>
          </div>
          {env.mcpTools.length > 0 ? (
            <ul className="ctxsec-chips">
              {env.mcpTools.map((n) => (
                <li key={n}>
                  <Tooltip content={n}>
                    <span className="ctxsec-chip">
                      {n.replace(/^mcp__/, "").slice(0, 24)}
                    </span>
                  </Tooltip>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ctxsec-empty">{t("rail.tools.none")}</p>
          )}
        </section>
      </div>
    </aside>
  );
}
