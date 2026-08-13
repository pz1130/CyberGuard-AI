import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SAMPLE_TASKS } from "../../lib/sampleTasks";

const setTask = vi.fn();
const env = {
  providerMode: "live",
  mcpTools: ["mcp__alerts__list"],
  pingOk: true as boolean | null,
};

vi.mock("../../state", () => ({
  useRun: () => ({ setTask, running: false }),
  useEnvironment: () => env,
}));

import { TimelineEmpty } from "../../components/investigation/TimelineEmpty";

describe("中间栏空态", () => {
  it("列出全部示例任务，含一句说明", () => {
    render(<TimelineEmpty />);
    for (const s of SAMPLE_TASKS) {
      expect(screen.getByText(s.label)).toBeTruthy();
      expect(screen.getByText(s.blurb)).toBeTruthy();
    }
  });

  it("点击示例把完整任务文本填进 composer", () => {
    setTask.mockReset();
    render(<TimelineEmpty />);
    fireEvent.click(screen.getByText(SAMPLE_TASKS[0].label));
    expect(setTask).toHaveBeenCalledWith(SAMPLE_TASKS[0].text);
  });

  it("全部就绪时不显示状态行", () => {
    env.providerMode = "live";
    env.mcpTools = ["mcp__alerts__list"];
    env.pingOk = true;
    render(<TimelineEmpty />);
    expect(screen.queryByText(/当前状态/)).toBeNull();
  });

  it("未就绪时把缺什么摆出来", () => {
    env.providerMode = "mock";
    env.mcpTools = [];
    env.pingOk = false;
    render(<TimelineEmpty />);
    const line = screen.getByText(/当前状态/).parentElement;
    expect(line?.textContent).toContain("sidecar 未连接");
    expect(line?.textContent).toContain("模型为 mock");
    expect(line?.textContent).toContain("未接入数据源");
  });
});
