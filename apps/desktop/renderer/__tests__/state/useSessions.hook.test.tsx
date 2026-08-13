import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionsProvider, useSessions } from "../../state/useSessions";

function Wrap({ children }: { children: ReactNode }) {
  return <SessionsProvider>{children}</SessionsProvider>;
}

const rowA = {
  session_id: "a",
  title: "A",
  tier: "readonly",
  updated_at: 1,
  event_count: 0,
};

describe("SessionsProvider", () => {
  afterEach(() => {
    delete (window as { cyberguard?: unknown }).cyberguard;
  });

  it("不依赖 run 域：select / adopt 都不拉 sessionEvents", async () => {
    const sessionEvents = vi.fn();
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({ sessions: [rowA] }),
      sessionEvents,
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(() => useSessions(), { wrapper: Wrap });
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));

    act(() => result.current.select("a"));
    expect(result.current.sessionId).toBe("a");

    act(() => result.current.adopt("new-sid"));
    expect(result.current.sessionId).toBe("new-sid");

    // 载入历史是 run 域的职责，会话域一次都不该碰这个 API
    expect(sessionEvents).not.toHaveBeenCalled();
  });

  it("create 把选中置空（run 域据此清时间线）", async () => {
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({ sessions: [rowA] }),
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(() => useSessions(), { wrapper: Wrap });
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));

    act(() => result.current.select("a"));
    act(() => result.current.create());
    expect(result.current.sessionId).toBe(null);
  });

  it("remove 失败不 dispatch removed、返回 false", async () => {
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({ sessions: [rowA] }),
      deleteSession: vi.fn().mockRejectedValue(new Error("boom")),
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(() => useSessions(), { wrapper: Wrap });
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));

    let ok = true;
    await act(async () => {
      ok = await result.current.remove("a");
    });
    expect(ok).toBe(false);
    expect(result.current.sessions).toHaveLength(1);
  });

  it("删掉当前选中的会话后，sessionId 收敛为 null", async () => {
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({ sessions: [rowA] }),
      deleteSession: vi.fn().mockResolvedValue({ ok: true }),
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(() => useSessions(), { wrapper: Wrap });
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));

    act(() => result.current.select("a"));
    await act(async () => {
      await result.current.remove("a");
    });
    expect(result.current.sessionId).toBe(null);
  });
});
