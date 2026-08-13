import { useCallback, useEffect, useRef, type ReactNode } from "react";
import type { Ev } from "../lib/types";
import { EnvironmentProvider, useEnvironment } from "./useEnvironment";
import { PlanProvider, usePlan } from "./usePlan";
import { RunProvider, useRun } from "./useRun";
import { SessionsProvider } from "./useSessions";
import { StreamProvider, useStreamDispatch } from "./useStream";

/**
 * 域之间的依赖是单向的，嵌套顺序即依赖顺序：
 *
 *   stream    ← 无依赖
 *   sessions  ← 无依赖
 *   run       ← 读 sessions（当前 sessionId、跑完刷新列表）
 *   plan      ← 出错时写 run 的时间线
 *   env       ← 读 run 的档位
 *
 * 早先 sessions 与 run 互相依赖（sessions 选中后要把历史推给 run，
 * run 跑完要让 sessions 刷新），只能靠一个在 render 阶段写 ref 的
 * 注册组件对穿。把「按 sessionId 载入时间线」归还给 run 域之后，
 * 环被拆开，注册组件和 ref 一并删掉。
 */

/** 订阅一次 IPC 事件流，扇出给各域 */
function EventFanout({ children }: { children: ReactNode }) {
  const run = useRun();
  const plan = usePlan();
  const env = useEnvironment();
  const streamIngest = useStreamDispatch();

  // 用 ref 持有最新回调，避免因回调引用变化反复解绑/重订阅 IPC。
  // 写入放 effect 里：ref 只在 IPC 异步回调中被读，render 阶段写没有必要。
  const sinks = useRef({ run, plan, env, streamIngest });
  useEffect(() => {
    sinks.current = { run, plan, env, streamIngest };
  }, [run, plan, env, streamIngest]);

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
  return (
    <EnvironmentProvider
      tier={run.tier}
      onPausedRuns={(id) =>
        run.dispatch({ type: "event", ev: { type: "run_paused", run_id: id } })
      }
    >
      {children}
    </EnvironmentProvider>
  );
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  return (
    <StreamProvider>
      <SessionsProvider>
        <RunProvider>
          <PlanLayer>
            <EnvLayer>
              <EventFanout>{children}</EventFanout>
            </EnvLayer>
          </PlanLayer>
        </RunProvider>
      </SessionsProvider>
    </StreamProvider>
  );
}
