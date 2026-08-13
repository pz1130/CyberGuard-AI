import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Caps, Ev, PendingPlan, SessionRow, Tier } from "../lib/types";

export function useDesktopRuntime() {
  const [pingOk, setPingOk] = useState<boolean | null>(null);
  const [tier, setTier] = useState<Tier>("readonly");
  const [caps, setCaps] = useState<Caps | null>(null);
  const [task, setTask] = useState("");
  const [events, setEvents] = useState<Ev[]>([]);
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);
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
        const prov = r?.provider as { mode?: string; has_api_key?: boolean } | undefined;
        if (prov?.mode) setProviderMode(prov.mode);
        // Reconcile with provider.get (effective live/mock after secrets load)
        void api.providerGet?.().then((p) => {
          const eff = p?.effective?.mode || p?.mode;
          if (eff) setProviderMode(String(eff));
        });
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
      // token stream: coalesce into buffer; do not spam timeline cards
      if (ev.type === "token" && typeof ev.delta === "string") {
        setStreaming(true);
        setStreamText((prev) => prev + String(ev.delta));
        return;
      }
      if (ev.type === "token_done") {
        setStreaming(false);
        // keep streamText until answer_ready card replaces it
        return;
      }

      setEvents((prev) => [...prev, ev]);
      if (ev.type === "run_started" && typeof ev.run_id === "string") {
        setRunId(ev.run_id);
        setRunStatus("running");
        setPausedRunId(null);
        setStreamText("");
        setStreaming(false);
        const tools = ev.mcp_tools;
        if (Array.isArray(tools)) {
          setMcpTools(tools.map(String));
        }
      }
      // New tool round: clear intermediate model chatter so final stream is clean
      if (ev.type === "tool_call_start") {
        setStreamText("");
        setStreaming(false);
      }
      if (ev.type === "run_paused") {
        setRunStatus(String(ev.ui_status || "已暂停"));
        if (typeof ev.run_id === "string") setPausedRunId(ev.run_id);
        setStreaming(false);
      }
      if (ev.type === "run_resumed") {
        setRunStatus(String(ev.ui_status || "已恢复"));
        setPausedRunId(null);
      }
      if (ev.type === "answer_ready") {
        setRunStatus("idle");
        setStreaming(false);
        // Prefer full answer on card; clear live buffer
        setStreamText("");
      }
      if (ev.type === "error") {
        setStreaming(false);
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

  const onRun = useCallback(async () => {
    if (!api || running) return;
    const text = (taskRef.current || task).trim();
    if (!text) return;

    setRunning(true);
    setEvents([]);
    setStreamText("");
    setStreaming(false);
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

  const onDeleteSession = useCallback(
    async (sid: string) => {
      if (!api?.deleteSession) return;
      try {
        await api.deleteSession(sid);
        if (sessionId === sid) {
          setSessionId(null);
          setEvents([]);
          setLastSubmitted(null);
        }
        refreshSessions();
      } catch (e) {
        setEvents((prev) => [
          ...prev,
          { type: "error", error: `delete session failed: ${e}` },
        ]);
      }
    },
    [api, sessionId, refreshSessions]
  );

  const onAbort = useCallback(async () => {
    if (!api || !runId) return;
    await api.abort(runId);
    setPendingPlan(null);
  }, [api, runId]);

  const onResume = useCallback(async () => {
    const rid = pausedRunId || runId;
    if (!api?.resume || !rid) return;
    setRunning(true);
    try {
      await api.resume(rid);
      setRunStatus("running");
      setPausedRunId(null);
    } catch (e) {
      setEvents((prev) => [
        ...prev,
        { type: "error", error: `resume failed: ${e}` },
      ]);
    } finally {
      setRunning(false);
    }
  }, [api, pausedRunId, runId]);

  const onSteer = useCallback(async () => {
    if (!api || !runId || !steerText.trim()) return;
    await api.steer(runId, steerText.trim());
    setSteerText("");
  }, [api, runId, steerText]);

  const refreshProviderStatus = useCallback(async () => {
    if (!api?.providerGet) return;
    try {
      const p = await api.providerGet();
      const eff = p.effective?.mode || p.mode;
      setProviderMode(String(eff || p.mode || "mock"));
    } catch {
      /* ignore */
    }
  }, [api]);

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
    streamText,
    streaming,
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
    statusLabel,
    onRun,
    onSelectSession,
    onNewInvestigation,
    onDeleteSession,
    onAbort,
    onResume,
    onSteer,
    onPlanApprove,
    onPlanReject,
    refreshProviderStatus,
    refreshSessions,
  };
}
