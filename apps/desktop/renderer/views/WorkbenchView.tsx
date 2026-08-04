import { useEffect, useRef, useState } from "react";
import { DataPanel } from "../components/DataPanel";
import { EmptyState, SAMPLE_TASKS } from "../components/EmptyState";
import { EventCard } from "../components/EventCard";
import { Markdown } from "../components/Markdown";
import { SessionList } from "../components/SessionList";
import type { Caps, Ev, SessionRow, Tier } from "../lib/types";

type Props = {
  sessions: SessionRow[];
  sessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewInvestigation: () => void;
  onDeleteSession?: (id: string) => void;
  events: Ev[];
  streamText: string;
  streaming: boolean;
  lastSubmitted: string | null;
  onViewEvidence?: (evidenceId?: string) => void;
  task: string;
  onTaskChange: (v: string) => void;
  onRun: () => void;
  onAbort: () => void;
  onResume?: () => void;
  running: boolean;
  runId: string | null;
  pausedRunId: string | null;
  runStatus: string;
  tier: Tier;
  onTierChange: (t: Tier) => void;
  steerText: string;
  onSteerTextChange: (v: string) => void;
  onSteer: () => void;
  caps: Caps | null;
  dataRoot: string;
  mcpTools: string[];
  hasApi: boolean;
  providerMode: string;
  onOpenSettingsLlm: () => void;
  onOpenSettingsMcp: () => void;
  showDataPanel: boolean;
  onToggleDataPanel: () => void;
  exportPass: string;
  onExportPass: (v: string) => void;
  exportBusy: boolean;
  exportMsg: string | null;
  onExport: () => void;
  exportAvailable: boolean;
  uninstallBusy: boolean;
  uninstallPreview: string | null;
  onUninstallInventory: () => void;
  onUninstallDryRun: () => void;
  onUninstallExecute: () => void;
};

