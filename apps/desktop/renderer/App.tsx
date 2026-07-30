import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Tier = "readonly" | "full";

type Caps = {
  tier: string;
  has_read: boolean;
  has_exec: boolean;
  has_edit: boolean;
  mock?: boolean;
};

type Ev = { type: string; [k: string]: unknown };

type SessionRow = {
  session_id: string;
  title: string;
  tier: string;
  updated_at: number;
  event_count: number;
};

declare global {
  interface Window {
    cyberguard?: {
      ping: () => Promise<{ ok: boolean; data_root?: string }>;
      capabilities: (tier: Tier) => Promise<Caps>;
      run: (
        task: string,
        tier: Tier,
        sessionId?: string
      ) => Promise<{ result: unknown; events: Ev[] }>;
      abort: (runId: string) => Promise<{ ok: boolean }>;
      steer: (runId: string, message: string) => Promise<{ ok: boolean }>;
      listSessions: () => Promise<{ sessions: SessionRow[] }>;
      createSession: (
        title: string,
        tier: Tier
      ) => Promise<{ session_id: string; title: string }>;
      sessionEvents: (
        sessionId: string
      ) => Promise<{ events: Ev[] }>;
      onEvent: (handler: (ev: Ev) => void) => () => void;
    };
  }
}

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
  const [mcpTools, setMcpTools] = useState<string[]>([]);
  const [lastSubmitted, setLastSubmitted] = useState<string | null>(null);
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
        const tools = ev.mcp_tools;
        if (Array.isArray(tools)) {
          setMcpTools(tools.map(String));
        }
      }
      if (ev.type === "start" && typeof ev.agent_run_id === "string") {
        setRunId(String(ev.agent_run_id));
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
  }, [api, runId]);

  const onSteer = useCallback(async () => {
    if (!api || !runId || !steerText.trim()) return;
    await api.steer(runId, steerText.trim());
    setSteerText("");
  }, [api, runId, steerText]);

  const statusLabel = useMemo(() => {
    if (!api) return "no preload (open via Electron)";
    if (pingOk === null) return "connecting…";
    return pingOk ? "sidecar online" : "sidecar offline";
  }, [api, pingOk]);

  return (
    <div className="app">
      <div className="banner">
        <strong>M1/M1.5 development build</strong> — sandbox and at-rest encryption
        are <em>not</em> enabled. Do not process real sensitive production data.
        LLM: <code>{providerMode}</code>.
      </div>
      {fvWarning && (
        <div className="banner" style={{ background: "#7f1d1d", color: "#fecaca" }}>
          <strong>FileVault:</strong> {fvWarning}
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
        <span>llm: {providerMode}</span>
        <span>tier: {tier}</span>
        <span>ports: none (JSONL stdio)</span>
      </div>

      <div className="workbench">
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
              <code>mcp_servers.json</code>。破坏性主机工具等 M2 沙箱。
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
          </div>
        </div>
      </div>

      <div className="footer">
        CyberGuard Desktop · M1.5 · live LLM path · not for distribution
      </div>
    </div>
  );
}
