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

function pillClass(kind: "ok" | "bad" | ""): string {
  if (kind === "ok") return "ok";
  if (kind === "bad") return "bad";
  return "";
}

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
  const sb =
    sandboxImpl === "none" ? "bad" : sandboxImpl === "seatbelt" ? "ok" : "";
  const tcc =
    tccSummary === "restricted"
      ? "bad"
      : tccSummary === "fda_likely"
        ? "ok"
        : "";
  const run =
    runStatus === "已暂停" || runStatus === "paused" || runStatus === "running"
      ? runStatus === "running"
        ? "ok"
        : "bad"
      : "";
  const llm = providerMode === "live" ? "ok" : "bad";

  return (
    <div className="status-bar" role="status">
      <span className={pillClass(pingOk ? "ok" : "bad")}>
        <span aria-hidden>●</span> {statusLabel}
      </span>
      <span
        className={pillClass(sb)}
        title={
          sandboxImpl === "none"
            ? "无 OS 沙箱 — 真实本机工具保持禁用"
            : `impl=${sandboxImpl}`
        }
      >
        sandbox {sandboxImpl}/{sandboxMode}
      </span>
      <span
        className={pillClass(tcc)}
        title={tccGuidance || tccWarning || "TCC probe (heuristic)"}
      >
        tcc {tccSummary}
      </span>
      <span className={pillClass(llm)}>llm {providerMode}</span>
      <span>tier {tier}</span>
      <span
        className={pillClass(run === "bad" ? "bad" : run === "ok" ? "ok" : "")}
        title={pausedRunId ? `paused run ${pausedRunId}` : undefined}
      >
        run {runStatus}
      </span>
      <span title="Evidence browser items (read-only + sha256)">
        {evidenceHint}
      </span>
      <span title="No listen ports — JSONL stdio only">stdio</span>
    </div>
  );
}
