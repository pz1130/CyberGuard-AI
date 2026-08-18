import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

describe("Sidebar", () => {
  beforeEach(() => {
    create.mockReset();
    onNavigate.mockReset();
  });

  it("顶部有 ＋ 新建，点击创建并切到 workbench", () => {
    render(<Sidebar activeView="settings" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByRole("button", { name: "＋ 新建" }));
    expect(create).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith("workbench");
  });

  it("底部 ViewNav 三个入口在", () => {
    render(<Sidebar activeView="workbench" onNavigate={onNavigate} />);
    expect(screen.getByRole("button", { name: "调查" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "证据" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "设置" })).toBeTruthy();
  });
});
