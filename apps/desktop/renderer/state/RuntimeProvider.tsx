import { useCallback, useEffect, useRef, type ReactNode } from "react";
import type { Ev } from "../lib/types";
import { EnvironmentProvider, useEnvironment } from "./useEnvironment";
import { PlanProvider, usePlan } from "./usePlan";
import { RunProvider, useRun } from "./useRun";
import { SessionsProvider, useSessions } from "./useSessions";
import { StreamProvider, useStreamDispatch } from "./useStream";

/**
 * 订阅一次 IPC 事件流，扇出给各域。
 * 必须挂在所有 Provider 内部（要用到各域的 ingest）。
 */
function EventFanout({ children }: { children: ReactNode }) {
  const run = useRun();
  const plan = usePlan();
  const env = useEnvironment();
  const streamIngest = useStreamDispatch();

  // 用 ref 持有最新回调，避免因回调引用变化反复解绑/重订阅 IPC
  const sinks = useRef({ run, plan, env, streamIngest });
  sinks.current = { run, plan, env, streamIngest };

  useEffect(() => {
    const api = typeof window !== "undefined" ? window.cyberguard : undefined;
    if (!api) return;
    return api.onEvent((ev: Ev) => {
      const s = sinks.current;
      s.streamIngest(ev);
      s.run.dispatch({ type: "event", ev });
      s.plan.ingest(ev);
      s.env.ingest(ev);
    });
  }, []);

  return <>{children}</>;
}

/** 把 sessions 与 run 两个域接起来（选中会话 → 载入事件；新建 → 清空） */
function SessionsBridge({ children }: { children: ReactNode }) {
  const run = useRun();

  const onEventsLoaded = useCallback(
    (events: Ev[], lastTask: string | null) => {
      run.loadEvents(events);
      if (lastTask) run.setTask(lastTask);
    },
    [run]
  );

  const onReset = useCallback(() => {
    run.reset();
  }, [run]);

  return (
    <SessionsProvider onEventsLoaded={onEventsLoaded} onReset={onReset}>
      {children}
    </SessionsProvider>
  );
}

/** run 域需要在跑完后刷新会话列表，但 SessionsProvider 在其内层 —— 用事件回调桥接 */
function RunLayer({ children }: { children: ReactNode }) {
  const pendingRefresh = useRef<(() => void) | null>(null);

  const onRunSettled = useCallback(() => {
    pendingRefresh.current?.();
  }, []);

  return (
    <RunProvider onRunSettled={onRunSettled}>
      <SessionsBridge>
        <RefreshRegistrar target={pendingRefresh} />
        {children}
      </SessionsBridge>
    </RunProvider>
  );
}

function RefreshRegistrar({
  target,
}: {
  target: React.MutableRefObject<(() => void) | null>;
}) {
  const sessions = useSessions();
  target.current = sessions.refresh;
  return null;
}

function PlanLayer({ children }: { children: ReactNode }) {
  const run = useRun();
  const onError = useCallback(
    (message: string) => run.dispatch({ type: "failed", error: message }),
    [run]
  );
  return <PlanProvider onError={onError}>{children}</PlanProvider>;
}

function EnvLayer({ children }: { children: ReactNode }) {
  const run = useRun();
  return <EnvironmentProvider tier={run.tier}>{children}</EnvironmentProvider>;
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  return (
    <StreamProvider>
      <RunLayer>
        <PlanLayer>
          <EnvLayer>
            <EventFanout>{children}</EventFanout>
          </EnvLayer>
        </PlanLayer>
      </RunLayer>
    </StreamProvider>
  );
}
