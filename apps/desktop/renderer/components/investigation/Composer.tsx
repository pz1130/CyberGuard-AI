import { useEffect, useState } from "react";
import type { Tier } from "../../lib/types";
import { useEnvironment, useRun } from "../../state";
import { Button, Select } from "../../ui";
import "./Composer.css";

const TIER_OPTIONS: Array<{ value: Tier; label: string }> = [
  { value: "readonly", label: "只读" },
  { value: "full", label: "完整" },
];

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
  const [showSteer, setShowSteer] = useState(false);

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
        placeholder="描述任务… 例如：分诊 high/critical 告警，给出优先级与建议动作"
        disabled={running}
        rows={3}
      />

      <div className="composer2-bar">
        <Select
          value={tier}
          onChange={setTier}
          options={TIER_OPTIONS}
          ariaLabel="能力档位"
          size="sm"
          disabled={running || sandboxLocked}
        />
        <Button
          variant="primary"
          size="sm"
          onClick={() => void run()}
          disabled={runDisabled}
        >
          {running ? "运行中…" : "运行"}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void abort()}
          disabled={!running || !runId}
        >
          中止
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowSteer((v) => !v)}
          disabled={!running || !runId}
        >
          中途补充
        </Button>
        <span className="composer2-hint">
          {sidecarOffline ? "sidecar 未连接，运行已禁用" : "⌘↵ 运行"}
        </span>
      </div>

      {showSteer ? (
        <div className="composer2-steer">
          <input
            className="composer2-steerinput"
            value={steerText}
            onChange={(e) => setSteerText(e.target.value)}
            placeholder="运行中途补充说明…"
            disabled={!running || !runId}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void steer()}
            disabled={!running || !runId || !steerText.trim()}
          >
            发送
          </Button>
        </div>
      ) : null}
    </div>
  );
}
