import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "./hooks/useTheme";
import type {
  ActiveView,
  Caps,
  Ev,
  PendingPlan,
  SessionRow,
  Tier,
} from "./lib/types";
import "./lib/types";

/** Minimal markdown → React nodes (headings, bold, lists, paragraphs). */
function SimpleMarkdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];

  const flushList = () => {
    if (!list.length) return;
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {list.map((item, i) => (
          <li key={i}>{inlineMd(item)}</li>
        ))}
      </ul>
    );
    list = [];
  };

  const inlineMd = (s: string): React.ReactNode => {
    // **bold** and `code`
    const parts: React.ReactNode[] = [];
    const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let k = 0;
    while ((m = re.exec(s))) {
      if (m.index > last) parts.push(s.slice(last, m.index));
      const tok = m[0];
      if (tok.startsWith("**")) {
        parts.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
      } else {
        parts.push(<code key={k++}>{tok.slice(1, -1)}</code>);
      }
      last = m.index + tok.length;
    }
    if (last < s.length) parts.push(s.slice(last));
    return parts.length === 1 ? parts[0] : <>{parts}</>;
  };

  for (const line of lines) {
    if (/^\s*[-*]\s+/.test(line)) {
      list.push(line.replace(/^\s*[-*]\s+/, ""));
      continue;
    }
    flushList();
    if (/^###\s+/.test(line)) {
      blocks.push(
        <h4 key={`h-${blocks.length}`}>{inlineMd(line.replace(/^###\s+/, ""))}</h4>
      );
    } else if (/^##\s+/.test(line)) {
      blocks.push(
        <h3 key={`h-${blocks.length}`}>{inlineMd(line.replace(/^##\s+/, ""))}</h3>
      );
    } else if (/^#\s+/.test(line)) {
      blocks.push(
        <h2 key={`h-${blocks.length}`}>{inlineMd(line.replace(/^#\s+/, ""))}</h2>
      );
    } else if (line.trim() === "") {
      blocks.push(<div key={`sp-${blocks.length}`} className="md-sp" />);
    } else {
      blocks.push(
        <p key={`p-${blocks.length}`}>{inlineMd(line)}</p>
      );
    }
  }
  flushList();
  return <div className="md-body">{blocks}</div>;
}

function EventCard({ ev }: { ev: Ev }) {
  const t = String(ev.type || "event");

  if (t === "user_task") {
    return (
      <div className="ev type-user_task">
        <div className="ev-label">你提交的任务</div>
        <div className="ev-task">{String(ev.task || "")}</div>
        {ev.tier ? (
          <div className="ev-meta">档位: {String(ev.tier)}</div>
        ) : null}
      </div>
    );
  }

  if (t === "run_started") {
    const prov = (ev.provider || {}) as {
      mode?: string;
      model?: string;
    };
    const tools = Array.isArray(ev.mcp_tools)
      ? (ev.mcp_tools as string[]).join(", ")
      : "—";
    return (
      <div className="ev type-run_started">
        <div className="ev-label">开始运行</div>
        <div className="ev-meta">
          LLM: {prov.mode || "?"}
          {prov.model ? ` · ${prov.model}` : ""} · MCP: {tools}
        </div>
      </div>
    );
  }

  if (t === "start") {
    return (
      <div className="ev type-start muted-ev">
        <span className="ev-label">agent 循环</span>
        <span className="ev-meta"> {String(ev.agent_name || "desktop-agent")}</span>
      </div>
    );
  }

  if (t === "tool_call_start") {
    return (
      <div className="ev type-tool_call_start">
        <div className="ev-label">调用工具</div>
        <code>{String(ev.name || "")}</code>
        {ev.arguments ? (
          <pre className="ev-pre">{String(ev.arguments)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "tool_call_end") {
    const err = Boolean(ev.error);
    return (
      <div className={`ev type-tool_call_end${err ? " type-error" : ""}`}>
        <div className="ev-label">{err ? "工具失败" : "工具结果"}</div>
        <code>{String(ev.name || "")}</code>
        {ev.result_preview ? (
          <pre className="ev-pre">{String(ev.result_preview)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "answer_ready") {
    const report =
      (typeof ev.candidate_text === "string" && ev.candidate_text) ||
      extractAssistantText(ev) ||
      "";
    return (
      <div className="ev type-answer_ready report">
        <div className="ev-label">报告</div>
        {report ? (
          <SimpleMarkdown text={report} />
        ) : (
          <div className="ev-meta">（无 candidate_text）</div>
        )}
        <details className="raw-details">
          <summary>原始事件 JSON</summary>
          <pre className="ev-pre">{JSON.stringify(ev, null, 2)}</pre>
        </details>
      </div>
    );
  }

  if (t === "error") {
    return (
      <div className="ev type-error">
        <div className="ev-label">错误</div>
        <pre className="ev-pre">
          {String(ev.error || ev.message || JSON.stringify(ev))}
        </pre>
      </div>
    );
  }

  if (t === "plan_ready") {
    const plan = (ev.plan || {}) as {
      summary?: string;
      steps?: string[];
      risk_level?: string;
    };
    return (
      <div className="ev type-plan_ready">
        <div className="ev-label">
          执行计划待审 · {String(ev.ui_label || "自批准")}
          {ev.local_approve_allowed === false ? " · 本机不可批（职责分离）" : ""}
        </div>
        <div className="ev-meta">
          risk={String(plan.risk_level || "?")} · plan_id={String(ev.plan_id || "")}
          {ev.timeout_seconds != null
            ? ` · timeout ${String(ev.timeout_seconds)}s → 拒绝`
            : ""}
        </div>
        {plan.summary ? (
          <pre className="ev-pre plan-summary">{String(plan.summary)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "plan_approved") {
    return (
      <div className="ev type-plan_approved">
        <div className="ev-label">
          计划已批准 · {String(ev.ui_label || "自批准")}
          {ev.revised ? "（已改写）" : ""}
        </div>
        {ev.plan_summary ? (
          <pre className="ev-pre">{String(ev.plan_summary)}</pre>
        ) : null}
      </div>
    );
  }

  if (t === "plan_rejected") {
    return (
      <div className="ev type-error">
        <div className="ev-label">计划未批准 — 未执行</div>
        <div className="ev-meta">
          {String(ev.status || "")}: {String(ev.reason || "")}
        </div>
      </div>
    );
  }

  if (t === "privilege_required") {
    return (
      <div className="ev type-plan_ready">
        <div className="ev-label">
          提权申请 · {String(ev.ui_label || "自批准")}
        </div>
        <div className="ev-meta">
          tool={String(ev.tool || "")} · {String(ev.denied_detail || "")}
        </div>
        {ev.plan && typeof ev.plan === "object" && (ev.plan as { summary?: string }).summary ? (
          <pre className="ev-pre plan-summary">
            {String((ev.plan as { summary?: string }).summary)}
          </pre>
        ) : null}
      </div>
    );
  }

  if (t === "privilege_decided") {
    const ok = String(ev.status || "") === "approved";
    return (
      <div className={`ev ${ok ? "type-plan_approved" : "type-error"}`}>
        <div className="ev-label">
          提权{ok ? "已批准 — 重试中" : "未批准"}
        </div>
        <div className="ev-meta">
          {String(ev.status || "")}
          {ev.reason ? `: ${String(ev.reason)}` : ""}
        </div>
      </div>
    );
  }

  if (t === "policy_event") {
    return (
      <div className="ev type-plan_approved">
        <div className="ev-label">policy_event</div>
        <div className="ev-meta">
          {String(ev.policy_event_type || "")} · tool={String(ev.tool || "")}{" "}
          · success={String(ev.success)}
        </div>
      </div>
    );
  }

  if (t === "run_paused") {
    return (
      <div className="ev type-error">
        <div className="ev-label">已暂停</div>
        <div className="ev-meta">
          {String(ev.reason || "")} · messages={String(ev.message_count ?? "")}
          · 可 agent.resume 继续
        </div>
      </div>
    );
  }

  if (t === "run_resumed") {
    return (
      <div className="ev type-plan_approved">
        <div className="ev-label">已恢复</div>
        <div className="ev-meta">messages={String(ev.message_count ?? "")}</div>
      </div>
    );
  }

  // fallback: compact one-liner + collapsible raw
  return (
    <div className={`ev type-${t}`}>
      <div className="ev-label">{t}</div>
      <details className="raw-details">
        <summary>详情</summary>
        <pre className="ev-pre">{JSON.stringify(ev, null, 2)}</pre>
      </details>
    </div>
  );
}

function extractAssistantText(ev: Ev): string {
  const messages = ev.messages;
  if (!Array.isArray(messages)) return "";
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i] as { role?: string; content?: string };
    if (m?.role === "assistant" && m.content && m.content.trim()) {
      return m.content;
    }
  }
  return "";
}

export function App() {
  const { theme, cycleTheme, resolved } = useTheme();
  const [activeView, setActiveView] = useState<ActiveView>("workbench");
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
  const [dataRoot, setDataRoot] = useState<string>("");
  const [providerMode, setProviderMode] = useState<string>("mock");
  const [sandboxImpl, setSandboxImpl] = useState<string>("unknown");
  const [sandboxMode, setSandboxMode] = useState<string>("—");
  const [fvWarning, setFvWarning] = useState<string | null>(null);
  const [tccSummary, setTccSummary] = useState<string>("—");
  const [tccWarning, setTccWarning] = useState<string | null>(null);
  const [tccGuidance, setTccGuidance] = useState<string | null>(null);
  const [mcpTools, setMcpTools] = useState<string[]>([]);
  const [lastSubmitted, setLastSubmitted] = useState<string | null>(null);
  const [pendingPlan, setPendingPlan] = useState<PendingPlan | null>(null);
  const [planEdit, setPlanEdit] = useState("");
  const [runStatus, setRunStatus] = useState<string>("idle");
  const [pausedRunId, setPausedRunId] = useState<string | null>(null);
  const [evidenceHint, setEvidenceHint] = useState<string>("—");
  const [exportPass, setExportPass] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [uninstallPreview, setUninstallPreview] = useState<string | null>(null);
  const [uninstallBusy, setUninstallBusy] = useState(false);
  const [showDataPanel, setShowDataPanel] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const taskRef = useRef(task);
  taskRef.current = task;

  const api = window.cyberguard;

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
        const sb = r?.sandbox as { sandbox_impl?: string; warning?: string | null } | undefined;
        if (sb?.sandbox_impl) setSandboxImpl(sb.sandbox_impl);
        const defaults = r?.policy_defaults as
          | { readonly?: { sandbox_mode?: string } }
          | undefined;
        if (defaults?.readonly?.sandbox_mode) {
          setSandboxMode(String(defaults.readonly.sandbox_mode));
        }
        const fv = r?.filevault as { warning?: string | null } | undefined;
        setFvWarning(fv?.warning || null);
        const tcc = r?.tcc as {
          summary?: string;
          warning?: string | null;
          guidance?: string | null;
          full_disk_access?: boolean | null;
        } | undefined;
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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

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

  const onRun = useCallback(async () => {
    if (!api || running) return;
    // Always read latest textarea value (avoid stale closure / IME edge cases)
    const text = (taskRef.current || task).trim();
    if (!text) return;

    setRunning(true);
    setEvents([]);
    setRunId(null);
    setLastSubmitted(text);
    // Always start a NEW investigation so Run = current textarea, not old session title
    setSessionId(null);
    try {
      const res = await api.run(text, tier, undefined);
      const sid =
        (res?.result as { session_id?: string } | undefined)?.session_id ||
        null;
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
        // Prefill composer with last user_task so you see what that run used
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

  useEffect(() => {
    if (!api?.onOpenDataPanel) return;
    return api.onOpenDataPanel(() => setShowDataPanel(true));
  }, [api]);

  const statusLabel = useMemo(() => {
    if (!api) return "no preload (open via Electron)";
    if (pingOk === null) return "connecting…";
    return pingOk ? "sidecar online" : "sidecar offline";
  }, [api, pingOk]);

  return (
    <div className="app">
      <header className="chrome">
        <div className="chrome-left">
          <div className="chrome-brand">
            <span className="chrome-mark" aria-hidden />
            CyberGuard
          </div>
          <nav className="chrome-nav" aria-label="Primary">
            <button
              type="button"
              className={`nav-tab${activeView === "workbench" ? " active" : ""}`}
              onClick={() => setActiveView("workbench")}
            >
              Workbench
            </button>
            <button
              type="button"
              className={`nav-tab${activeView === "evidence" ? " active" : ""}`}
              onClick={() => setActiveView("evidence")}
            >
              Evidence
            </button>
            <button
              type="button"
              className={`nav-tab${activeView === "settings" ? " active" : ""}`}
              onClick={() => setActiveView("settings")}
            >
              Settings
            </button>
          </nav>
        </div>
        <div className="chrome-right">
          <button
            type="button"
            className="chrome-icon-btn"
            onClick={cycleTheme}
            title={`Theme: ${theme} (${resolved})`}
          >
            {resolved === "dark" ? "Dark" : "Light"}
            {theme === "system" ? " · Auto" : ""}
          </button>
        </div>
      </header>
      <div className="banner">
        <strong>Development build (not notarized)</strong> — not for distribution.
        Plan Mode uses <em>自批准</em> (approval_type=self) — not segregation-of-duties.
        Timeout = reject. LLM: <code>{providerMode}</code>. Local hash chain ≠ WORM.
      </div>
      {pendingPlan && activeView === "workbench" && (
        <div className="plan-panel">
          <div className="plan-panel-header">
            <strong>Plan Mode · {pendingPlan.ui_label || "自批准"}</strong>
            <span className="ev-meta">
              {pendingPlan.local_approve_allowed
                ? `超时 ${pendingPlan.timeout_seconds ?? 300}s → 拒绝`
                : "本机无批准按钮（职责分离 — 须服务端审批）"}
            </span>
          </div>
          <div className="ev-meta">
            risk={String(pendingPlan.plan?.risk_level || "?")} ·{" "}
            {pendingPlan.plan_id}
          </div>
          <textarea
            className="plan-edit"
            value={planEdit}
            onChange={(e) => setPlanEdit(e.target.value)}
            rows={8}
            disabled={!pendingPlan.local_approve_allowed}
            aria-label="execution plan"
          />
          <div className="plan-actions">
            {pendingPlan.local_approve_allowed ? (
              <>
                <button type="button" className="btn-approve" onClick={onPlanApprove}>
                  自批准并执行
                </button>
                <button type="button" className="btn-reject" onClick={onPlanReject}>
                  拒绝
                </button>
              </>
            ) : (
              <span className="ev-meta">等待服务端审批…</span>
            )}
          </div>
        </div>
      )}
      {fvWarning && (
        <div className="banner" style={{ background: "#7f1d1d", color: "#fecaca" }}>
          <strong>FileVault:</strong> {fvWarning}
        </div>
      )}
      {tccWarning && (
        <div className="banner" style={{ background: "#7c2d12", color: "#fed7aa" }}>
          <strong>TCC:</strong> {tccWarning}
          {tccGuidance ? (
            <div style={{ marginTop: 4, opacity: 0.9, fontSize: 12 }}>{tccGuidance}</div>
          ) : null}
        </div>
      )}

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
        <span title="Evidence browser items (read-only + sha256)">{evidenceHint}</span>
        <span>ports: none (JSONL stdio)</span>
      </div>

      {activeView === "workbench" && (
      <div className="workbench view-enter">
        <div className="col">
          <h2>Sessions</h2>
          <div className="col-body session-list">
            <button
              type="button"
              className={!sessionId ? "active" : ""}
              onClick={onNewInvestigation}
            >
              + New investigation
            </button>
            {sessions.map((s) => (
              <button
                key={s.session_id}
                type="button"
                className={sessionId === s.session_id ? "active" : ""}
                onClick={() => onSelectSession(s.session_id)}
              >
                {s.title || s.session_id.slice(0, 8)}
                <div style={{ color: "var(--muted)", fontSize: 11 }}>
                  {s.event_count} events · {s.tier}
                </div>
              </button>
            ))}
            {sessions.length === 0 && (
              <p style={{ color: "var(--muted)", fontSize: 12 }}>
                No local sessions yet. Type a task below and click Run.
              </p>
            )}
          </div>
        </div>

        <div className="col">
          <h2>Execution</h2>
          <div className="col-body">
            {lastSubmitted && (
              <div className="submitted-banner">
                本次提交：<strong>{lastSubmitted}</strong>
              </div>
            )}
            <div className="timeline">
              {events.length === 0 && (
                <div className="ev" style={{ color: "var(--muted)" }}>
                  在下方输入任务后点 <strong>Run</strong>。工具调用与报告会显示在这里。
                </div>
              )}
              {events.map((ev, i) => (
                <EventCard key={i} ev={ev} />
              ))}
              <div ref={bottomRef} />
            </div>
          </div>
          <div className="composer">
            <textarea
              value={task}
              onChange={(e) => setTask(e.target.value)}
              onKeyDown={(e) => {
                // Cmd/Ctrl+Enter to run
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  void onRun();
                }
              }}
              placeholder="在这里输入任务，例如：这批告警里哪些值得优先处理？给出理由与建议动作。"
              disabled={running}
            />
            <div className="row">
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value as Tier)}
                disabled={running}
              >
                <option value="readonly">readonly（无本机 Exec）</option>
                <option value="full">full（本机工具仍 mock）</option>
              </select>
              <button
                className="primary"
                type="button"
                onClick={() => void onRun()}
                disabled={!api || running || !task.trim()}
              >
                {running ? "Running…" : "Run"}
              </button>
              <button
                className="secondary"
                type="button"
                onClick={() => void onAbort()}
                disabled={!running || !runId}
              >
                Abort
              </button>
            </div>
            <div className="hint">
              Run 始终使用<strong>上方输入框当前文字</strong>（新建调查，不沿用旧会话标题）。
              ⌘/Ctrl+Enter 也可运行。
            </div>
            <div className="row">
              <input
                style={{
                  flex: 1,
                  background: "#0b1220",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  borderRadius: 8,
                  padding: "8px 10px",
                }}
                value={steerText}
                onChange={(e) => setSteerText(e.target.value)}
                placeholder="运行中途补充说明（Steer）…"
                disabled={!running || !runId}
              />
              <button
                className="secondary"
                type="button"
                onClick={() => void onSteer()}
                disabled={!running || !runId || !steerText.trim()}
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
              <span>{String(caps?.has_read ?? "—")}</span>
              <span>real_read</span>
              <span>{String(caps?.real_read ?? "—")}</span>
              <span>real_edit</span>
              <span>{String(caps?.real_edit ?? "—")}</span>
              <span>real_exec</span>
              <span>{String(caps?.real_exec ?? "—")}</span>
              <span>has_exec</span>
              <span>{String(caps?.has_exec ?? "—")}</span>
              <span>has_edit</span>
              <span>{String(caps?.has_edit ?? "—")}</span>
              <span>run_id</span>
              <span style={{ fontFamily: "monospace", fontSize: 11 }}>
                {runId ?? "—"}
              </span>
              <span>session_id</span>
              <span style={{ fontFamily: "monospace", fontSize: 11 }}>
                {sessionId ?? "—"}
              </span>
              <span>data_root</span>
              <span style={{ fontFamily: "monospace", fontSize: 10 }}>
                {dataRoot || "—"}
              </span>
            </div>
            <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 16 }}>
              Readonly 档不暴露本机 Exec。MCP 来自{" "}
              <code>mcp_servers.json</code>。
            </p>
            {mcpTools.length > 0 && (
              <div style={{ marginTop: 12, fontSize: 12 }}>
                <div style={{ color: "var(--muted)", marginBottom: 6 }}>
                  MCP tools（上次运行）
                </div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {mcpTools.map((n) => (
                    <li key={n} style={{ fontFamily: "monospace", fontSize: 11 }}>
                      {n}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="data-panel">
              <button
                type="button"
                className="secondary data-panel-toggle"
                onClick={() => setShowDataPanel((v) => !v)}
              >
                {showDataPanel ? "▾" : "▸"} Data · Export / Uninstall (M7)
              </button>
              {showDataPanel && (
                <div className="data-panel-body">
                  <div className="data-section">
                    <div className="data-section-title">Encrypted export</div>
                    <p className="data-hint">
                      Sessions / audit / evidence index / episodic. Keys not included.
                      Prefer age when installed; else CGX1 (PBKDF2+Fernet).
                    </p>
                    <input
                      type="password"
                      className="data-input"
                      value={exportPass}
                      onChange={(e) => setExportPass(e.target.value)}
                      placeholder="passphrase (≥8)"
                      autoComplete="new-password"
                      disabled={exportBusy}
                    />
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void onExport()}
                      disabled={exportBusy || !api?.exportEncrypted}
                    >
                      {exportBusy ? "Exporting…" : "Export…"}
                    </button>
                    {exportMsg && (
                      <pre className="data-msg">{exportMsg}</pre>
                    )}
                  </div>
                  <div className="data-section">
                    <div className="data-section-title">Uninstall local data</div>
                    <p className="data-hint">
                      Crypto-shred keys + delete data_root. External evidence listed only.
                      TCC must be removed manually.
                    </p>
                    <div className="row data-actions">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void onUninstallInventory()}
                        disabled={uninstallBusy}
                      >
                        Inventory
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void onUninstallDryRun()}
                        disabled={uninstallBusy}
                      >
                        Dry-run
                      </button>
                      <button
                        type="button"
                        className="btn-reject"
                        onClick={() => void onUninstallExecute()}
                        disabled={uninstallBusy}
                      >
                        Delete data…
                      </button>
                    </div>
                    {uninstallPreview && (
                      <pre className="data-msg">{uninstallPreview}</pre>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      )}

      {activeView === "evidence" && (
        <div className="view-pane view-enter">
          <h1>Evidence</h1>
          <p className="lede">
            只读证据库（sha256 + mount: read-only）。完整 GUI 注册/校验在 P2；
            当前可在工作台任务中通过 sidecar 注册，计数见状态栏。
          </p>
          <div className="settings-card">
            <h3>Catalog</h3>
            <p>
              Status: <span className="pill accent">{evidenceHint}</span>
            </p>
            <p style={{ marginTop: 10 }}>
              Use RPC <code className="mono">evidence.register</code> /{" "}
              <code className="mono">evidence.verify</code> via agent tools, or
              wait for the P2 file picker UI.
            </p>
            <div className="empty-actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="primary"
                onClick={() => setActiveView("workbench")}
              >
                Back to Workbench
              </button>
            </div>
          </div>
        </div>
      )}

      {activeView === "settings" && (
        <div className="view-pane view-enter">
          <h1>Settings</h1>
          <p className="lede">
            完整 LLM / MCP GUI 在 P1。下方为当前状态与数据安全（导出/卸载）。
          </p>
          <div className="settings-grid">
            <div className="settings-card">
              <h3>LLM Provider</h3>
              <p>
                Mode: <strong>{providerMode}</strong> · data_root:{" "}
                <code className="mono" style={{ fontSize: 11 }}>
                  {dataRoot || "—"}
                </code>
              </p>
              <p style={{ marginTop: 8 }}>
                配置文件：
                <code className="mono">provider.json</code> / Keychain。P1
                将提供表单与连通测试。
              </p>
            </div>
            <div className="settings-card">
              <h3>Appearance</h3>
              <p>
                Theme: <strong>{theme}</strong> (resolved{" "}
                <strong>{resolved}</strong>)
              </p>
              <div className="empty-actions" style={{ marginTop: 10 }}>
                <button type="button" className="secondary" onClick={cycleTheme}>
                  Cycle theme (dark → light → system)
                </button>
              </div>
            </div>
            <div className="settings-card">
              <h3>Data &amp; Security</h3>
              <p>加密导出与卸载（M7）。</p>
              <div className="empty-actions" style={{ marginTop: 10 }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setActiveView("workbench");
                    setShowDataPanel(true);
                  }}
                >
                  Open Export / Uninstall panel
                </button>
              </div>
            </div>
            <div className="settings-card">
              <h3>About</h3>
              <p>
                CyberGuard Desktop · development build · not notarized · not for
                distribution. Local hash chain ≠ WORM. 自批准 ≠ 职责分离审批.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="footer">
        CyberGuard Desktop · M7 engineering · not notarized · not for distribution
      </div>
    </div>
  );
}
