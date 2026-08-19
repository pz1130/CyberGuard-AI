import { describe, expect, it } from "vitest";
import { interpolate, pickPluralKey } from "../../i18n/plural";

describe("pickPluralKey", () => {
  it("en 的 1 取 _one，其余取 _other", () => {
    expect(pickPluralKey("en", "evidence.count", 1)).toBe("evidence.count_one");
    expect(pickPluralKey("en", "evidence.count", 0)).toBe("evidence.count_other");
    expect(pickPluralKey("en", "evidence.count", 7)).toBe("evidence.count_other");
  });

  // 中文没有单复数变化，恒取 _other —— 不是偷懒，是语言事实
  it("zh 恒取 _other", () => {
    for (const n of [0, 1, 7]) {
      expect(pickPluralKey("zh", "evidence.count", n)).toBe("evidence.count_other");
    }
  });
});

describe("interpolate", () => {
  it("替换 {n} 且不求值表达式", () => {
    expect(interpolate("库中 {n} 件", { n: 3 })).toBe("库中 3 件");
    expect(interpolate("{a} → {b}", { a: "x", b: "y" })).toBe("x → y");
  });

  it("缺参数时原样保留占位符，不抛错", () => {
    expect(interpolate("库中 {n} 件", {})).toBe("库中 {n} 件");
  });
});
