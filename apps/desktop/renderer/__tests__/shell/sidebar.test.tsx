import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../i18n/I18nProvider";

const create = vi.fn();
const onNavigate = vi.fn();

vi.mock("../../state", () => ({
  useSessions: () => ({
    sessions: [],
    sessionId: null,
    select: vi.fn(),
    create,
    remove: vi.fn(),
    refresh: vi.fn(),
    clearAll: vi.fn(),
    adopt: vi.fn(),
  }),
}));

import { Sidebar } from "../../components/shell/Sidebar";

function renderSidebar(activeView: "workbench" | "settings" = "settings") {
  // jsdom navigator.language 为 en-US；钉 zh 以保持中文按钮名查询
  localStorage.setItem("cg.language", "zh");
  return render(
    <I18nProvider>
      <Sidebar activeView={activeView} onNavigate={onNavigate} />
    </I18nProvider>
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    create.mockReset();
    onNavigate.mockReset();
    localStorage.clear();
  });

  it("顶部有 ＋ 新建，点击创建并切到 workbench", () => {
    renderSidebar("settings");
    fireEvent.click(screen.getByRole("button", { name: "＋ 新建" }));
    expect(create).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith("workbench");
  });

  it("底部 ViewNav 三个入口在", () => {
    renderSidebar("workbench");
    expect(screen.getByRole("button", { name: "调查" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "证据" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "设置" })).toBeTruthy();
  });
});
