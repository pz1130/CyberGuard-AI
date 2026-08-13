import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionsProvider, useSessions } from "../../state/useSessions";

function wrapperFor(onEventsLoaded = vi.fn(), onReset = vi.fn()) {
  return function Wrap({ children }: { children: ReactNode }) {
    return (
      <SessionsProvider onEventsLoaded={onEventsLoaded} onReset={onReset}>
        {children}
      </SessionsProvider>
    );
  };
}

describe("SessionsProvider adopt / remove", () => {
  afterEach(() => {
    delete (window as { cyberguard?: unknown }).cyberguard;
  });

  it("adopt 只选中，不拉 sessionEvents / onEventsLoaded", async () => {
    const sessionEvents = vi.fn();
    const onEventsLoaded = vi.fn();
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({
        sessions: [
          {
            session_id: "new-sid",
            title: "新",
            tier: "readonly",
            updated_at: 1,
            event_count: 0,
          },
        ],
      }),
      sessionEvents,
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(() => useSessions(), {
      wrapper: wrapperFor(onEventsLoaded),
    });
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));

    act(() => {
      result.current.adopt("new-sid");
    });
    expect(result.current.sessionId).toBe("new-sid");
    expect(sessionEvents).not.toHaveBeenCalled();
    expect(onEventsLoaded).not.toHaveBeenCalled();
  });

  it("remove 失败不 dispatch removed、返回 false", async () => {
    const onReset = vi.fn();
    window.cyberguard = {
      listSessions: vi.fn().mockResolvedValue({
        sessions: [
          {
            session_id: "a",
            title: "A",
            tier: "readonly",
            updated_at: 1,
            event_count: 0,
          },
        ],
      }),
      deleteSession: vi.fn().mockRejectedValue(new Error("boom")),
    } as unknown as typeof window.cyberguard;

    const { result } = renderHook(() => useSessions(), {
      wrapper: wrapperFor(vi.fn(), onReset),
    });
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));

    let ok = true;
    await act(async () => {
      ok = await result.current.remove("a");
    });
    expect(ok).toBe(false);
    expect(result.current.sessions).toHaveLength(1);
    expect(onReset).not.toHaveBeenCalled();
  });
});
