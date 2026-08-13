import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EnvironmentProvider } from "../../state/useEnvironment";

describe("EnvironmentProvider ping", () => {
  afterEach(() => {
    delete (window as { cyberguard?: unknown }).cyberguard;
  });

  it("paused_runs[0].run_id 触发 onPausedRuns（INV-36）", async () => {
    const onPausedRuns = vi.fn();
    window.cyberguard = {
      ping: vi.fn().mockResolvedValue({
        paused_runs: [{ run_id: "r-paused", task: "续跑" }],
      }),
      providerGet: vi.fn().mockResolvedValue({ mode: "mock" }),
      capabilities: vi.fn().mockResolvedValue({}),
    } as unknown as typeof window.cyberguard;

    render(
      <EnvironmentProvider tier="readonly" onPausedRuns={onPausedRuns}>
        <div>child</div>
      </EnvironmentProvider>
    );

    await waitFor(() => {
      expect(onPausedRuns).toHaveBeenCalledWith("r-paused");
    });
  });

  it("paused_runs 缺失或无 run_id 时不回调", async () => {
    const onPausedRuns = vi.fn();
    window.cyberguard = {
      ping: vi.fn().mockResolvedValue({}),
      providerGet: vi.fn().mockResolvedValue({ mode: "mock" }),
      capabilities: vi.fn().mockResolvedValue({}),
    } as unknown as typeof window.cyberguard;

    render(
      <EnvironmentProvider tier="readonly" onPausedRuns={onPausedRuns}>
        <div>child</div>
      </EnvironmentProvider>
    );

    await waitFor(() => {
      expect(window.cyberguard?.ping).toHaveBeenCalled();
    });
    expect(onPausedRuns).not.toHaveBeenCalled();
  });
});
