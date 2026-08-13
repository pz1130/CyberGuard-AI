import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  path.resolve(__dirname, "../../styles/tokens.css"),
  "utf8"
);

// 主题相关：深浅两套都必须定义
const REQUIRED_PAIRED = [
  "--layer-0",
  "--layer-1",
  "--layer-2",
  "--layer-3",
  "--border-0",
  "--border-1",
  "--border-2",
  "--shadow-1",
  "--shadow-2",
  "--shadow-3",
  "--text",
  "--text-muted",
  "--text-faint",
  "--accent",
  "--ok",
  "--warn",
  "--danger",
  "--info",
  "--plan",
];

// 主题无关：定义一次即可
const REQUIRED_ONCE = [
  "--text-2xs",
  "--text-xs",
  "--text-sm",
  "--text-base",
  "--text-md",
  "--text-lg",
  "--text-xl",
  "--leading-tight",
  "--leading-normal",
  "--leading-relaxed",
  "--sp-1",
  "--sp-2",
  "--sp-3",
  "--sp-4",
  "--sp-5",
  "--sp-6",
  "--sp-8",
  "--sp-10",
  "--motion-fast",
  "--motion-base",
];

function blockFor(selector: string): string {
  const i = css.indexOf(selector);
  expect(i, `selector ${selector} not found`).toBeGreaterThan(-1);
  const open = css.indexOf("{", i);
  const close = css.indexOf("}", open);
  return css.slice(open, close);
}

describe("tokens.css", () => {
  const dark = blockFor('html[data-theme="dark"]');
  const light = blockFor('html[data-theme="light"]');

  it.each(REQUIRED_PAIRED)("%s 在深浅两套主题下都有定义", (token) => {
    expect(dark).toContain(`${token}:`);
    expect(light).toContain(`${token}:`);
  });

  it.each(REQUIRED_ONCE)("%s 已定义", (token) => {
    expect(css).toContain(`${token}:`);
  });

  it("字重不使用 700", () => {
    expect(css).not.toMatch(/font-weight:\s*(700|bold)/);
  });
});
