type Props = {
  statusLabel: string;
  pingOk: boolean | null;
  sandboxImpl: string;
  sandboxMode: string;
  tccSummary: string;
  tccGuidance: string | null;
  tccWarning: string | null;
  providerMode: string;
  tier: string;
  runStatus: string;
  pausedRunId: string | null;
  evidenceHint: string;
};

export function StatusBar({
  statusLabel,
  pingOk,
  sandboxImpl,
  sandboxMode,
  tccSummary,
  tccGuidance,
  tccWarning,
  providerMode,
  tier,
  runStatus,
  pausedRunId,
  evidenceHint,
}: Props) {
  return (
    <div className="status-bar">
      <span className={pingOk ? "ok" : "bad"}>● {statusLabel}</span>
      <span
        className={
          sandboxImpl === "none" ? "bad" : sandboxImpl === "seatbelt" ? "ok" : ""
        }
        title={
          sandboxImpl === "none"
            ? "无 OS 沙箱 — 真实本机工具保持禁用"
            : `impl=${sandboxImpl}`
        }
      >
        sandbox: {sandboxImpl}/{sandboxMode}
      </span>
      <span
        className={
          tccSummary === "restricted"
            ? "bad"
            : tccSummary === "fda_likely"
              ? "ok"
              : ""
        }
        title={tccGuidance || tccWarning || "TCC probe (heuristic)"}
      >
        tcc: {tccSummary}
      </span>
      <span>llm: {providerMode}</span>
      <span>tier: {tier}</span>
      <span
        className={
          runStatus === "已暂停" || runStatus === "paused" ? "bad" : ""
        }
        title={pausedRunId ? `paused run ${pausedRunId}` : undefined}
      >
        run: {runStatus}
      </span>
      <span title="Evidence browser items (read-only + sha256)">
        {evidenceHint}
      </span>
      <span>ports: none (JSONL stdio)</span>
    </div>
  );
}
