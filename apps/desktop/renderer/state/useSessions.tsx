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

export type SessionsContextValue = SessionsState & {
  refresh: () => void;
  select: (id: string) => Promise<void>;
  create: () => void;
  remove: (id: string) => Promise<void>;
  clearAll: () => void;
};

const SessionsContext = createContext<SessionsContextValue | null>(null);

export type SessionsProviderProps = {
  children: ReactNode;
  /** 选中会话后把历史事件交给 run 域 */
  onEventsLoaded: (events: Ev[], lastTask: string | null) => void;
  /** 新建调查时清空 run 域 */
  onReset: () => void;
};

export function SessionsProvider({
  children,
  onEventsLoaded,
  onReset,
}: SessionsProviderProps) {
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

  const select = useCallback(
    async (sid: string) => {
      if (!api) return;
      dispatch({ type: "select", sessionId: sid });
      try {
        const r = await api.sessionEvents(sid);
        const evs = r.events || [];
        let lastTask: string | null = null;
        for (let i = evs.length - 1; i >= 0; i--) {
          if (evs[i].type === "user_task" && typeof evs[i].task === "string") {
            lastTask = String(evs[i].task);
            break;
          }
        }
        onEventsLoaded(evs, lastTask);
      } catch {
        onEventsLoaded([], null);
      }
    },
    [api, onEventsLoaded]
  );

  const create = useCallback(() => {
    dispatch({ type: "select", sessionId: null });
    onReset();
  }, [onReset]);

  const remove = useCallback(
    async (sid: string) => {
      if (!api?.deleteSession) return;
      await api.deleteSession(sid);
      dispatch({ type: "removed", sessionId: sid });
      if (state.sessionId === sid) onReset();
      refresh();
    },
    [api, state.sessionId, onReset, refresh]
  );

  const clearAll = useCallback(() => {
    dispatch({ type: "clearAll" });
    onReset();
  }, [onReset]);

  const value = useMemo<SessionsContextValue>(
    () => ({ ...state, refresh, select, create, remove, clearAll }),
    [state, refresh, select, create, remove, clearAll]
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
