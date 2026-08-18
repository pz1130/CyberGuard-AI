import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListRow } from "../../ui";

describe("ListRow", () => {
  it("默认不带 variant 类", () => {
    render(<ListRow title="告警分诊" />);
    expect(screen.getByText("告警分诊").closest(".ui-listrow")!.className).not.toContain(
      "ui-listrow--nav"
    );
  });

  it("variant=nav 渲染 ui-listrow--nav", () => {
    render(<ListRow variant="nav" title="设置" />);
    expect(screen.getByText("设置").closest(".ui-listrow")!.className).toContain(
      "ui-listrow--nav"
    );
  });

  it("active 时 aria-current 为 true", () => {
    render(<ListRow variant="nav" active title="调查" onClick={() => {}} />);
    expect(
      screen.getByRole("button", { name: "调查" }).getAttribute("aria-current")
    ).toBe("true");
  });
});
