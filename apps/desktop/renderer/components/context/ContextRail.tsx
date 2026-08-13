import type { SettingsSection } from "../../lib/types";
import { useEnvironment, useRun } from "../../state";
import { Button, Tooltip } from "../../ui";
import { StatusBar } from "./StatusBar";
import "./ContextRail.css";

/** 从时间线事件里数出「发现」——工具返回的高危计数与证据登记数 */
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

  return (
    <div className="wb-rail ctxrail">
      <header className="ctxrail-head">
        <h2 className="ctxrail-title">本次调查</h2>
      </header>

      <div className="ctxrail-body">
        <section className="ctxsec">
          <h3 className="ctxsec-h">发现</h3>
          {highCount > 0 ? (
            <p className="ctxsec-stat ctxsec-stat--danger">{highCount} 条高危</p>
          ) : (
            <p className="ctxsec-empty">尚无</p>
          )}
        </section>

        <section className="ctxsec">
          <div className="ctxsec-hrow">
            <h3 className="ctxsec-h">证据</h3>
            <Button size="sm" variant="ghost" onClick={() => onViewEvidence()}>
              全部
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
            <p className="ctxsec-empty">本轮未登记 · 库中 {env.evidenceCount} 件</p>
          )}
        </section>

        <section className="ctxsec">
          <div className="ctxsec-hrow">
            <h3 className="ctxsec-h">工具</h3>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onOpenSettings("mcp")}
            >
              数据源
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
            <p className="ctxsec-empty">未发现 · 可选</p>
          )}
        </section>
      </div>

      <StatusBar onOpenSettings={onOpenSettings} />
    </div>
  );
}
