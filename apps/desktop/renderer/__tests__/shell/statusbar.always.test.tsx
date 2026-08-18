import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../../App";

/** 六项常显 —— INV-36 / INV-38 / M2 判据 10 */
function expectSixVisible() {
  const bar = screen.getByRole("contentinfo", { name: "运行态" });
  expect(bar).toBeTruthy();
  for (const label of ["沙箱", "权限"]) {
    expect(bar.textContent).toContain(label);
  }
  // 连接态三选一
  expect(bar.textContent).toMatch(/在线|离线|连接中/);
  // Provider 档位二选一
  expect(bar.textContent).toMatch(/live|mock/);
  // 能力档位二选一
  expect(bar.textContent).toMatch(/只读|完整/);
}

describe("状态栏常显", () => {
  it("调查页可见", () => {
    render(<App />);
    expectSixVisible();
  });

  it("切到证据页仍可见", async () => {
    render(<App />);
    screen.getByRole("button", { name: "证据" }).click();
    expectSixVisible();
  });

  it("切到设置页仍可见", async () => {
    render(<App />);
    screen.getByRole("button", { name: "设置" }).click();
    expectSixVisible();
  });

  it("不再是 ContextRail 的子节点", () => {
    render(<App />);
    const bar = screen.getByRole("contentinfo", { name: "运行态" });
    expect(bar.closest(".ctxrail")).toBeNull();
  });
});
