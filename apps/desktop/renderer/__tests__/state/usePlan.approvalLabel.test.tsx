import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../i18n/I18nProvider";
import { PlanProvider, usePlan } from "../../state/usePlan";

/**
 * K.1：审批标题必须由 approval_type 映射到词条，不能用 sidecar 的成品文案 ——
 * ui_label 恒为中文，英文界面下会漏出中文（11-OPEN-QUESTIONS §K.1）。
 * connected 未排期，segregation 真机产生不出来，只能桩事件。
 */
function wrap({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <PlanProvider onError={() => {}}>{children}</PlanProvider>
    </I18nProvider>
  );
}

const planEvent = (over: Record<string, unknown>) => ({
  type: "plan_ready",
  plan_id: "p1",
  plan: { summary: "s" },
  ...over,
});

describe("审批标题按 approval_type 映射", () => {
  beforeEach(() => localStorage.clear());

  it("segregation 走词条，不用 sidecar 的中文 ui_label", () => {
    localStorage.setItem("cg.language", "zh");
    const { result } = renderHook(() => usePlan(), { wrapper: wrap });
    act(() =>
      result.current.ingest(
        planEvent({ approval_type: "segregation", ui_label: "职责分离审批" })
      )
    );
    expect(result.current.pendingPlan?.ui_label).toBe("职责分离审批");
  });

  it("英文 locale 下 segregation 标题无中文", () => {
    localStorage.setItem("cg.language", "en");
    const { result } = renderHook(() => usePlan(), { wrapper: wrap });
    act(() =>
      result.current.ingest(
        planEvent({ approval_type: "segregation", ui_label: "职责分离审批" })
      )
    );
    const label = result.current.pendingPlan?.ui_label ?? "";
    expect(label).not.toMatch(/[一-鿿]/);
    expect(label).toMatch(/segregation/i);
  });

  it("self 仍走自批准词条", () => {
    localStorage.setItem("cg.language", "en");
    const { result } = renderHook(() => usePlan(), { wrapper: wrap });
    act(() => result.current.ingest(planEvent({ approval_type: "self" })));
    expect(result.current.pendingPlan?.ui_label).toMatch(/self-approve/i);
  });

  it("未知类型不得标成自批准 —— 那是 INV-06 意义上的错标", () => {
    localStorage.setItem("cg.language", "en");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result } = renderHook(() => usePlan(), { wrapper: wrap });
    act(() =>
      result.current.ingest(planEvent({ approval_type: "four_eyes" }))
    );
    expect(result.current.pendingPlan?.ui_label ?? "").not.toMatch(
      /self-approve/i
    );
    warn.mockRestore();
  });
});
