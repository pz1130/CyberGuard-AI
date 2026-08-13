import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const run = vi.fn();

vi.mock("../../state", () => ({
  useRun: () => ({
    task: "分诊告警",
    setTask: vi.fn(),
    tier: "readonly",
    setTier: vi.fn(),
    run,
    abort: vi.fn(),
    steer: vi.fn(),
    steerText: "",
    setSteerText: vi.fn(),
    running: false,
    runId: null,
  }),
  useEnvironment: () => ({ pingOk: true }),
}));

import { Composer } from "../../components/investigation/Composer";

const SRC = resolve(
  __dirname,
  "../../components/investigation/Composer.tsx"
);

describe("Composer ⌘↵ 不双发", () => {
  beforeEach(() => {
    run.mockClear();
    window.cyberguard = { run: vi.fn() } as unknown as typeof window.cyberguard;
  });

  afterEach(() => {
    delete (window as { cyberguard?: unknown }).cyberguard;
  });

  it("源码锁：preventDefault 后紧跟 stopPropagation", () => {
    const src = readFileSync(SRC, "utf8");
    expect(src).toMatch(/e\.preventDefault\(\);\s*e\.stopPropagation\(\);/);
  });

  it("textarea ⌘Enter 调用 run 一次且不冒泡到 window", () => {
    const onWindow = vi.fn();
    window.addEventListener("keydown", onWindow);
    render(<Composer />);
    fireEvent.keyDown(screen.getByPlaceholderText(/描述任务/), {
      key: "Enter",
      metaKey: true,
    });
    expect(run).toHaveBeenCalledTimes(1);
    expect(onWindow).not.toHaveBeenCalled();
    window.removeEventListener("keydown", onWindow);
  });
});
