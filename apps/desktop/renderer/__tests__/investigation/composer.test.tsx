import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../i18n/I18nProvider";

const mocks = vi.hoisted(() => ({
  run: vi.fn(),
  setTier: vi.fn(),
  tier: "readonly" as "readonly" | "full",
  sandboxImpl: "seatbelt",
  pingOk: true as boolean | null,
}));

vi.mock("../../state", () => ({
  useRun: () => ({
    task: "分诊告警",
    setTask: vi.fn(),
    get tier() {
      return mocks.tier;
    },
    setTier: mocks.setTier,
    run: mocks.run,
    abort: vi.fn(),
    steer: vi.fn(),
    steerText: "",
    setSteerText: vi.fn(),
    running: false,
    runId: null,
  }),
  useEnvironment: () => ({
    get pingOk() {
      return mocks.pingOk;
    },
    get sandboxImpl() {
      return mocks.sandboxImpl;
    },
  }),
}));

import { Composer } from "../../components/investigation/Composer";

const SRC = resolve(
  __dirname,
  "../../components/investigation/Composer.tsx"
);

function renderComposer() {
  // jsdom navigator.language 为 en-US；钉 zh 以保持中文占位符 / aria 查询
  localStorage.setItem("cg.language", "zh");
  return render(
    <I18nProvider>
      <Composer />
    </I18nProvider>
  );
}

describe("Composer ⌘↵ 不双发", () => {
  beforeEach(() => {
    mocks.run.mockClear();
    mocks.setTier.mockClear();
    mocks.tier = "readonly";
    mocks.sandboxImpl = "seatbelt";
    mocks.pingOk = true;
    localStorage.clear();
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
    renderComposer();
    fireEvent.keyDown(screen.getByPlaceholderText(/描述任务/), {
      key: "Enter",
      metaKey: true,
    });
    expect(mocks.run).toHaveBeenCalledTimes(1);
    expect(onWindow).not.toHaveBeenCalled();
    window.removeEventListener("keydown", onWindow);
  });

  it("sandboxImpl=none 时强制只读并禁用档位选择（INV-16）", () => {
    mocks.tier = "full";
    mocks.sandboxImpl = "none";
    renderComposer();
    expect(mocks.setTier).toHaveBeenCalledWith("readonly");
    expect(
      screen.getByRole("combobox", { name: "能力档位" }).getAttribute(
        "data-disabled"
      )
    ).not.toBe(null);
  });
});
