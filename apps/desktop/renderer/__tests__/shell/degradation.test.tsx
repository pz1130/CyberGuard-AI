import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../App";

/** 桩法与 __tests__/state/useEnvironment.provider.test.tsx 同款 */
function stubSandboxNone() {
  window.cyberguard = {
    ping: vi.fn().mockResolvedValue({ sandbox: { sandbox_impl: "none" } }),
    providerGet: vi.fn().mockResolvedValue({ mode: "mock" }),
    capabilities: vi.fn().mockResolvedValue({}),
    // App 的 EventFanout 在 cyberguard 存在时必调 onEvent；provider 单测不挂 App 故可省
    onEvent: vi.fn(() => () => {}),
  } as unknown as typeof window.cyberguard;
}

/**
 * INV-38：安全降级必须显式标注，不得伪装。
 * sandbox_impl=none 时状态栏须**显著**告警 —— 只挂 tooltip 不算。
 */
describe("降级显著告警", () => {
  afterEach(() => {
    delete (window as { cyberguard?: unknown }).cyberguard;
  });

  it("sandbox_impl=none 时状态栏整条进入 danger 态", async () => {
    stubSandboxNone();
    render(<App />);
    await waitFor(() => {
      const bar = screen.getByRole("contentinfo", { name: "运行态" });
      expect(bar.className).toContain("statusbar--danger");
    });
    expect(
      screen.getByRole("contentinfo", { name: "运行态" }).textContent
    ).toContain("沙箱");
  });

  it("用户收起降级浮出条后，状态栏仍保持降级态", async () => {
    stubSandboxNone();
    render(<App />);
    await waitFor(() => screen.getByRole("alert"));
    // 浮出条可收起；状态栏不可 —— 可收起的提示条不是安全边界（INV-38）
    // jsdom + React 19：原生 HTMLElement.click() 不触发该按钮的 onClick，改用 fireEvent
    fireEvent.click(screen.getAllByRole("button", { name: "收起" })[0]);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("contentinfo", { name: "运行态" }).className
    ).toContain("statusbar--danger");
  });
});
