import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  path.resolve(__dirname, "../../styles/tokens.css"),
  "utf8"
);

/** 取某个选择器块里的 token 值 */
function tokensIn(selector: string): Record<string, string> {
  const i = css.indexOf(selector);
  expect(i, `selector ${selector} not found`).toBeGreaterThan(-1);
  const open = css.indexOf("{", i);
  const close = css.indexOf("}", open);
  const body = css.slice(open + 1, close);
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

function srgbToLinear(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

/** WCAG 相对亮度。只接受 #rrggbb —— 参与对比度计算的 token 不许用 rgba */
function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  expect(m, `${hex} 不是 #rrggbb —— 参与对比度计算的 token 必须是不透明色`)
    .not.toBeNull();
  const n = parseInt(m![1], 16);
  const r = srgbToLinear((n >> 16) & 255);
  const g = srgbToLinear((n >> 8) & 255);
  const b = srgbToLinear(n & 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(fg: string, bg: string): number {
  const a = luminance(fg);
  const b = luminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** 承载信息的文本类 token —— 对三个面取最坏值都要过 4.5 */
const TEXT_TOKENS = [
  "--text",
  "--text-muted",
  "--accent-text",
  "--ok",
  "--warn",
  "--danger",
  "--info",
  "--plan",
];

const SURFACES = ["--layer-0", "--layer-1", "--layer-2"];

describe.each([
  ["light", ':root,\nhtml[data-theme="light"]'],
  ["dark", 'html[data-theme="dark"]'],
])("%s 主题对比度", (_name, selector) => {
  const t = tokensIn(selector);

  it.each(TEXT_TOKENS)("%s 对三个面最坏值 ≥ 4.5:1", (token) => {
    const worst = Math.min(...SURFACES.map((s) => contrast(t[token], t[s])));
    expect(Number(worst.toFixed(2))).toBeGreaterThanOrEqual(4.5);
  });

  // 装饰级，豁免 4.5 但不得低于 3 —— 规则见 spec §1.3
  it("--text-faint 对三个面最坏值 ≥ 3:1", () => {
    const worst = Math.min(
      ...SURFACES.map((s) => contrast(t["--text-faint"], t[s]))
    );
    expect(Number(worst.toFixed(2))).toBeGreaterThanOrEqual(3);
  });

  it("--accent 实底配 --text-inverse ≥ 4.5:1", () => {
    expect(
      Number(contrast(t["--text-inverse"], t["--accent"]).toFixed(2))
    ).toBeGreaterThanOrEqual(4.5);
  });
});
