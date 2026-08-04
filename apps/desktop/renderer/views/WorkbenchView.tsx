import { useEffect, useRef } from "react";
import { DataPanel } from "../components/DataPanel";
import { EmptyState } from "../components/EmptyState";
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
  // data panel
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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [props.events]);

  return (
    <div className="workbench view-enter">
      <SessionList
        sessions={props.sessions}
        sessionId={props.sessionId}
        onSelect={props.onSelectSession}
        onNew={props.onNewInvestigation}
        onDelete={props.onDeleteSession}
      />

      <div className="col">
        <h2>Execution</h2>
        <div className="col-body">
          {(props.runStatus === "已暂停" || props.runStatus === "paused") && (
            <div className="submitted-banner pause-banner">
              运行已暂停
              {props.pausedRunId ? ` · ${props.pausedRunId.slice(0, 8)}…` : ""}
              {props.onResume ? (
                <button
                  type="button"
                  className="primary"
                  style={{ marginLeft: 10 }}
                  onClick={() => void props.onResume?.()}
                >
                  Resume
                </button>
              ) : null}
            </div>
          )}
          {props.lastSubmitted && (
            <div className="submitted-banner">
              本次提交：<strong>{props.lastSubmitted}</strong>
            </div>
          )}
          <div className="timeline">
            {props.events.length === 0 && (
              <EmptyState
                onOpenSettingsLlm={props.onOpenSettingsLlm}
                onOpenSettingsMcp={props.onOpenSettingsMcp}
                onFillSample={(text) => props.onTaskChange(text)}
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
                  {props.streaming ? "流式输出…" : "流式草稿"}
                  {props.streaming ? (
                    <span className="stream-cursor" aria-hidden>
                      ▍
                    </span>
                  ) : null}
                </div>
                {props.streamText ? (
                  <Markdown text={props.streamText} />
                ) : (
                  <div className="ev-meta">waiting for tokens…</div>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
        <div className="composer">
          <textarea
            value={props.task}
            onChange={(e) => props.onTaskChange(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                void props.onRun();
              }
            }}
            placeholder="在这里输入任务，例如：这批告警里哪些值得优先处理？给出理由与建议动作。"
            disabled={props.running}
          />
          <div className="row">
            <select
              value={props.tier}
              onChange={(e) => props.onTierChange(e.target.value as Tier)}
              disabled={props.running}
            >
              <option value="readonly">readonly（无本机 Exec）</option>
              <option value="full">full</option>
            </select>
            <button
              className="primary"
              type="button"
              onClick={() => void props.onRun()}
              disabled={!props.hasApi || props.running || !props.task.trim()}
            >
              {props.running ? "Running…" : "Run"}
            </button>
            <button
              className="secondary"
              type="button"
              onClick={() => void props.onAbort()}
              disabled={!props.running || !props.runId}
            >
              Abort
            </button>
            {props.onResume &&
            (props.pausedRunId ||
              props.runStatus === "已暂停" ||
              props.runStatus === "paused") ? (
              <button
                className="secondary"
                type="button"
                onClick={() => void props.onResume?.()}
                disabled={props.running}
              >
                Resume
              </button>
            ) : null}
          </div>
          <div className="hint">
            Run 始终使用<strong>上方输入框当前文字</strong>
            （新建调查，不沿用旧会话标题）。⌘/Ctrl+Enter 也可运行。
          </div>
          <div className="row">
            <input
              className="steer-input"
              value={props.steerText}
              onChange={(e) => props.onSteerTextChange(e.target.value)}
              placeholder="运行中途补充说明（Steer）…"
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
              Steer
            </button>
          </div>
        </div>
      </div>

      <div className="col">
        <h2>Context</h2>
        <div className="col-body">
          <div className="context-section">
            <div className="context-h">Auth / capabilities</div>
            <div className="kv">
              <span>llm</span>
              <span>
                <span
                  className={`pill ${props.providerMode === "live" ? "ok" : "warn"}`}
                >
                  {props.providerMode}
                </span>
              </span>
              <span>tier</span>
              <span>{props.tier}</span>
              <span>read</span>
              <span>
                {props.caps?.has_read ? "yes" : "no"}
                {props.caps?.real_read ? " · real" : " · mock"}
              </span>
              <span>exec / edit</span>
              <span>
                {props.caps?.has_exec ? "exec" : "no-exec"} ·{" "}
                {props.caps?.has_edit ? "edit" : "no-edit"}
              </span>
              <span>sandbox</span>
              <span className="mono-sm">
                {props.caps?.sandbox_impl || "—"}/
                {props.caps?.policy?.sandbox_mode || "—"}
              </span>
            </div>
          </div>

          <div className="context-section mt-12">
            <div className="context-h">Run</div>
            <div className="kv">
              <span>status</span>
              <span>{props.runStatus}</span>
              <span>run_id</span>
              <span className="mono-sm">{props.runId ?? "—"}</span>
              <span>session</span>
              <span className="mono-sm">
                {props.sessionId
                  ? `${props.sessionId.slice(0, 12)}…`
                  : "—"}
              </span>
            </div>
          </div>

          {props.mcpTools.length > 0 && (
            <div className="context-section mt-12">
              <div className="context-h">MCP tools（本轮）</div>
              <ul className="mcp-tools-list">
                {props.mcpTools.map((n) => (
                  <li key={n} className="mono-sm">
                    {n}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="muted-copy mt-12">
            data_root:{" "}
            <code className="mono-xs">{props.dataRoot || "—"}</code>
          </p>

          <DataPanel
            open={props.showDataPanel}
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
        </div>
      </div>
    </div>
  );
}
