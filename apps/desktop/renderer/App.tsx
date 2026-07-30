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

export function App() {
  const [pingOk, setPingOk] = useState<boolean | null>(null);
  const [tier, setTier] = useState<Tier>("readonly");
  const [caps, setCaps] = useState<Caps | null>(null);
  const [task, setTask] = useState(
    "Triage these sample alerts and list what to look at first."
  );
  const [events, setEvents] = useState<Ev[]>([]);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [steerText, setSteerText] = useState("");
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [dataRoot, setDataRoot] = useState<string>("");
  const bottomRef = useRef<HTMLDivElement>(null);

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
      .then((r) => {
        setPingOk(true);
        if (r?.data_root) setDataRoot(r.data_root);
      })
      .catch(() => setPingOk(false));
    refreshSessions();
  }, [api, refreshSessions]);

  useEffect(() => {
    if (!api) return;
    api.capabilities(tier).then(setCaps).catch(() => setCaps(null));
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
      }
      if (ev.type === "start" && typeof ev.agent_run_id === "string") {
        setRunId(String(ev.agent_run_id));
      }
    });
  }, [api]);

  const onRun = useCallback(async () => {
    if (!api || running) return;
    setRunning(true);
    setEvents([]);
    setRunId(null);
    try {
      const res = await api.run(task, tier, sessionId || undefined);
      const sid =
        (res?.result as { session_id?: string } | undefined)?.session_id ||
        sessionId;
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
  }, [api, task, tier, running, sessionId, refreshSessions]);

  const onSelectSession = useCallback(
    async (sid: string) => {
      if (!api) return;
      setSessionId(sid);
      try {
        const r = await api.sessionEvents(sid);
        setEvents(r.events || []);
      } catch {
        setEvents([]);
      }
    },
    [api]
  );

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
        <strong>M1 development build</strong> — mock LLM/tools only. Sandbox and
        at-rest encryption are <em>not</em> enabled. Do not process real sensitive
        data.
      </div>

      <div className="status-bar">
        <span className={pingOk ? "ok" : "bad"}>● {statusLabel}</span>
        <span>sandbox: none (M1)</span>
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
              onClick={() => {
                setSessionId(null);
                setEvents([]);
              }}
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
                No local sessions yet. Run a task to create JSONL under the
                managed data root.
              </p>
            )}
          </div>
        </div>

        <div className="col">
          <h2>Execution</h2>
          <div className="col-body">
            <div className="timeline">
              {events.length === 0 && (
                <div className="ev" style={{ color: "var(--muted)" }}>
                  Events from the mock agent loop appear here (tool calls,
                  answers, abort).
                </div>
              )}
              {events.map((ev, i) => (
                <div key={i} className={`ev type-${ev.type}`}>
                  <strong>{ev.type}</strong>
                  {"\n"}
                  {JSON.stringify(ev, null, 2)}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </div>
          <div className="composer">
            <textarea
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Task for the mock agent…"
              disabled={running}
            />
            <div className="row">
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value as Tier)}
                disabled={running}
              >
                <option value="readonly">readonly (no ExecOperations)</option>
                <option value="full">full (mock exec only)</option>
              </select>
              <button
                className="primary"
                type="button"
                onClick={onRun}
                disabled={!api || running || !task.trim()}
              >
                {running ? "Running…" : "Run"}
              </button>
              <button
                className="secondary"
                type="button"
                onClick={onAbort}
                disabled={!running || !runId}
              >
                Abort
              </button>
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
                placeholder="Steer mid-run (user message)…"
                disabled={!running || !runId}
              />
              <button
                className="secondary"
                type="button"
                onClick={onSteer}
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
              Readonly tier must not expose local <code>ExecOperations</code>{" "}
              (M1 exit criterion). Full tier still uses mock exec — no host I/O
              until M2. Sessions are JSONL under the managed data root (not{" "}
              <code>/tmp</code>).
            </p>
          </div>
        </div>
      </div>

      <div className="footer">
        CyberGuard Desktop · M1 · mock loop · tray + local sessions · not for
        distribution
      </div>
    </div>
  );
}
