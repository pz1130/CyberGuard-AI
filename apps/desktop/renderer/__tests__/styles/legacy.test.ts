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
  /* T5: shell chrome 在 AppChrome.css；views.css 旧块会压过 40px */
  ".chrome-brand",
  ".chrome-icon-btn",
  ".chrome-left",
];

describe("遗留样式清理", () => {
  const legacy = read("styles.css") + "\n" + read("styles/views.css");

  it.each(RETIRED)("%s 已从遗留样式中移除", (sel) => {
    expect(legacy).not.toContain(sel);
  });

  it("views.css 不得再给 .chrome 设 min-height: 48px（会压过 AppChrome 40px）", () => {
    const views = read("styles/views.css");
    expect(views).not.toMatch(/\.chrome\s*\{[^}]*min-height:\s*48px/s);
  });
});
