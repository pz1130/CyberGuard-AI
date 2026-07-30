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

declare global {
  interface Window {
    cyberguard?: {
      ping: () => Promise<{ ok: boolean }>;
      capabilities: (tier: Tier) => Promise<Caps>;
      run: (
        task: string,
        tier: Tier
      ) => Promise<{ result: unknown; events: Ev[] }>;
      abort: (runId: string) => Promise<{ ok: boolean }>;
      steer: (runId: string, message: string) => Promise<{ ok: boolean }>;
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
  const bottomRef = useRef<HTMLDivElement>(null);

  const api = window.cyberguard;

  useEffect(() => {
    if (!api) {
      setPingOk(false);
      return;
    }
    api
      .ping()
      .then(() => setPingOk(true))
      .catch(() => setPingOk(false));
  }, [api]);

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
      await api.run(task, tier);
    } catch (e) {
      setEvents((prev) => [
        ...prev,
        { type: "error", error: String(e), status: "failed" },
      ]);
    } finally {
      setRunning(false);
    }
  }, [api, task, tier, running]);

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
            <button className="active" type="button">
              Investigation · mock
            </button>
            <p style={{ color: "var(--muted)", fontSize: 12 }}>
              Session tree is a skeleton in M1. Real local JSONL sessions land
              later.
            </p>
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
            </div>
            <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 16 }}>
              Readonly tier must not expose local <code>ExecOperations</code>{" "}
              (M1 exit criterion). Full tier still uses mock exec — no host I/O
              until M2.
            </p>
          </div>
        </div>
      </div>

      <div className="footer">
        CyberGuard Desktop · M1 skeleton · agent-core mock loop · not for
        distribution
      </div>
    </div>
  );
}
