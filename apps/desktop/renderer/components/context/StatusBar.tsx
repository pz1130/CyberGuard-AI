import { useEnvironment, useRun } from "../../state";
import type { SettingsSection } from "../../lib/types";
import { Disclosure, StatusDot, Tooltip } from "../../ui";
import type { StatusLevel } from "../../ui";
import "./StatusBar.css";

function sandboxLevel(impl: string): StatusLevel {
  if (impl === "none") return "danger";
  if (impl === "unknown") return "warn";
  return "ok";
}

function tccLevel(summary: string): StatusLevel {
  if (summary === "restricted") return "warn";
  if (summary === "fda_likely") return "ok";
  return "idle";
}

function connectionLabel(pingOk: boolean | null): string {
  if (pingOk === true) return "在线";
  if (pingOk === false) return "离线";
  return "连接中";
}

export function StatusBar({
  onOpenSettings,
}: {
  onOpenSettings: (s?: SettingsSection) => void;
}) {
  const env = useEnvironment();
  const { tier, paused, pausedRunId } = useRun();

  const online: StatusLevel =
    env.pingOk === null ? "idle" : env.pingOk ? "ok" : "danger";

  return (
    <footer className="statusbar" aria-label="运行态">
      {/* 六项常显，不可折叠 —— INV-36 / M2 判据 10 */}
      <div className="statusbar-row">
        <Tooltip content={env.pingOk === false ? "sidecar 未连接" : "sidecar"}>
          <span>
            <StatusDot level={online} label={connectionLabel(env.pingOk)} />
          </span>
        </Tooltip>
        <Tooltip content={`sandbox_impl: ${env.sandboxImpl}`}>
          <span>
            <StatusDot level={sandboxLevel(env.sandboxImpl)} label="沙箱" />
          </span>
        </Tooltip>
        <Tooltip content={env.tccGuidance || `tcc: ${env.tccSummary}`}>
          <span>
            <StatusDot level={tccLevel(env.tccSummary)} label="权限" />
          </span>
        </Tooltip>
      </div>

      <div className="statusbar-row statusbar-row--text">
        <button
          type="button"
          className={`statusbar-chip${
            env.providerMode === "live" ? " is-ok" : " is-warn"
          }`}
          onClick={() => onOpenSettings("llm")}
        >
          {env.providerMode === "live" ? "live" : "mock"}
        </button>
        <span className="statusbar-sep">·</span>
        <span className="statusbar-tier">
          {tier === "readonly" ? "只读" : "完整"}
        </span>
        {paused ? (
          <span className="statusbar-paused">
            ⏸ 已暂停
            {pausedRunId ? ` ${pausedRunId.slice(0, 8)}` : ""}
          </span>
        ) : null}
      </div>

      <Disclosure summary="环境详情" className="statusbar-more">
        <dl className="statusbar-kv">
          <dt>read</dt>
          <dd>
            {env.caps?.has_read ? "yes" : "no"}
            {env.caps?.real_read ? " · real" : ""}
          </dd>
          <dt>exec / edit</dt>
          <dd>
            {env.caps?.has_exec ? "exec" : "—"} /{" "}
            {env.caps?.has_edit ? "edit" : "—"}
          </dd>
          <dt>sandbox_mode</dt>
          <dd>{env.sandboxMode}</dd>
          <dt>tcc</dt>
          <dd>{env.tccSummary}</dd>
          <dt>data_root</dt>
          <dd title={env.dataRoot}>
            …/{env.dataRoot.split("/").slice(-2).join("/") || "—"}
          </dd>
        </dl>
      </Disclosure>
    </footer>
  );
}
