import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../../App";

describe("AppChrome", () => {
  beforeEach(() => {
    localStorage.clear();
    // jsdom navigator.language 为 en-US；钉 zh 以保持中文标题 / aria 查询
    localStorage.setItem("cg.language", "zh");
  });

  it("顶栏不再含视图导航（已下放左栏）", () => {
    render(<App />);
    const header = screen.getByRole("banner");
    expect(header.querySelector("nav")).toBeNull();
  });

  it("顶栏显示当前调查标题", () => {
    render(<App />);
    expect(screen.getByRole("banner").textContent).toContain("新调查");
  });

  it("侧栏开关是 icon 按钮", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "切换侧栏" }).className).toContain(
      "ui-btn--icon"
    );
  });
});
