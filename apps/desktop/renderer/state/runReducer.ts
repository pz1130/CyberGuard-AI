import type { Ev } from "../lib/types";

/** 运行态枚举。控制流只许比较这个，禁止比较显示文案。 */
export type RunStatus = "idle" | "running" | "paused" | "done" | "failed";

export type RunState = {
  status: RunStatus;
  runId: string | null;
  pausedRunId: string | null;
  events: Ev[];
  mcpTools: string[];
  lastSubmitted: string | null;
};

export const initialRunState: RunState = {
  status: "idle",
  runId: null,
  pausedRunId: null,
  events: [],
  mcpTools: [],
  lastSubmitted: null,
};

export type RunAction =
  | { type: "event"; ev: Ev }
  | { type: "submit"; text: string }
  | { type: "settled" }
  | { type: "failed"; error: string }
  | { type: "loadEvents"; events: Ev[] }
  | { type: "reset" };

/** 流式 token 由 stream 域独占，不进时间线 */
const STREAM_ONLY = new Set(["token", "token_done"]);

function str(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

function reduceEvent(state: RunState, ev: Ev): RunState {
  if (STREAM_ONLY.has(ev.type)) return state;

  let next: RunState = { ...state, events: [...state.events, ev] };

  switch (ev.type) {
    case "run_started": {
      const rid = str(ev.run_id);
      next = {
        ...next,
        status: "running",
        runId: rid ?? next.runId,
        pausedRunId: null,
        mcpTools: Array.isArray(ev.mcp_tools)
          ? ev.mcp_tools.map(String)
          : next.mcpTools,
      };
      break;
    }
    case "start": {
      const rid = str(ev.agent_run_id);
      if (rid) next = { ...next, runId: rid };
      break;
    }
    case "run_paused": {
      // 只看事件类型，不看 ui_status 文案
      next = {
        ...next,
        status: "paused",
        pausedRunId: str(ev.run_id) ?? next.runId,
      };
      break;
    }
    case "run_resumed": {
      next = { ...next, status: "running", pausedRunId: null };
      break;
    }
    case "answer_ready": {
      next = { ...next, status: "done" };
      break;
    }
    case "error": {
      next = { ...next, status: "failed" };
      break;
    }
    default:
      break;
  }

  return next;
}

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case "event":
      return reduceEvent(state, action.ev);

    case "submit":
      return {
        ...state,
        status: "running",
        runId: null,
        pausedRunId: null,
        events: [],
        lastSubmitted: action.text,
      };

    case "settled":
      // IPC 调用返回时收口；暂停态由事件决定，不被覆盖
      return state.status === "running" ? { ...state, status: "done" } : state;

    case "failed":
      return {
        ...state,
        status: "failed",
        events: [
          ...state.events,
          { type: "error", error: action.error, status: "failed" },
        ],
      };

    case "loadEvents":
      return {
        ...state,
        status: "idle",
        runId: null,
        pausedRunId: null,
        events: action.events,
      };

    case "reset":
      return initialRunState;

    default:
      return state;
  }
}
