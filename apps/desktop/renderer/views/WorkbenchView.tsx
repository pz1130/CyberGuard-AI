import { useEffect, useRef } from "react";
import { DataPanel } from "../components/DataPanel";
import { EmptyState } from "../components/EmptyState";
import { EventCard } from "../components/EventCard";
import { SessionList } from "../components/SessionList";
import type { Caps, Ev, SessionRow, Tier } from "../lib/types";

type Props = {
  sessions: SessionRow[];
  sessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewInvestigation: () => void;
  events: Ev[];
  lastSubmitted: string | null;
  task: string;
  onTaskChange: (v: string) => void;
  onRun: () => void;
  onAbort: () => void;
  running: boolean;
  runId: string | null;
  tier: Tier;
  onTierChange: (t: Tier) => void;
  steerText: string;
  onSteerTextChange: (v: string) => void;
  onSteer: () => void;
  caps: Caps | null;
  dataRoot: string;
  mcpTools: string[];
  hasApi: boolean;
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
      />

      <div className="col">
        <h2>Execution</h2>
        <div className="col-body">
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
              <EventCard key={i} ev={ev} />
            ))}
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
              <option value="full">full（本机工具仍 mock）</option>
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
          <div className="kv">
            <span>has_read</span>
            <span>{String(props.caps?.has_read ?? "—")}</span>
            <span>real_read</span>
            <span>{String(props.caps?.real_read ?? "—")}</span>
            <span>real_edit</span>
            <span>{String(props.caps?.real_edit ?? "—")}</span>
            <span>real_exec</span>
            <span>{String(props.caps?.real_exec ?? "—")}</span>
            <span>has_exec</span>
            <span>{String(props.caps?.has_exec ?? "—")}</span>
            <span>has_edit</span>
            <span>{String(props.caps?.has_edit ?? "—")}</span>
            <span>run_id</span>
            <span className="mono-sm">{props.runId ?? "—"}</span>
            <span>session_id</span>
            <span className="mono-sm">{props.sessionId ?? "—"}</span>
            <span>data_root</span>
            <span className="mono-xs">{props.dataRoot || "—"}</span>
          </div>
          <p className="muted-copy mt-16">
            Readonly 档不暴露本机 Exec。MCP 来自{" "}
            <code>mcp_servers.json</code>。
          </p>
          {props.mcpTools.length > 0 && (
            <div className="mcp-tools-block">
              <div className="muted-copy mb-6">MCP tools（上次运行）</div>
              <ul className="mcp-tools-list">
                {props.mcpTools.map((n) => (
                  <li key={n} className="mono-sm">
                    {n}
                  </li>
                ))}
              </ul>
            </div>
          )}

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
