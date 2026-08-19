import { useEffect, useMemo, useState } from "react";
import type { Tier } from "../../lib/types";
import { useI18n } from "../../i18n/I18nProvider";
import { useEnvironment, useRun } from "../../state";
import { Button, Select } from "../../ui";
import "./Composer.css";

export function Composer() {
  const {
    task,
    setTask,
    tier,
    setTier,
    run,
    abort,
    steer,
    steerText,
    setSteerText,
    running,
    runId,
  } = useRun();
  const { pingOk, sandboxImpl } = useEnvironment();
  const { t } = useI18n();
  const [showSteer, setShowSteer] = useState(false);

  const tierOptions = useMemo(
    (): Array<{ value: Tier; label: string }> => [
      { value: "readonly", label: t("composer.tier.readonly") },
      { value: "full", label: t("composer.tier.full") },
    ],
    [t]
  );

  const hasApi = typeof window !== "undefined" && Boolean(window.cyberguard);
  const sidecarOffline = !hasApi || pingOk === false;
  const sandboxLocked = sandboxImpl === "none";
  const runDisabled = sidecarOffline || running || !task.trim();

  useEffect(() => {
    if (sandboxImpl === "none" && tier !== "readonly") {
      setTier("readonly");
    }
  }, [sandboxImpl, tier, setTier]);

  return (
    <div className="composer2">
      <textarea
        className="composer2-input"
        value={task}
        onChange={(e) => setTask(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            if (!runDisabled) void run();
          }
        }}
        placeholder={t("composer.placeholder")}
        disabled={running}
        rows={3}
      />

      <div className="composer2-bar">
        <Select
          value={tier}
          onChange={setTier}
          options={tierOptions}
          ariaLabel={t("composer.tier.aria")}
          size="sm"
          disabled={running || sandboxLocked}
        />
        <Button
          variant="primary"
          size="sm"
          onClick={() => void run()}
          disabled={runDisabled}
        >
          {running ? t("composer.running") : t("composer.run")}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void abort()}
          disabled={!running || !runId}
        >
          {t("composer.abort")}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowSteer((v) => !v)}
          disabled={!running || !runId}
        >
          {t("composer.steer")}
        </Button>
        <span className="composer2-hint">
          {sidecarOffline ? t("composer.hint.offline") : t("composer.hint.run")}
        </span>
      </div>

      {showSteer ? (
        <div className="composer2-steer">
          <input
            className="composer2-steerinput"
            value={steerText}
            onChange={(e) => setSteerText(e.target.value)}
            placeholder={t("composer.steer.placeholder")}
            disabled={!running || !runId}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void steer()}
            disabled={!running || !runId || !steerText.trim()}
          >
            {t("composer.steer.send")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
