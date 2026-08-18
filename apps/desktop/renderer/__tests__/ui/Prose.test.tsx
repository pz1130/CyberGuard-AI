import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Prose } from "../../ui";

describe("Prose", () => {
  it("包一层 ui-prose 容器", () => {
    render(<Prose><p>报告正文</p></Prose>);
    expect(screen.getByText("报告正文").closest(".ui-prose")).toBeTruthy();
  });
});
