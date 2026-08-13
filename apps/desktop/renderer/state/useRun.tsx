import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Ev, Tier } from "../lib/types";
import {
  initialRunState,
  runReducer,
  type RunAction,
  type RunState,
} from "./runReducer";

export type RunContextValue = RunState & {
  tier: Tier;
  setTier: (t: Tier) => void;
  task: string;
  setTask: (v: string) => void;
  steerText: string;
  setSteerText: (v: string) => void;
  running: boolean;
  paused: boolean;
  run: () => Promise<void>;
  abort: () => Promise<void>;
  resume: () => Promise<void>;
  steer: () => Promise<void>;
  loadEvents: (events: Ev[]) => void;
  reset: () => void;
  dispatch: (a: RunAction) => void;
};

const RunContext = createContext<RunContextValue | null>(null);

export type RunProviderProps = {
  children: ReactNode;
  /** 运行成功后回调，用于让 sessions 域刷新列表并选中新会话 */
  onRunSettled?: (sessionId: string | null) => void;
};

export function RunProvider({ children, onRunSettled }: RunProviderProps) {
  const [state, dispatch] = useReducer(runReducer, initialRunState);
  const [tier, setTier] = useState<Tier>("readonly");
  const [task, setTask] = useState("");
  const [steerText, setSteerText] = useState("");

  const taskRef = useRef(task);
  taskRef.current = task;

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;
  const running = state.status === "running";
  const paused = state.status === "paused";

  const run = useCallback(async () => {
    if (!api || running) return;
    const text = taskRef.current.trim();
    if (!text) return;

    dispatch({ type: "submit", text });
    try {
      const res = await api.run(text, tier, undefined);
      const sid =
        (res?.result as { session_id?: string } | undefined)?.session_id || null;
      onRunSettled?.(sid);
      dispatch({ type: "settled" });
    } catch (e) {
      dispatch({ type: "failed", error: String(e) });
    }
  }, [api, tier, running, onRunSettled]);

  const abort = useCallback(async () => {
    if (!api || !state.runId) return;
    await api.abort(state.runId);
  }, [api, state.runId]);

  const resume = useCallback(async () => {
    const rid = state.pausedRunId || state.runId;
    if (!api?.resume || !rid) return;
    try {
      await api.resume(rid);
    } catch (e) {
      dispatch({ type: "failed", error: `resume failed: ${e}` });
    }
  }, [api, state.pausedRunId, state.runId]);

  const steer = useCallback(async () => {
    if (!api || !state.runId || !steerText.trim()) return;
    await api.steer(state.runId, steerText.trim());
    setSteerText("");
  }, [api, state.runId, steerText]);

  const loadEvents = useCallback((events: Ev[]) => {
    dispatch({ type: "loadEvents", events });
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: "reset" });
    setTask("");
  }, []);

  const value = useMemo<RunContextValue>(
    () => ({
      ...state,
      tier,
      setTier,
      task,
      setTask,
      steerText,
      setSteerText,
      running,
      paused,
      run,
      abort,
      resume,
      steer,
      loadEvents,
      reset,
      dispatch,
    }),
    [
      state,
      tier,
      task,
      steerText,
      running,
      paused,
      run,
      abort,
      resume,
      steer,
      loadEvents,
      reset,
    ]
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRun must be used within RunProvider");
  return ctx;
}
