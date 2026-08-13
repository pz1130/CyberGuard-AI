import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Select } from "../../ui/Select";

const OPTIONS = [
  { value: "readonly", label: "只读" },
  { value: "full", label: "完整" },
];

describe("Select", () => {
  it("渲染为 combobox 角色并带 aria-label", () => {
    render(
      <Select
        value="readonly"
        onChange={() => {}}
        options={OPTIONS}
        ariaLabel="能力档位"
      />
    );
    const trigger = screen.getByRole("combobox", { name: "能力档位" });
    expect(trigger).toBeTruthy();
  });

  it("显示当前选中项的 label 而非 value", () => {
    render(
      <Select
        value="full"
        onChange={() => {}}
        options={OPTIONS}
        ariaLabel="能力档位"
      />
    );
    expect(screen.getByRole("combobox").textContent).toContain("完整");
  });

  it("disabled 时 trigger 不可用", () => {
    render(
      <Select
        value="readonly"
        onChange={() => {}}
        options={OPTIONS}
        ariaLabel="能力档位"
        disabled
      />
    );
    expect(screen.getByRole("combobox").getAttribute("data-disabled")).not.toBe(
      null
    );
  });

  it("不使用原生 select 元素", () => {
    const { container } = render(
      <Select
        value="readonly"
        onChange={vi.fn()}
        options={OPTIONS}
        ariaLabel="能力档位"
      />
    );
    expect(container.querySelector("select")).toBe(null);
  });
});
