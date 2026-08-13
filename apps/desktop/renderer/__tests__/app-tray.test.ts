import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const APP = resolve(__dirname, "../App.tsx");

describe("托盘打开数据页", () => {
  it("AppInner 订阅 onOpenDataPanel 并打开 settings/data", () => {
    const src = readFileSync(APP, "utf8");
    expect(src).toMatch(/api\.onOpenDataPanel\(\(\) => openSettings\("data"\)\)/);
  });
});
