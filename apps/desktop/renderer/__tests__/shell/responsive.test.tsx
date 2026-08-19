import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../../App";

/** 覆盖 setup.ts 里恒 false 的 matchMedia 桩 */
function setViewport(width: number) {
  window.matchMedia = ((query: string) => {
    const m = /max-width:\s*(\d+)px/.exec(query);
    return {
      matches: m ? width <= Number(m[1]) : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    };
  }) as unknown as typeof window.matchMedia;
}

describe("响应式与折叠持久化", () => {
  beforeEach(() => {
    localStorage.clear();
    // jsdom navigator.language 为 en-US；钉 zh，使 aria-label 查询保持中文
    localStorage.setItem("cg.language", "zh");
  });

  it("窄于 1180px 自动收右侧板", () => {
    setViewport(1100);
    render(<App />);
    expect(screen.queryByRole("complementary", { name: "本次调查" })).toBeNull();
  });

  it("窄于 900px 自动收左栏", () => {
    setViewport(860);
    render(<App />);
    expect(screen.queryByRole("complementary", { name: "会话与导航" })).toBeNull();
  });

  it("宽屏两者都在", () => {
    setViewport(1440);
    render(<App />);
    expect(screen.getByRole("complementary", { name: "本次调查" })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "会话与导航" })).toBeTruthy();
  });

  it("手动折叠写入 localStorage 并在重挂载后恢复", () => {
    setViewport(1440);
    const first = render(<App />);
    screen.getByRole("button", { name: "切换侧栏" }).click();
    expect(localStorage.getItem("cg.sidebar_collapsed")).toBe("1");
    first.unmount();
    render(<App />);
    expect(screen.queryByRole("complementary", { name: "会话与导航" })).toBeNull();
  });
});