export function WorkbenchView(props: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSteer, setShowSteer] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [props.events, props.streamText]);

  const paused =
    props.runStatus === "已暂停" || props.runStatus === "paused";

  return (
    <div className="workbench view-enter">
      <SessionList
        sessions={props.sessions}
        sessionId={props.sessionId}
        onSelect={props.onSelectSession}
        onNew={props.onNewInvestigation}
        onDelete={props.onDeleteSession}
      />

      <div className="col col-main">
        <div className="col-head">
          <h2>调查</h2>
          <div className="col-head-pills">
            {props.running && <span className="pill ok">运行中</span>}
            {paused && <span className="pill warn">已暂停</span>}
            {!props.running && !paused && props.events.length > 0 && (
              <span className="pill">空闲</span>
            )}
          </div>
        </div>

        <div className="col-body timeline-wrap">
          {paused && (
            <div className="inline-alert warn">
              <span>
                已暂停
                {props.pausedRunId
                  ? ` · ${props.pausedRunId.slice(0, 8)}`
                  : ""}
              </span>
              {props.onResume ? (
                <button
                  type="button"
                  className="primary"
                  onClick={() => void props.onResume?.()}
                >
                  继续
                </button>
              ) : null}
            </div>
          )}

          <div className="timeline">
            {props.events.length === 0 && !props.streaming && (
              <EmptyState
                onOpenSettingsLlm={props.onOpenSettingsLlm}
                onOpenSettingsMcp={props.onOpenSettingsMcp}
                onFillSample={(text) => props.onTaskChange(text)}
                providerMode={props.providerMode}
                mcpToolCount={props.mcpTools.length}
              />
            )}
            {props.events.map((ev, i) => (
              <EventCard
                key={i}
                ev={ev}
                onViewEvidence={props.onViewEvidence}
              />
            ))}
            {(props.streaming || props.streamText) && (
              <div className="ev type-stream report">
                <div className="ev-label">
                  {props.streaming ? "流式输出" : "草稿"}
                  {props.streaming ? (
                    <span className="stream-cursor" aria-hidden>
                      ▍
                    </span>
                  ) : null}
                </div>
                {props.streamText ? (
                  <Markdown text={props.streamText} />
                ) : (
                  <div className="ev-meta">等待首包…</div>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="composer">
          {!props.task.trim() && props.events.length > 0 && (
            <div className="sample-chips sample-chips-composer">
              {SAMPLE_TASKS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="sample-chip"
                  disabled={props.running}
                  onClick={() => props.onTaskChange(s.text)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}
          <textarea
            value={props.task}
            onChange={(e) => props.onTaskChange(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                void props.onRun();
              }
            }}
            placeholder="描述任务… 例如：分诊 high/critical 告警，给出优先级与建议动作"
            disabled={props.running}
            rows={3}
          />
          <div className="composer-bar">
            <select
              value={props.tier}
              onChange={(e) => props.onTierChange(e.target.value as Tier)}
              disabled={props.running}
              title="能力档位"
            >
              <option value="readonly">只读</option>
              <option value="full">完整</option>
            </select>
            <button
              className="primary"
              type="button"
              onClick={() => void props.onRun()}
              disabled={!props.hasApi || props.running || !props.task.trim()}
            >
              {props.running ? "运行中…" : "运行"}
            </button>
            <button
              className="secondary"
              type="button"
              onClick={() => void props.onAbort()}
              disabled={!props.running || !props.runId}
            >
              中止
            </button>
            <button
              type="button"
              className="ghost-btn"
              onClick={() => setShowSteer((v) => !v)}
              disabled={!props.running || !props.runId}
            >
              中途补充
            </button>
            <span className="composer-hint">⌘↵ 运行</span>
          </div>
          {showSteer && (
            <div className="row steer-row">
              <input
                className="steer-input"
                value={props.steerText}
                onChange={(e) => props.onSteerTextChange(e.target.value)}
                placeholder="运行中途补充说明…"
                disabled={!props.running || !props.runId}
              />
              <button
                className="secondary"
                type="button"
                onClick={() => void props.onSteer()}
                disabled={
                  !props.running || !props.runId || !props.steerText.trim()
                }
              >
                发送
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="col col-context">
        <div className="col-head">
          <h2>本轮</h2>
        </div>
        <div className="col-body">
          <div className="ready-card">
            <div className="ready-card-title">演示就绪</div>
            <button
              type="button"
              className={`ready-row${
                props.providerMode === "live" ? " ok" : " warn"
              }`}
              onClick={props.onOpenSettingsLlm}
            >
              <span>LLM</span>
              <span className="ready-val">
                {props.providerMode === "live" ? "live ✓" : "mock · 配置"}
              </span>
            </button>
            <button
              type="button"
              className={`ready-row${
                props.mcpTools.length > 0 ? " ok" : ""
              }`}
              onClick={props.onOpenSettingsMcp}
            >
              <span>MCP</span>
              <span className="ready-val">
                {props.mcpTools.length > 0
                  ? `${props.mcpTools.length} tools ✓`
                  : "未发现 · 可选"}
              </span>
            </button>
            <div className="ready-row static">
              <span>档位</span>
              <span className="ready-val">
                {props.tier === "readonly" ? "只读" : "完整"}
              </span>
            </div>
            <div className="ready-row static">
              <span>状态</span>
              <span className="ready-val">{props.runStatus || "空闲"}</span>
            </div>
          </div>

          {props.mcpTools.length > 0 && (
            <div className="context-section mt-12">
              <div className="context-h">本轮工具</div>
              <div className="tool-chips">
                {props.mcpTools.map((n) => (
                  <span key={n} className="pill mono-xs" title={n}>
                    {n.replace(/^mcp__/, "").slice(0, 28)}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="context-actions mt-12">
            {props.onViewEvidence ? (
              <button
                type="button"
                className="secondary context-full-btn"
                onClick={() => props.onViewEvidence?.()}
              >
                查看证据
              </button>
            ) : null}
            <button
              type="button"
              className="secondary context-full-btn"
              onClick={props.onOpenSettingsMcp}
            >
              数据源
            </button>
            <button
              type="button"
              className="secondary context-full-btn"
              onClick={props.onOpenSettingsLlm}
            >
              语言模型
            </button>
          </div>

          <button
            type="button"
            className="ghost-btn advanced-toggle"
            onClick={() => setShowAdvanced((v) => !v)}
          >
            {showAdvanced ? "▾ 调试信息" : "▸ 调试信息"}
          </button>
          {showAdvanced && (
            <div className="context-advanced">
              <div className="kv">
                <span>read</span>
                <span>
                  {props.caps?.has_read ? "yes" : "no"}
                  {props.caps?.real_read ? " · real" : ""}
                </span>
                <span>exec/edit</span>
                <span>
                  {props.caps?.has_exec ? "exec" : "—"}/
                  {props.caps?.has_edit ? "edit" : "—"}
                </span>
                <span>run_id</span>
                <span className="mono-xs">{props.runId ?? "—"}</span>
                <span>session</span>
                <span className="mono-xs">
                  {props.sessionId
                    ? `${props.sessionId.slice(0, 10)}…`
                    : "—"}
                </span>
                <span>data_root</span>
                <span className="mono-xs" title={props.dataRoot}>
                  …/{props.dataRoot.split("/").slice(-2).join("/") || "—"}
                </span>
              </div>
            </div>
          )}

          {props.showDataPanel && (
            <DataPanel
              open={true}
              onToggle={props.onToggleDataPanel}
              exportPass={props.exportPass}
              onExportPass={props.onExportPass}
              exportBusy={props.exportBusy}
              exportMsg={props.exportMsg}
              onExport={props.onExport}
              exportAvailable={props.exportAvailable}
              uninstallBusy={props.uninstallBusy}
              uninstallPreview={props.uninstallPreview}
              onInventory={props.onUninstallInventory}
              onDryRun={props.onUninstallDryRun}
              onExecute={props.onUninstallExecute}
            />
          )}
        </div>
      </div>
    </div>
  );
}
