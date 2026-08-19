import { describe, expect, it } from "vitest";
import en from "../../i18n/en.json";
import zh from "../../i18n/zh.json";

/** 判据 1：任何一边多一条或少一条都算漏，这条测试是迁移期唯一的完备性信号 */
describe("词条键集", () => {
  it("zh 与 en 的 key 完全相同", () => {
    const zhKeys = Object.keys(zh).sort();
    const enKeys = Object.keys(en).sort();
    expect(enKeys.filter((k) => !zhKeys.includes(k))).toEqual([]);
    expect(zhKeys.filter((k) => !enKeys.includes(k))).toEqual([]);
  });

  it("没有空值 —— 空串等于漏译", () => {
    for (const [k, v] of Object.entries({ ...zh, ...en })) {
      expect(String(v).trim(), `${k} 是空的`).not.toBe("");
    }
  });

  it("复数 key 成对出现", () => {
    const keys = Object.keys(zh);
    for (const k of keys.filter((x) => x.endsWith("_one"))) {
      expect(keys, `${k} 缺对应的 _other`).toContain(
        k.replace(/_one$/, "_other")
      );
    }
  });
});
