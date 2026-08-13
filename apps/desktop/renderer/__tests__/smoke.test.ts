import { describe, expect, it } from "vitest";

describe("test harness", () => {
  it("runs in jsdom", () => {
    expect(typeof window).toBe("object");
    expect(typeof document.createElement("div")).toBe("object");
  });
});
