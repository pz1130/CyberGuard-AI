import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../../ui/Button";

describe("Button", () => {
  it("默认是 secondary + md，且 type=button", () => {
    render(<Button>运行</Button>);
    const btn = screen.getByRole("button", { name: "运行" });
    expect(btn.className).toContain("ui-btn--secondary");
    expect(btn.className).toContain("ui-btn--md");
    expect(btn.getAttribute("type")).toBe("button");
  });

  it.each([
    ["primary", "ui-btn--primary"],
    ["danger", "ui-btn--danger"],
    ["ghost", "ui-btn--ghost"],
  ] as const)("variant=%s 落到类名 %s", (variant, cls) => {
    render(<Button variant={variant}>x</Button>);
    expect(screen.getByRole("button").className).toContain(cls);
  });

  it("disabled 时不触发 onClick 且带 aria-disabled", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        x
      </Button>
    );
    const btn = screen.getByRole("button");
    btn.click();
    expect(onClick).not.toHaveBeenCalled();
    expect(btn.getAttribute("aria-disabled")).toBe("true");
  });

  it("允许外部追加 className", () => {
    render(<Button className="extra">x</Button>);
    expect(screen.getByRole("button").className).toContain("extra");
  });
});
