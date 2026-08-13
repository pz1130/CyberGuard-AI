import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const read = (p: string) =>
  readFileSync(path.resolve(__dirname, "../../", p), "utf8");

/** Workbench 已迁走的旧类名，不得再出现在遗留样式文件里 */
const RETIRED = [
  ".workbench",
  ".col-main",
  ".col-context",
  ".timeline-wrap",
  ".composer",
  ".ev ",
  ".ready-card",
  ".sample-chip",
  ".alert-strip",
  ".chrome-nav",
  ".nav-tab",
  ".context-advanced",
  ".tool-chips",
];

describe("遗留样式清理", () => {
  const legacy = read("styles.css") + "\n" + read("styles/views.css");

  it.each(RETIRED)("%s 已从遗留样式中移除", (sel) => {
    expect(legacy).not.toContain(sel);
  });
});
