import { act, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Ev } from "../../lib/types";
import {
  StreamProvider,
  useStreamDispatch,
  useStreamFlag,
  useStreamText,
} from "../../state/useStream";

/**
 * 流式隔离的回归护栏。
 *
 * 曾经的失败模式：Timeline 调 useStream() 拿 { streaming } 布尔，
 * 但 context value 每个 token 都是新对象，导致 Timeline 随 token
 * 全量重渲染，Task 8 的隔离形同虚设。
 *
 * 注意：每个 token 必须单独 act()。放进同一个 act() 会被 React
 * 自动批处理合并成一次渲染，读数是假的。
 */

let flagRenders = 0;
let textRenders = 0;

/** 只关心「在不在流」的消费者，如 Timeline */
function FlagConsumer() {
  const streaming = useStreamFlag();
  flagRenders += 1;
  return <div data-testid="flag">{streaming ? "running" : "idle"}</div>;
}

/** 真正需要正文的消费者，只有 StreamEvent */
function TextConsumer() {
  const text = useStreamText();
  textRenders += 1;
  return <div data-testid="text">{text}</div>;
}

let fire: ((ev: Ev) => void) | null = null;
function Pump() {
  fire = useStreamDispatch();
  return null;
}

function setup() {
  flagRenders = 0;
  textRenders = 0;
  const utils = render(
    <StreamProvider>
      <Pump />
      <FlagConsumer />
      <TextConsumer />
    </StreamProvider>
  );
  return { ...utils, base: { flag: flagRenders, text: textRenders } };
}

function pump(ev: Ev, times = 1) {
  for (let i = 0; i < times; i++) {
    act(() => {
      fire?.(ev);
    });
  }
}

describe("流式隔离", () => {
  it("N 个 token 只让布尔消费者渲染一次（false→true），正文消费者渲染 N 次", () => {
    const { base } = setup();

    pump({ type: "token", delta: "x" }, 20);

    expect(flagRenders - base.flag).toBe(1);
    expect(textRenders - base.text).toBe(20);
  });

  it("token_done 后布尔翻回 false，仅再渲染一次", () => {
    const { base } = setup();

    pump({ type: "token", delta: "x" }, 10);
    pump({ type: "token_done" });

    // true 一次 + false 一次
    expect(flagRenders - base.flag).toBe(2);
  });

  it("正文累加，answer_ready 清空缓冲", () => {
    const { getByTestId } = setup();

    pump({ type: "token", delta: "ab" });
    pump({ type: "token", delta: "cd" });
    expect(getByTestId("text").textContent).toBe("abcd");

    pump({ type: "answer_ready" });
    expect(getByTestId("text").textContent).toBe("");
    expect(getByTestId("flag").textContent).toBe("idle");
  });

  it("tool_call_start 清掉上一轮的模型碎碎念", () => {
    const { getByTestId } = setup();

    pump({ type: "token", delta: "中间碎碎念" });
    pump({ type: "tool_call_start", tool_name: "list_alerts" });

    expect(getByTestId("text").textContent).toBe("");
    expect(getByTestId("flag").textContent).toBe("idle");
  });

  it("dispatch 引用恒定 —— 写侧永不因流式更新重订阅", () => {
    setup();
    const first = fire;
    pump({ type: "token", delta: "x" }, 5);
    expect(fire).toBe(first);
  });
});
