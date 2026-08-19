import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../App";

/**
 * T10 Step 2：右栏「证据」链接是 Workbench 跳证据页的落点 —— 点它要选中
 * 并高亮对应行。计划里这一条原本只写了「手工验证」，补成自动化。
 */
const EVID = "ev_9f3c2a1b7d5e";

function stubApi() {
  window.cyberguard = {
    onEvent: vi.fn(() => () => {}),
    ping: vi.fn().mockResolvedValue({ sandbox: { sandbox_impl: "seatbelt" } }),
    providerGet: vi.fn().mockResolvedValue({ mode: "mock" }),
    capabilities: vi.fn().mockResolvedValue({}),
    listSessions: vi.fn().mockResolvedValue({
      sessions: [
        { session_id: "s1", title: "登记过证据的一次调查", tier: "readonly", updated_at: 1, event_count: 2 },
      ],
    }),
    sessionEvents: vi.fn().mockResolvedValue({
      events: [
        { type: "user_task", task: "读本地告警" },
        { type: "evidence_register", evidence_id: EVID },
      ],
    }),
    evidenceList: vi.fn().mockResolvedValue({
      evidence: [
        {
          evidence_id: "ev_other0000",
          path: "/tmp/other.txt",
          name: "other.txt",
          sha256: "a".repeat(64),
          size: 12,
          readonly: true,
          registered_at: 1,
        },
        {
          evidence_id: EVID,
          path: "/tmp/gp-evidence.txt",
          name: "gp-evidence.txt",
          sha256: "b".repeat(64),
          size: 34,
          readonly: true,
          registered_at: 2,
        },
      ],
    }),
  } as unknown as typeof window.cyberguard;
}

describe("右栏证据链接跳转并高亮", () => {
  beforeEach(() => {
    localStorage.clear();
    // jsdom navigator.language 为 en-US；钉 zh，使侧栏/右栏 aria 保持中文
    localStorage.setItem("cg.language", "zh");
    stubApi();
  });

  it("点右栏证据 id → 切到证据页，对应行拿到落点高亮", async () => {
    render(<App />);

    // 选中那次调查，右栏才会列出本轮登记的证据 id
    const sidebar = screen.getByRole("complementary", { name: "会话与导航" });
    await waitFor(() =>
      within(sidebar).getByText(/登记过证据的一次调查/)
    );
    within(sidebar).getByText(/登记过证据的一次调查/).click();

    const rail = await screen.findByRole("complementary", { name: "本次调查" });
    const link = await waitFor(() =>
      within(rail).getByRole("button", { name: new RegExp(EVID.slice(0, 12)) })
    );
    link.click();

    // 落点：证据页里该行带高亮类，另一行不带
    const row = await waitFor(() => {
      const el = document.getElementById(`evidence-row-${EVID}`);
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    await waitFor(() => expect(row.className).toContain("evidence-row-hi"));
    expect(
      document.getElementById("evidence-row-ev_other0000")?.className ?? ""
    ).not.toContain("evidence-row-hi");
  });
});
