import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../../App";

/**
 * 常显五项 —— 连接 / 沙箱 / 权限 / Provider / 档位（INV-36 / INV-38 / M2 判据 10）。
 * 第六项「暂停」是状态指示，只在 paused 为真时出现（StatusBar.tsx），
 * 因此不在此断言 —— 未暂停时它不该占位。INV-36 的「待上报数」缺口见
 * docs/desktop/11-OPEN-QUESTIONS.md §J。
 */
function expectAlwaysOnVisible() {
  const bar = screen.getByRole("contentinfo", { name: /runtime|运行态/i });
  expect(bar).toBeTruthy();
  expect(bar.textContent).toMatch(/sandbox|沙箱/i);
  expect(bar.textContent).toMatch(/permission|权限/i);
  // 连接态三选一
  expect(bar.textContent).toMatch(/online|offline|connecting|在线|离线|连接中/i);
  // Provider 档位二选一
  expect(bar.textContent).toMatch(/live|mock/);
  // 能力档位二选一
  expect(bar.textContent).toMatch(/read-only|full|只读|完整/i);
}

function clickSidebarNav(label: string) {
  const sidebar = screen.getByRole("complementary", { name: "会话与导航" });
  within(sidebar).getByRole("button", { name: label }).click();
}

describe("状态栏常显", () => {
  beforeEach(() => localStorage.clear());

  it("调查页可见", () => {
    render(<App />);
    expectAlwaysOnVisible();
  });

  it("切到证据页仍可见", async () => {
    render(<App />);
    clickSidebarNav("证据");
    expectAlwaysOnVisible();
  });

  it("切到设置页仍可见", async () => {
    render(<App />);
    clickSidebarNav("设置");
    expectAlwaysOnVisible();
  });

  it("不再是 ContextRail 的子节点", () => {
    render(<App />);
    const bar = screen.getByRole("contentinfo", { name: /runtime|运行态/i });
    expect(bar.closest(".ctxrail")).toBeNull();
  });

  it.each([
    ["都展开", false, false],
    ["只收左栏", true, false],
    ["只收侧板", false, true],
    ["都收起", true, true],
  ])("%s 时常显五项仍在", (_n, sidebar, rail) => {
    localStorage.setItem("cg.sidebar_collapsed", sidebar ? "1" : "0");
    localStorage.setItem("cg.rail_collapsed", rail ? "1" : "0");
    render(<App />);
    expectAlwaysOnVisible();
  });
});
