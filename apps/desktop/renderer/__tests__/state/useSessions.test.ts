import { describe, expect, it } from "vitest";
import type { SessionRow } from "../../lib/types";
import {
  initialSessionsState,
  sessionsReducer,
} from "../../state/sessionsReducer";

const row = (id: string): SessionRow => ({
  session_id: id,
  title: `会话 ${id}`,
  tier: "readonly",
  updated_at: 1,
  event_count: 0,
});

describe("sessionsReducer", () => {
  it("setList 写入列表且不动当前选中", () => {
    const base = { ...initialSessionsState, sessionId: "a" };
    const s = sessionsReducer(base, { type: "setList", sessions: [row("a")] });
    expect(s.sessions).toHaveLength(1);
    expect(s.sessionId).toBe("a");
  });

  it("select 切换当前会话", () => {
    const s = sessionsReducer(initialSessionsState, {
      type: "select",
      sessionId: "b",
    });
    expect(s.sessionId).toBe("b");
  });

  it("删除当前选中的会话时，sessionId 收敛为 null", () => {
    const base = {
      sessions: [row("a"), row("b")],
      sessionId: "a",
    };
    const s = sessionsReducer(base, { type: "removed", sessionId: "a" });
    expect(s.sessionId).toBe(null);
    expect(s.sessions.map((x) => x.session_id)).toEqual(["b"]);
  });

  it("删除非当前会话时，sessionId 不变", () => {
    const base = {
      sessions: [row("a"), row("b")],
      sessionId: "a",
    };
    const s = sessionsReducer(base, { type: "removed", sessionId: "b" });
    expect(s.sessionId).toBe("a");
    expect(s.sessions.map((x) => x.session_id)).toEqual(["a"]);
  });

  it("clearAll 清空列表与选中（卸载后使用）", () => {
    const base = { sessions: [row("a")], sessionId: "a" };
    expect(sessionsReducer(base, { type: "clearAll" })).toEqual(
      initialSessionsState
    );
  });
});
