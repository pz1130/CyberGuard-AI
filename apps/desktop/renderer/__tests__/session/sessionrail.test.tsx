import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../i18n/I18nProvider";
import type { SessionRow } from "../../lib/types";

const remove = vi.fn().mockResolvedValue(true);
const select = vi.fn();

const rows: SessionRow[] = [
  {
    session_id: "a",
    title: "会话 A",
    tier: "readonly",
    updated_at: 1,
    event_count: 0,
  },
  {
    session_id: "b",
    title: "会话 B",
    tier: "readonly",
    updated_at: 2,
    event_count: 1,
  },
];

vi.mock("../../state", () => ({
  useSessions: () => ({
    sessions: rows,
    sessionId: "a",
    select,
    create: vi.fn(),
    remove,
    refresh: vi.fn(),
    clearAll: vi.fn(),
    adopt: vi.fn(),
  }),
  useRun: () => ({ setTask: vi.fn(), running: false }),
}));

import { SessionRail } from "../../components/session/SessionRail";

function renderRail() {
  // jsdom navigator.language 为 en-US；钉 zh 以保持中文 aria / 撤销文案查询
  localStorage.setItem("cg.language", "zh");
  return render(
    <I18nProvider>
      <SessionRail />
    </I18nProvider>
  );
}

describe("SessionRail 删除撤销", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    remove.mockReset();
    remove.mockResolvedValue(true);
    select.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("点击删除不立刻调 API，5 秒后才提交", async () => {
    renderRail();
    fireEvent.click(screen.getByRole("button", { name: "删除 会话 A" }));
    expect(screen.queryByText("会话 A")).toBeNull();
    expect(screen.getByText("已删除 · 撤销")).toBeTruthy();
    expect(remove).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(remove).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith("a");
  });

  it("撤销则恢复行且不调 API", async () => {
    renderRail();
    fireEvent.click(screen.getByRole("button", { name: "删除 会话 A" }));
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    expect(screen.getByText("会话 A")).toBeTruthy();
    expect(screen.queryByText("已删除 · 撤销")).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(remove).not.toHaveBeenCalled();
  });

  it("API 失败时恢复行并就地报错", async () => {
    remove.mockResolvedValue(false);
    renderRail();
    fireEvent.click(screen.getByRole("button", { name: "删除 会话 A" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByText("会话 A")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("删除失败");
  });
});
