import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import type { Ev } from "../lib/types";
import {
  initialSessionsState,
  sessionsReducer,
  type SessionsState,
} from "./sessionsReducer";

/**
 * 会话域只管「有哪些会话、当前选中哪个」，**不依赖 run 域**。
 *
 * 「按 sessionId 载入时间线」的职责归 run 域（时间线是它的状态），
 * 由 run 侧订阅 sessionId 变化来做。方向因此是单向的 run → sessions，
 * 不再需要 ref 桥接把两边的回调对穿。
 */
export type SessionsContextValue = SessionsState & {
  refresh: () => void;
  /** 只改选中；载入历史由 run 域订阅 sessionId 完成 */
  select: (id: string) => void;
  /** 跑完后认领新会话。与 select 的区别由 run 域用「已应用的 id」来消解 */
  adopt: (sessionId: string) => void;
  create: () => void;
  /** 失败返回 false，不抛、不 dispatch removed */
  remove: (id: string) => Promise<boolean>;
  clearAll: () => void;
};

const SessionsContext = createContext<SessionsContextValue | null>(null);

export function SessionsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(sessionsReducer, initialSessionsState);
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const refresh = useCallback(() => {
    if (!api?.listSessions) return;
    api
      .listSessions()
      .then((r) => dispatch({ type: "setList", sessions: r.sessions || [] }))
      .catch(() => dispatch({ type: "setList", sessions: [] }));
  }, [api]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const select = useCallback((sid: string) => {
    dispatch({ type: "select", sessionId: sid });
  }, []);

  // 选中置空即「新调查」；run 域订阅到 null 会自行清空时间线
  const create = useCallback(() => {
    dispatch({ type: "select", sessionId: null });
  }, []);

  const adopt = useCallback((sessionId: string) => {
    dispatch({ type: "select", sessionId });
  }, []);

  const remove = useCallback(
    async (sid: string): Promise<boolean> => {
      if (!api?.deleteSession) return false;
      try {
        await api.deleteSession(sid);
      } catch {
        return false;
      }
      // 删的是当前会话时，reducer 会把 sessionId 收敛为 null，
      // run 域随之清空时间线，这里不需要再显式通知
      dispatch({ type: "removed", sessionId: sid });
      refresh();
      return true;
    },
    [api, refresh]
  );

  const clearAll = useCallback(() => {
    dispatch({ type: "clearAll" });
  }, []);

  const value = useMemo<SessionsContextValue>(
    () => ({ ...state, refresh, select, adopt, create, remove, clearAll }),
    [state, refresh, select, adopt, create, remove, clearAll]
  );

  return (
    <SessionsContext.Provider value={value}>
      {children}
    </SessionsContext.Provider>
  );
}

export function useSessions(): SessionsContextValue {
  const ctx = useContext(SessionsContext);
  if (!ctx) throw new Error("useSessions must be used within SessionsProvider");
  return ctx;
}
