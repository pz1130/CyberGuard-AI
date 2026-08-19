import { useEnvironment, useRun } from "../../state";
import type { SettingsSection } from "../../lib/types";
import { useI18n } from "../../i18n/I18nProvider";
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

function connectionKey(pingOk: boolean | null): string {
  if (pingOk === true) return "statusbar.online";
  if (pingOk === false) return "statusbar.offline";
  return "statusbar.connecting";
}

export function StatusBar({
  onOpenSettings,
}: {
  onOpenSettings: (s?: SettingsSection) => void;
}) {
  const { t } = useI18n();
  const env = useEnvironment();
  const { tier, paused, pausedRunId } = useRun();

  const online: StatusLevel =
    env.pingOk === null ? "idle" : env.pingOk ? "ok" : "danger";
  const degraded = env.securityDegradations.length > 0;

  return (
    <footer
      className={`statusbar${degraded ? " statusbar--danger" : ""}`}
      aria-label={t("statusbar.aria")}
    >
      {/* 常显五项，不可折叠 —— INV-36 / M2 判据 10。
          第六项「暂停」在下一组里按 paused 出现，未暂停时不占位。 */}
      <div className="statusbar-row">
        <Tooltip
          content={
            env.pingOk === false
              ? t("statusbar.sidecarOffline")
              : t("statusbar.sidecarOk")
          }
        >
          <span>
            <StatusDot
              level={online}
              label={t(connectionKey(env.pingOk))}
            />
          </span>
        </Tooltip>
        <Tooltip content={`sandbox_impl: ${env.sandboxImpl}`}>
          <span>
            <StatusDot
              level={sandboxLevel(env.sandboxImpl)}
              label={t("statusbar.sandbox")}
            />
          </span>
        </Tooltip>
        <Tooltip content={env.tccGuidance || `tcc: ${env.tccSummary}`}>
          <span>
            <StatusDot
              level={tccLevel(env.tccSummary)}
              label={t("statusbar.permission")}
            />
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
          {tier === "readonly"
            ? t("statusbar.tierReadonly")
            : t("statusbar.tierFull")}
        </span>
        {paused ? (
          <span className="statusbar-paused">
            ⏸ {t("statusbar.paused")}
            {pausedRunId ? ` ${pausedRunId.slice(0, 8)}` : ""}
          </span>
        ) : null}
      </div>

      <Disclosure
        summary={t("statusbar.envDetails")}
        className="statusbar-more"
      >
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
