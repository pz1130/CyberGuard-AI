import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlanEvent } from "../../components/investigation/events/PlanEvent";
import { ToolEvent } from "../../components/investigation/events/ToolEvent";
import {
  isClosedToolStart,
  toolIdentity,
} from "../../components/investigation/events";
import type { Ev } from "../../lib/types";

describe("isClosedToolStart（append-only 起止配对）", () => {
  it("同名 start+end：跳过 start，end 不算 closed start", () => {
    const events: Ev[] = [
      { type: "tool_call_start", name: "read_file" },
      { type: "tool_call_end", name: "read_file", result_preview: "ok" },
    ];
    expect(isClosedToolStart(events, 0)).toBe(true);
    expect(isClosedToolStart(events, 1)).toBe(false);
  });

  it("仅有 start（进行中）不跳过", () => {
    const events: Ev[] = [{ type: "tool_call_start", name: "scan" }];
    expect(isClosedToolStart(events, 0)).toBe(false);
  });

  it("不同名的 later end 不关闭 start", () => {
    const events: Ev[] = [
      { type: "tool_call_start", name: "a" },
      { type: "tool_call_end", name: "b" },
    ];
    expect(isClosedToolStart(events, 0)).toBe(false);
  });

  it("同工具第二次调用：已结束的 start 关闭，inflight start 保留", () => {
    const events: Ev[] = [
      { type: "tool_call_start", name: "read_file" },
      { type: "tool_call_end", name: "read_file" },
      { type: "tool_call_start", name: "read_file" },
    ];
    expect(isClosedToolStart(events, 0)).toBe(true);
    expect(isClosedToolStart(events, 2)).toBe(false);
  });

  it("tool_name 与 name 视为同一身份", () => {
    expect(toolIdentity({ type: "tool_call_start", tool_name: "x" })).toBe("x");
    const events: Ev[] = [
      { type: "tool_call_start", tool_name: "x" },
      { type: "tool_call_end", name: "x" },
    ];
    expect(isClosedToolStart(events, 0)).toBe(true);
  });
});

describe("ToolEvent 失败文案", () => {
  it("error 为 boolean 时展示 result_preview，不展示 true", () => {
    render(
      <ToolEvent
        ev={{
          type: "tool_call_end",
          name: "read_file",
          error: true,
          result_preview: "ENOENT: missing",
        }}
      />
    );
    expect(screen.getByText("ENOENT: missing")).toBeTruthy();
    expect(screen.queryByText("true")).toBeNull();
  });

  it("error 为字符串时仍展示 error 文本", () => {
    render(
      <ToolEvent
        ev={{
          type: "tool_call_end",
          name: "read_file",
          error: "permission denied",
        }}
      />
    );
    expect(screen.getByText("permission denied")).toBeTruthy();
  });
});

describe("PlanEvent live 字段", () => {
  it("plan_approved 用 plan_summary（无 plan 对象）", () => {
    render(
      <PlanEvent
        ev={{
          type: "plan_approved",
          plan_summary: "扫本机端口",
          approval_type: "self",
        }}
      />
    );
    expect(screen.getByText("扫本机端口")).toBeTruthy();
    expect(screen.getByText("approval_type: self")).toBeTruthy();
  });

  it("plan_rejected 展示 reason", () => {
    render(
      <PlanEvent
        ev={{ type: "plan_rejected", reason: "超时=拒绝", status: "timeout" }}
      />
    );
    expect(screen.getByText("超时=拒绝")).toBeTruthy();
  });
});

describe("Timeline 流式隔离", () => {
  it("Timeline 只读 streaming，不读 streamText", () => {
    const src = readFileSync(
      resolve(__dirname, "../../components/investigation/Timeline.tsx"),
      "utf8"
    );
    expect(src).toMatch(/const \{ streaming \} = useStream\(\)/);
    expect(src).not.toMatch(/\bstreamText\b/);
  });
});
