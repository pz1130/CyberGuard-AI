import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Caps, Ev, PendingPlan, SessionRow, Tier } from "../lib/types";

export function useDesktopRuntime() {
  const [pingOk, setPingOk] = useState<boolean | null>(null);
  const [tier, setTier] = useState<Tier>("readonly");
  const [caps, setCaps] = useState<Caps | null>(null);
  const [task, setTask] = useState("");
  const [events, setEvents] = useState<Ev[]>([]);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [steerText, setSteerText] = useState("");
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [dataRoot, setDataRoot] = useState("");
  const [providerMode, setProviderMode] = useState("mock");
  const [sandboxImpl, setSandboxImpl] = useState("unknown");
  const [sandboxMode, setSandboxMode] = useState("—");
  const [fvWarning, setFvWarning] = useState<string | null>(null);
  const [tccSummary, setTccSummary] = useState("—");
  const [tccWarning, setTccWarning] = useState<string | null>(null);
  const [tccGuidance, setTccGuidance] = useState<string | null>(null);
  const [mcpTools, setMcpTools] = useState<string[]>([]);
  const [lastSubmitted, setLastSubmitted] = useState<string | null>(null);
  const [pendingPlan, setPendingPlan] = useState<PendingPlan | null>(null);
  const [planEdit, setPlanEdit] = useState("");
  const [runStatus, setRunStatus] = useState("idle");
  const [pausedRunId, setPausedRunId] = useState<string | null>(null);
  const [evidenceHint, setEvidenceHint] = useState("—");
  const [exportPass, setExportPass] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [uninstallPreview, setUninstallPreview] = useState<string | null>(null);
  const [uninstallBusy, setUninstallBusy] = useState(false);
  const [showDataPanel, setShowDataPanel] = useState(false);
  const taskRef = useRef(task);
  taskRef.current = task;

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const refreshSessions = useCallback(() => {
    if (!api?.listSessions) return;
    api
      .listSessions()
      .then((r) => setSessions(r.sessions || []))
      .catch(() => setSessions([]));
  }, [api]);

  useEffect(() => {
    if (!api) {
      setPingOk(false);
      return;
    }
    api
      .ping()
      .then((r: Record<string, unknown>) => {
        setPingOk(true);
        if (typeof r?.data_root === "string") setDataRoot(r.data_root);
        const prov = r?.provider as { mode?: string } | undefined;
        if (prov?.mode) setProviderMode(prov.mode);
        const sb = r?.sandbox as
          | { sandbox_impl?: string; warning?: string | null }
          | undefined;
        if (sb?.sandbox_impl) setSandboxImpl(sb.sandbox_impl);
        const defaults = r?.policy_defaults as
          | { readonly?: { sandbox_mode?: string } }
          | undefined;
        if (defaults?.readonly?.sandbox_mode) {
          setSandboxMode(String(defaults.readonly.sandbox_mode));
        }
        const fv = r?.filevault as { warning?: string | null } | undefined;
        setFvWarning(fv?.warning || null);
        const tcc = r?.tcc as
          | {
              summary?: string;
              warning?: string | null;
              guidance?: string | null;
              full_disk_access?: boolean | null;
            }
          | undefined;
        if (tcc?.summary) setTccSummary(String(tcc.summary));
        else if (tcc?.full_disk_access === true) setTccSummary("fda_likely");
        else if (tcc?.full_disk_access === false) setTccSummary("restricted");
        setTccWarning(tcc?.warning || null);
        setTccGuidance(tcc?.guidance || null);
        const ec = r?.evidence_count;
        if (typeof ec === "number") setEvidenceHint(`evidence: ${ec}`);
        const paused = r?.paused_runs;
        if (Array.isArray(paused) && paused.length) {
          setRunStatus("已暂停");
          const first = paused[0] as { run_id?: string };
          if (first?.run_id) setPausedRunId(String(first.run_id));
        }
      })
      .catch(() => setPingOk(false));
    refreshSessions();
  }, [api, refreshSessions]);

  useEffect(() => {
    if (!api) return;
    api
      .capabilities(tier)
      .then((c) => {
        setCaps(c);
        const pol = (c as Caps & { policy?: { sandbox_mode?: string } }).policy;
        if (pol?.sandbox_mode) setSandboxMode(pol.sandbox_mode);
      })
      .catch(() => setCaps(null));
  }, [api, tier]);

  useEffect(() => {
    if (!api) return;
    return api.onEvent((ev) => {
      setEvents((prev) => [...prev, ev]);
      if (ev.type === "run_started" && typeof ev.run_id === "string") {
        setRunId(ev.run_id);
        setRunStatus("running");
        setPausedRunId(null);
        const tools = ev.mcp_tools;
        if (Array.isArray(tools)) {
          setMcpTools(tools.map(String));
        }
      }
      if (ev.type === "run_paused") {
        setRunStatus(String(ev.ui_status || "已暂停"));
        if (typeof ev.run_id === "string") setPausedRunId(ev.run_id);
      }
      if (ev.type === "run_resumed") {
        setRunStatus(String(ev.ui_status || "已恢复"));
        setPausedRunId(null);
      }
      if (ev.type === "answer_ready") {
        setRunStatus("idle");
      }
      if (ev.type === "start" && typeof ev.agent_run_id === "string") {
        setRunId(String(ev.agent_run_id));
      }
      if (
        (ev.type === "plan_ready" || ev.type === "privilege_required") &&
        typeof ev.plan_id === "string"
      ) {
        const plan = (ev.plan || {}) as PendingPlan["plan"];
        const label =
          ev.type === "privilege_required"
            ? String(ev.ui_label || "自批准") + " · 提权"
            : String(ev.ui_label || "自批准");
        setPendingPlan({
          plan_id: String(ev.plan_id),
          plan,
          approval_type: String(ev.approval_type || "self"),
          ui_label: label,
          local_approve_allowed: ev.local_approve_allowed !== false,
          timeout_seconds:
            typeof ev.timeout_seconds === "number"
              ? ev.timeout_seconds
              : undefined,
        });
        setPlanEdit(String(plan?.summary || ""));
      }
      if (
        ev.type === "plan_approved" ||
        ev.type === "plan_rejected" ||
        ev.type === "privilege_decided" ||
        ev.type === "policy_event"
      ) {
        if (ev.type !== "policy_event") {
          setPendingPlan(null);
        }
      }
    });
  }, [api]);

  useEffect(() => {
    if (!api?.onOpenDataPanel) return;
    return api.onOpenDataPanel(() => setShowDataPanel(true));
  }, [api]);

  const onRun = useCallback(async () => {
    if (!api || running) return;
    const text = (taskRef.current || task).trim();
    if (!text) return;

    setRunning(true);
    setEvents([]);
    setRunId(null);
    setLastSubmitted(text);
    setSessionId(null);
    try {
      const res = await api.run(text, tier, undefined);
      const sid =
        (res?.result as { session_id?: string } | undefined)?.session_id || null;
      if (sid) setSessionId(sid);
      refreshSessions();
    } catch (e) {
      setEvents((prev) => [
        ...prev,
        { type: "error", error: String(e), status: "failed" },
      ]);
    } finally {
      setRunning(false);
    }
  }, [api, task, tier, running, refreshSessions]);

  const onSelectSession = useCallback(
    async (sid: string) => {
      if (!api) return;
      setSessionId(sid);
      try {
        const r = await api.sessionEvents(sid);
        const evs = r.events || [];
        setEvents(evs);
        for (let i = evs.length - 1; i >= 0; i--) {
          if (evs[i].type === "user_task" && typeof evs[i].task === "string") {
            setTask(String(evs[i].task));
            setLastSubmitted(String(evs[i].task));
            break;
          }
        }
      } catch {
        setEvents([]);
      }
    },
    [api]
  );

  const onNewInvestigation = useCallback(() => {
    setSessionId(null);
    setEvents([]);
    setRunId(null);
    setLastSubmitted(null);
    setTask("");
  }, []);

  const onAbort = useCallback(async () => {
    if (!api || !runId) return;
    await api.abort(runId);
    setPendingPlan(null);
  }, [api, runId]);

  const onSteer = useCallback(async () => {
    if (!api || !runId || !steerText.trim()) return;
    await api.steer(runId, steerText.trim());
    setSteerText("");
  }, [api, runId, steerText]);

  const onPlanApprove = useCallback(async () => {
    if (!api?.planApprove || !pendingPlan) return;
    if (!pendingPlan.local_approve_allowed) return;
    const revised =
      planEdit.trim() && planEdit.trim() !== (pendingPlan.plan?.summary || "")
        ? planEdit.trim()
        : undefined;
    try {
      await api.planApprove(pendingPlan.plan_id, revised);
    } catch (e) {
      setEvents((prev) => [
        ...prev,
        { type: "error", error: `plan approve failed: ${e}` },
      ]);
    }
  }, [api, pendingPlan, planEdit]);

  const onPlanReject = useCallback(async () => {
    if (!api?.planReject || !pendingPlan) return;
    try {
      await api.planReject(pendingPlan.plan_id, "rejected_by_user");
    } catch (e) {
      setEvents((prev) => [
        ...prev,
        { type: "error", error: `plan reject failed: ${e}` },
      ]);
    }
  }, [api, pendingPlan]);

  const onExport = useCallback(async () => {
    if (!api?.exportEncrypted) {
      setExportMsg("export API unavailable (open via Electron)");
      return;
    }
    if (exportPass.trim().length < 8) {
      setExportMsg("passphrase ≥ 8 characters");
      return;
    }
    setExportBusy(true);
    setExportMsg(null);
    try {
      const r = await api.exportEncrypted(exportPass);
      if (r?.canceled) {
        setExportMsg("export canceled");
      } else if (r?.ok === false) {
        setExportMsg(String(r.error || "export failed"));
      } else {
        const dest = r.dest || r.path || "file";
        const hash = r.plaintext_sha256 || r.sha256;
        setExportMsg(
          `exported (${r.method || "encrypted"}) → ${dest}` +
            (hash ? ` · sha256 ${String(hash).slice(0, 12)}…` : "")
        );
        setExportPass("");
      }
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setExportBusy(false);
    }
  }, [api, exportPass]);

  const onUninstallInventory = useCallback(async () => {
    if (!api?.uninstallInventory) {
      setUninstallPreview("uninstall API unavailable");
      return;
    }
    setUninstallBusy(true);
    try {
      const inv = await api.uninstallInventory();
      const del = (inv.will_delete || [])
        .map((c) => `  - ${c.name} (${c.approx_bytes ?? "?"} B)`)
        .join("\n");
      const keep = (inv.will_not_delete?.evidence_outside_data_root || []).join(
        "\n  - "
      );
      const manual = (inv.manual_steps || [])
        .map((m) => `  - ${m.item}: ${m.action}`)
        .join("\n");
      setUninstallPreview(
        `data_root: ${inv.data_root || "?"}\n` +
          `will delete:\n${del || "  (empty)"}\n` +
          `will NOT delete (external evidence):\n  - ${keep || "(none)"}\n` +
          `manual steps:\n${manual || "  (none)"}`
      );
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api]);

  const onUninstallDryRun = useCallback(async () => {
    if (!api?.uninstallExecute) return;
    setUninstallBusy(true);
    try {
      const r = await api.uninstallExecute({ confirm: true, dryRun: true });
      setUninstallPreview(
        (uninstallPreview ? uninstallPreview + "\n\n" : "") +
          `dry_run result: executed=${String(r.executed)} ok=${String(r.ok)}`
      );
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api, uninstallPreview]);

  const onUninstallExecute = useCallback(async () => {
    if (!api?.uninstallExecute) return;
    setUninstallBusy(true);
    try {
      const r = await api.uninstallExecute({ confirm: true, dryRun: false });
      if (r?.canceled) {
        setUninstallPreview("uninstall canceled");
      } else {
        setUninstallPreview(
          `executed=${String(r.executed)} deleted=${(r.deleted || []).join(", ") || "—"}`
        );
        if (r.executed) {
          setSessions([]);
          setSessionId(null);
          setEvents([]);
        }
      }
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api]);

  const statusLabel = useMemo(() => {
    if (!api) return "no preload (open via Electron)";
    if (pingOk === null) return "connecting…";
    return pingOk ? "sidecar online" : "sidecar offline";
  }, [api, pingOk]);

  return {
    api,
    pingOk,
    tier,
    setTier,
    caps,
    task,
    setTask,
    events,
    running,
    runId,
    steerText,
    setSteerText,
    sessions,
    sessionId,
    dataRoot,
    providerMode,
    setProviderMode,
    sandboxImpl,
    sandboxMode,
    fvWarning,
    tccSummary,
    tccWarning,
    tccGuidance,
    mcpTools,
    lastSubmitted,
    pendingPlan,
    planEdit,
    setPlanEdit,
    runStatus,
    pausedRunId,
    evidenceHint,
    setEvidenceHint,
    exportPass,
    setExportPass,
    exportBusy,
    exportMsg,
    uninstallPreview,
    uninstallBusy,
    showDataPanel,
    setShowDataPanel,
    statusLabel,
    onRun,
    onSelectSession,
    onNewInvestigation,
    onAbort,
    onSteer,
    onPlanApprove,
    onPlanReject,
    onExport,
    onUninstallInventory,
    onUninstallDryRun,
    onUninstallExecute,
  };
}
