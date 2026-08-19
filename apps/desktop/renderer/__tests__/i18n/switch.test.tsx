import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../App";
import { resolveLanguage } from "../../i18n/I18nProvider";

describe("语言切换", () => {
  beforeEach(() => localStorage.clear());

  it("system 档按 navigator.language 分流", () => {
    const spy = vi.spyOn(navigator, "language", "get");
    spy.mockReturnValue("zh-CN");
    expect(resolveLanguage("system")).toBe("zh");
    spy.mockReturnValue("en-US");
    expect(resolveLanguage("system")).toBe("en");
    spy.mockRestore();
  });

  it("存了 en 时主区与状态栏无中文", async () => {
    localStorage.setItem("cg.language", "en");
    render(<App />);
    await waitFor(() => screen.getByRole("contentinfo"));
    // 语言选择器故意保留母语写法「中文」（T5）；整页 body 会命中它。
    // 判据收窄到 contentinfo + main，排除设置页语言选项的固有 CJK。
    const bar = screen.getByRole("contentinfo");
    const main = document.querySelector(".app-main") ?? document.body;
    expect(bar.textContent).not.toMatch(/[一-鿿]/);
    expect(main.textContent).not.toMatch(/[一-鿿]/);
  });

  it("存了 zh 时状态栏是中文", async () => {
    localStorage.setItem("cg.language", "zh");
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("contentinfo").textContent).toMatch(/沙箱/)
    );
  });
});
