import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunProvider, useRun } from "../../state/useRun";
import { SessionsProvider, useSessions } from "../../state/useSessions";

function Wrap({ children }: { children: ReactNode }) {
  return (
    <SessionsProvider>
      <RunProvider>{children}</RunProvider>
    </SessionsProvider>
  );
}

const useBoth = () => ({ run: useRun(), sessions: useSessions() });

const row = (id: string) => ({
  session_id: id,
  title: id,
  tier: "readonly",
  updated_at: 1,
  event_count: 0,
});

describe("run 域订阅 sessionId", () => {
  afterEach(() => {
    delete (window as { cyberguard?: unknown }).cyberguard;
  });

  it("select 触发载入历史时间线，并回填最后一次任务文本", async () => {
    const sessionEvents = vi.fn().mockResolvedValue({
      events: [
        { type: "user_task", task: "旧任务" },
        { type: "answer_ready", text: "结论" },
      ],
    });
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({ sessions: [row("a")] }),
      sessionEvents,
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(useBoth, { wrapper: Wrap });
    await waitFor(() => expect(result.current.sessions.sessions).toHaveLength(1));

    act(() => result.current.sessions.select("a"));

    await waitFor(() => expect(result.current.run.events).toHaveLength(2));
    expect(sessionEvents).toHaveBeenCalledWith("a");
    expect(result.current.run.task).toBe("旧任务");
  });

  it("create 把选中置空后，run 域清空时间线与输入框", async () => {
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({ sessions: [row("a")] }),
      sessionEvents: vi
        .fn()
        .mockResolvedValue({ events: [{ type: "user_task", task: "旧任务" }] }),
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(useBoth, { wrapper: Wrap });
    await waitFor(() => expect(result.current.sessions.sessions).toHaveLength(1));

    act(() => result.current.sessions.select("a"));
    await waitFor(() => expect(result.current.run.events).toHaveLength(1));

    act(() => result.current.sessions.create());
    await waitFor(() => expect(result.current.run.events).toHaveLength(0));
    expect(result.current.run.task).toBe("");
  });

  /**
   * 关键回归点：跑完后 run 会认领新会话 id。若这次 id 变化也触发重载，
   * 磁盘上的历史会冲掉刚跑完、还在屏幕上的这一轮。
   */
  it("跑完认领新会话时不重载历史，本轮时间线保留", async () => {
    const sessionEvents = vi.fn().mockResolvedValue({ events: [] });

    // 事件必须在运行期间流入：预先 dispatch 会把状态置成 running，
    // 导致 run() 因 `if (running) return` 提前退出，测不到认领路径。
    let emitDuringRun: (() => void) | null = null;

    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({ sessions: [] }),
      sessionEvents,
      run: vi.fn().mockImplementation(async () => {
        emitDuringRun?.();
        return { result: { session_id: "fresh" } };
      }),
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(useBoth, { wrapper: Wrap });

    emitDuringRun = () =>
      result.current.run.dispatch({
        type: "event",
        ev: { type: "run_started", run_id: "r-1" },
      });

    act(() => result.current.run.setTask("分诊告警"));

    await act(async () => {
      await result.current.run.run();
    });

    expect(result.current.sessions.sessionId).toBe("fresh");
    // 认领不得触发重载，否则会用磁盘历史冲掉刚跑完的这一轮
    expect(sessionEvents).not.toHaveBeenCalled();
    expect(
      result.current.run.events.some((e) => e.type === "run_started")
    ).toBe(true);
  });
});
