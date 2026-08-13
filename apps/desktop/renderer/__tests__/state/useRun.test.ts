import { describe, expect, it } from "vitest";
import {
  initialRunState,
  runReducer,
  type RunState,
} from "../../state/runReducer";

function apply(state: RunState, evs: Array<Record<string, unknown>>): RunState {
  return evs.reduce<RunState>(
    (s, ev) => runReducer(s, { type: "event", ev: ev as never }),
    state
  );
}

describe("runReducer 状态机", () => {
  it("初始为 idle", () => {
    expect(initialRunState.status).toBe("idle");
    expect(initialRunState.runId).toBe(null);
  });

  it("submit 进入 running 并记录 lastSubmitted，同时清空旧事件", () => {
    const dirty = { ...initialRunState, events: [{ type: "old" }] };
    const s = runReducer(dirty, { type: "submit", text: "分诊告警" });
    expect(s.status).toBe("running");
    expect(s.lastSubmitted).toBe("分诊告警");
    expect(s.events).toEqual([]);
  });

  it("run_started 记录 runId 与 mcp_tools", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1", mcp_tools: ["mcp__a", "mcp__b"] },
    ]);
    expect(s.status).toBe("running");
    expect(s.runId).toBe("r-1");
    expect(s.mcpTools).toEqual(["mcp__a", "mcp__b"]);
  });

  it("run_paused → paused 并记录 pausedRunId", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "run_paused", run_id: "r-1" },
    ]);
    expect(s.status).toBe("paused");
    expect(s.pausedRunId).toBe("r-1");
  });

  it("run_resumed → running 并清掉 pausedRunId", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "run_paused", run_id: "r-1" },
      { type: "run_resumed", run_id: "r-1" },
    ]);
    expect(s.status).toBe("running");
    expect(s.pausedRunId).toBe(null);
  });

  it("answer_ready → done", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "answer_ready" },
    ]);
    expect(s.status).toBe("done");
  });

  it("error → failed", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "error", error: "boom" },
    ]);
    expect(s.status).toBe("failed");
  });

  it("状态不由中文显示串驱动：ui_status 不影响 status", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "run_paused", run_id: "r-1", ui_status: "随便什么文案" },
    ]);
    expect(s.status).toBe("paused");
  });

  it("token / token_done 事件不进时间线（由 stream 域处理）", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "token", delta: "abc" },
      { type: "token_done" },
    ]);
    expect(s.events.map((e) => e.type)).toEqual(["run_started"]);
  });

  it("settled 把 running 收敛为 done，但不覆盖 paused", () => {
    const running = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
    ]);
    expect(runReducer(running, { type: "settled" }).status).toBe("done");

    const paused = apply(running, [{ type: "run_paused", run_id: "r-1" }]);
    expect(runReducer(paused, { type: "settled" }).status).toBe("paused");
  });

  it("failed 动作把错误写进时间线", () => {
    const s = runReducer(initialRunState, { type: "failed", error: "网络断了" });
    expect(s.status).toBe("failed");
    expect(s.events.at(-1)).toMatchObject({ type: "error", error: "网络断了" });
  });

  it("loadEvents 覆盖时间线并回到 idle", () => {
    const s = runReducer(initialRunState, {
      type: "loadEvents",
      events: [{ type: "user_task", task: "旧任务" }],
    });
    expect(s.status).toBe("idle");
    expect(s.events).toHaveLength(1);
  });

  it("reset 回到初始态", () => {
    const s = apply(initialRunState, [{ type: "run_started", run_id: "r-1" }]);
    expect(runReducer(s, { type: "reset" })).toEqual(initialRunState);
  });
});
