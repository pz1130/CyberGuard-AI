import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import en from "../../i18n/en.json";
import zh from "../../i18n/zh.json";

const glossary = readFileSync(
  path.resolve(__dirname, "../../../../../docs/desktop/06-GLOSSARY.md"),
  "utf8"
);

/**
 * 术语表定稿后挡漂移：中文出现表内术语时，英文必须用表定译法。
 * 防的是后续加词条时把 sandbox unavailable 写成 sandbox not working。
 */
const TERMS: Array<[zh: string, en: RegExp]> = [
  ["沙箱", /sandbox/i],
  ["只读", /read-only/i],
  ["证据", /evidence/i],
  ["审批", /approval|approve/i],
  ["降级", /degrad/i],
  ["自批准", /self-approve/i],
  ["批准", /approv/i],
  ["拒绝", /reject/i],
  ["提权", /privilege/i],
  ["高危", /high-severity/i],
  // 「完整」单独匹配会误伤「完整性 OK」→ Integrity OK；档位 Full 由 statusbar/composer.tier 键覆盖
  ["权限", /permission/i],
];

describe("英文词条与 06-GLOSSARY 术语一致", () => {
  it("术语表本身含这些词条", () => {
    for (const [term] of TERMS) {
      expect(glossary, `06-GLOSSARY 缺术语 ${term}`).toContain(term);
    }
  });

  it.each(TERMS)("中文含「%s」时英文须用表定译法", (term, pattern) => {
    const offenders = Object.keys(zh)
      .filter((k) => String((zh as Record<string, string>)[k]).includes(term))
      .filter(
        (k) => !pattern.test(String((en as Record<string, string>)[k] ?? ""))
      );
    expect(offenders).toEqual([]);
  });

  it("沙箱 / mock 禁止语用表定英文整句", () => {
    expect(en["degradation.sandbox.label"]).toBe("Sandbox unavailable");
    expect(en["degradation.mock.detail"]).toBe(
      "No real model configured; output must not be used as findings"
    );
  });
});
