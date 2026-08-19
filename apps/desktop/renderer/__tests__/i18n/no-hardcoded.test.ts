import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "../..");

/**
 * 迁移白名单 —— 尚未抽 key 的文件。**每迁完一块删一行，最终必须清空**（判据 2）。
 * 不要往里加新文件：新写的界面从第一天就该用 t()。
 */
const PENDING = new Set<string>([
  "App.tsx",
  // useFindings 正则含「条」「高危」是刻意的摘要匹配（不得改），UI 文案已抽 key
  "components/context/ContextRail.tsx",
  "components/session/SessionRail.tsx",
  "components/shell/AppChrome.tsx",
  "lib/llmPresets.ts",
  "state/UiPrefsProvider.tsx",
  "state/useExport.ts",
  "state/usePlan.tsx",
  "state/useUninstall.ts",
  "ui/Timestamp.tsx",
  "views/settings/AboutSection.tsx",
  "views/settings/AppearanceSection.tsx",
  "views/settings/DataSection.tsx",
  "views/settings/HubSection.tsx",
  "views/settings/LlmSection.tsx",
  "views/settings/McpSection.tsx",
  "views/settings/SettingsShell.tsx",
  "views/settings/SkillsSection.tsx",
  "views/settings/useLlmSection.ts",
  "views/settings/useMcpSection.ts",
  "views/settings/useSkillsSection.ts",
]);

const CJK = /[一-鿿]/;

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "__tests__" || name === "i18n" || name === "node_modules") continue;
      walk(full, out);
    } else if (/\.tsx?$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

/** 去掉注释后再看 —— 注释保持中文是明确决定（spec §2.2） */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !/^\s*(\/\/|\*)/.test(l))
    .join("\n");
}

describe("渲染层无硬编码中文", () => {
  const files = walk(ROOT).filter((f) => !f.includes("__tests__"));

  it.each(files.map((f) => path.relative(ROOT, f)))("%s", (rel) => {
    if (PENDING.has(rel)) return; // 迁移中，见 PENDING 注释
    const code = stripComments(readFileSync(path.join(ROOT, rel), "utf8"));
    const offenders = code
      .split("\n")
      .map((line, i) => ({ line: line.trim(), no: i + 1 }))
      .filter((x) => CJK.test(x.line));
    expect(
      offenders.map((o) => `${rel}:${o.no} ${o.line.slice(0, 60)}`)
    ).toEqual([]);
  });
});
