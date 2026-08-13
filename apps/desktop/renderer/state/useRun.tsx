import {
  createContext,
  useCallback,
  useEffect,
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
import { useSessions } from "./useSessions";

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

/**
 * run 域持有时间线，因此也负责「按当前 sessionId 把历史载进来」。
 * 它单向依赖 sessions 域（读 sessionId、跑完后刷新列表），
 * sessions 域不反过来依赖它。
 */
export function RunProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(runReducer, initialRunState);
  const [tier, setTier] = useState<Tier>("readonly");
  const [task, setTask] = useState("");
  const [steerText, setSteerText] = useState("");

  // run() 读 taskRef 而非 task，好让它的引用不随每次按键变化。
  // 只在提交时（用户事件）被读，effect 写入足够及时。
  const taskRef = useRef(task);
  useEffect(() => {
    taskRef.current = task;
  }, [task]);

  const { sessionId, refresh, adopt } = useSessions();

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;
  const running = state.status === "running";
  const paused = state.status === "paused";

  /**
   * 已经把时间线对齐到哪个 sessionId。
   * 跑完认领新会话时先写这里再 adopt，下面的 effect 就会跳过重载，
   * 不会用磁盘上的历史冲掉刚跑完、还在屏幕上的那一轮。
   */
  const appliedSessionRef = useRef<string | null>(null);

  useEffect(() => {
    if (sessionId === appliedSessionRef.current) return;
    appliedSessionRef.current = sessionId;

    if (sessionId === null) {
      dispatch({ type: "reset" });
      setTask("");
      return;
    }
    if (!api) return;

    let stale = false;
    void api
      .sessionEvents(sessionId)
      .then((r) => {
        if (stale) return;
        const evs = r.events || [];
        dispatch({ type: "loadEvents", events: evs });
        for (let i = evs.length - 1; i >= 0; i--) {
          if (evs[i].type === "user_task" && typeof evs[i].task === "string") {
            setTask(String(evs[i].task));
            break;
          }
        }
      })
      .catch(() => {
        if (!stale) dispatch({ type: "loadEvents", events: [] });
      });

    // 快速连点会话时，丢弃过期请求的结果
    return () => {
      stale = true;
    };
  }, [sessionId, api]);

  const run = useCallback(async () => {
    if (!api || running) return;
    const text = taskRef.current.trim();
    if (!text) return;

    dispatch({ type: "submit", text });
    try {
      const res = await api.run(text, tier, undefined);
      const sid =
        (res?.result as { session_id?: string } | undefined)?.session_id || null;
      if (sid) {
        // 先标记已对齐，再认领 —— 否则上面的 effect 会重载并冲掉本轮时间线
        appliedSessionRef.current = sid;
        adopt(sid);
      }
      refresh();
      dispatch({ type: "settled" });
    } catch (e) {
      dispatch({ type: "failed", error: String(e) });
    }
  }, [api, tier, running, adopt, refresh]);

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
