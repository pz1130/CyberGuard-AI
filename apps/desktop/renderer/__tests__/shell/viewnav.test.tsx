import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ViewNav } from "../../components/shell/ViewNav";

describe("ViewNav", () => {
  it("三个入口都在，当前项标 aria-current", () => {
    render(<ViewNav activeView="evidence" onNavigate={() => {}} />);
    expect(screen.getByRole("button", { name: "调查" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "设置" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "证据" }).getAttribute("aria-current")
    ).toBe("true");
  });

  it("点击回调带视图 id", () => {
    const onNavigate = vi.fn();
    render(<ViewNav activeView="workbench" onNavigate={onNavigate} />);
    screen.getByRole("button", { name: "设置" }).click();
    expect(onNavigate).toHaveBeenCalledWith("settings");
  });
});
