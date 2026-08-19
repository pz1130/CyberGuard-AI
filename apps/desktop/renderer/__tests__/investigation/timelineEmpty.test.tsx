import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../i18n/I18nProvider";
import zh from "../../i18n/zh.json";
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

function renderEmpty() {
  // jsdom navigator.language 为 en-US；钉 zh，断言走权威中文词条
  localStorage.setItem("cg.language", "zh");
  return render(
    <I18nProvider>
      <TimelineEmpty />
    </I18nProvider>
  );
}

describe("中间栏空态", () => {
  beforeEach(() => {
    localStorage.clear();
    env.providerMode = "live";
    env.mcpTools = ["mcp__alerts__list"];
    env.pingOk = true;
  });

  it("列出全部示例任务，含一句说明", () => {
    renderEmpty();
    for (const s of SAMPLE_TASKS) {
      expect(screen.getByText(zh[s.labelKey as keyof typeof zh])).toBeTruthy();
      expect(screen.getByText(zh[s.blurbKey as keyof typeof zh])).toBeTruthy();
    }
  });

  it("点击示例把完整任务文本填进 composer", () => {
    setTask.mockReset();
    renderEmpty();
    fireEvent.click(
      screen.getByText(zh[SAMPLE_TASKS[0].labelKey as keyof typeof zh])
    );
    expect(setTask).toHaveBeenCalledWith(
      zh[SAMPLE_TASKS[0].textKey as keyof typeof zh]
    );
  });

  it("全部就绪时不显示状态行", () => {
    renderEmpty();
    expect(screen.queryByText(/当前状态/)).toBeNull();
  });

  it("未就绪时把缺什么摆出来", () => {
    env.providerMode = "mock";
    env.mcpTools = [];
    env.pingOk = false;
    renderEmpty();
    const line = screen.getByText(/当前状态/).parentElement;
    expect(line?.textContent).toContain("sidecar 未连接");
    expect(line?.textContent).toContain("模型为 mock");
    expect(line?.textContent).toContain("未接入数据源");
  });
});
