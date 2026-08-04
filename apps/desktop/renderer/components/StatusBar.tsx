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

/** Compact status: 4 primary pills; rest in title tooltips on “more”. */
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
  const sbBad = sandboxImpl === "none";
  const sbOk = sandboxImpl === "seatbelt";
  const llmOk = providerMode === "live";
  const runPaused =
    runStatus === "已暂停" || runStatus === "paused";
  const runBusy = runStatus === "running";

  const moreTitle = [
    `tcc: ${tccSummary}`,
    tccWarning || tccGuidance || "",
    `tier: ${tier}`,
    evidenceHint,
    "ports: none (JSONL stdio)",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="status-bar" role="status">
      <span className={pingOk ? "ok" : "bad"} title={statusLabel}>
        <span aria-hidden className="status-dot" />
        {pingOk ? "Online" : "Offline"}
      </span>
      <span
        className={sbBad ? "bad" : sbOk ? "ok" : ""}
        title={
          sbBad
            ? "No OS sandbox — host tools stay disabled"
            : `sandbox ${sandboxImpl}/${sandboxMode}`
        }
      >
        {sbOk ? "Sandbox" : sbBad ? "No sandbox" : sandboxImpl}
      </span>
      <span
        className={llmOk ? "ok" : "bad"}
        title={`LLM mode: ${providerMode}`}
      >
        LLM {providerMode}
      </span>
      <span
        className={runPaused ? "bad" : runBusy ? "ok" : ""}
        title={
          pausedRunId
            ? `paused ${pausedRunId}`
            : `run ${runStatus} · tier ${tier}`
        }
      >
        {runPaused ? "Paused" : runBusy ? "Running" : "Idle"}
      </span>
      <span className="status-more" title={moreTitle}>
        {evidenceHint.replace(/^evidence:\s*/i, "Ev ")} · {tier}
      </span>
    </div>
  );
}
