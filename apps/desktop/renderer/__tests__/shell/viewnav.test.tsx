import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../i18n/I18nProvider";
import { ViewNav } from "../../components/shell/ViewNav";

function renderNav(
  activeView: "workbench" | "evidence" | "settings",
  onNavigate: (v: string) => void = () => {}
) {
  // jsdom navigator.language 为 en-US；钉 zh 以保持中文入口名查询
  localStorage.setItem("cg.language", "zh");
  return render(
    <I18nProvider>
      <ViewNav activeView={activeView} onNavigate={onNavigate} />
    </I18nProvider>
  );
}

describe("ViewNav", () => {
  beforeEach(() => localStorage.clear());

  it("三个入口都在，当前项标 aria-current", () => {
    renderNav("evidence");
    expect(screen.getByRole("button", { name: "调查" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "设置" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "证据" }).getAttribute("aria-current")
    ).toBe("true");
  });

  it("点击回调带视图 id", () => {
    const onNavigate = vi.fn();
    renderNav("workbench", onNavigate);
    screen.getByRole("button", { name: "设置" }).click();
    expect(onNavigate).toHaveBeenCalledWith("settings");
  });
});
