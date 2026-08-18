# 桌面端 Claude 风格视觉改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CyberGuard 桌面端的观感与信息架构改成 Claude macOS 客户端风格（暖米白色板 + 左栏导航 + 居中限宽单栏），同时把安全状态栏升为不可折叠的全宽贴底栏。

**Architecture:** 路线 A —— 先换 token（全局立刻生效），再扩 primitives，再重排外壳，最后三个视图逐个迁。状态栏与左栏从 `WorkbenchView` 内部提升到 `App` 级，因此证据页与设置页也共享同一外壳。primitives 的 TS 接口只做加法（新增 variant / size），已有消费方零改动。

**Tech Stack:** React 19 + Vite + TypeScript + 原生 CSS 变量（无 Tailwind、无 UI 框架）· Radix Select/Tooltip · Vitest + @testing-library/react · jsdom

**Spec:** `docs/superpowers/specs/2026-08-18-desktop-claude-visual-design.md`

## Global Constraints

- **分支**：`feature/desktop-claude-visual`。一个界面 / 一层一次提交（CLAUDE.md 工作流约定）。
- **纯渲染层改动**。不得修改 `app/`、`packages/`、`apps/desktop/sidecar/`、JSONL 协议。`tests/test_desktop_*.py` 的 138 个测试**理应一个字都不用改**；需要动它们就是越界信号，停下来。
- **不引入任何新依赖**。不引入 Tailwind、UI 组件库、CSS-in-JS、字体文件。
- **不打包品牌字体**。衬线走 `ui-serif, "New York", "Iowan Old Style", Georgia, serif`（macOS 自带）。
- **不做快照测试。**
- **不动 `ContextRail.useFindings()` 的正则与其注释** —— 那条决策登记在 `docs/desktop/11-OPEN-QUESTIONS.md` §I，等 M1.5 真实数据，不在本轮范围。
- **accent 只做填充，状态色只做「点 + 文字」**（spec §1.3）。唯一例外是降级浮出条与异常态状态栏，允许整条染 `*-muted` 底。
- **状态栏常显五项**（连接 / 沙箱 / 权限 / Provider / 档位）不得随任何面板折叠而消失（INV-36 / INV-38 / M2 判据 10）；第六项「暂停」按 `paused` 出现。
- **对比度**：文本类 token 对 `--layer-0/1/2` 取最坏值须 ≥4.5:1；`--text-faint` 豁免但须 ≥3:1；`--accent` 实底配 `--text-inverse` 须 ≥4.5:1。两套主题各一遍。
- 每个任务结束时全套必须绿：
  ```bash
  cd apps/desktop && npm run test && npm run typecheck
  cd ../.. && PYTHONPATH="packages:$(pwd)" .venv/bin/python -m pytest -q tests/test_desktop_*.py
  ```

---

## File Structure

**新建**

| 文件 | 职责 |
|---|---|
| `renderer/__tests__/styles/contrast.test.ts` | WCAG 对比度断言（判据 4） |
| `renderer/__tests__/shell/statusbar.always.test.tsx` | 常显五项（判据 2；暂停项按 `paused` 出现） |
| `renderer/__tests__/shell/degradation.test.tsx` | 降级显著告警（判据 3） |
| `renderer/__tests__/shell/responsive.test.tsx` | 断点与折叠持久化 |
| `renderer/components/shell/Sidebar.tsx` / `.css` | 左栏容器：新建 + 会话列表 + 底部视图导航 |
| `renderer/components/shell/ViewNav.tsx` | 左栏底部「调查 / 证据 / 设置」 |
| `renderer/state/UiPrefsProvider.tsx` | `useUiPrefs` 升为 context，含折叠状态 |
| `renderer/ui/Prose.tsx` / `.css` | Markdown 答案排版容器 |
| `renderer/views/settings/*.tsx` | Settings 壳 + 七个分区 |

**修改**

| 文件 | 改什么 |
|---|---|
| `renderer/styles/tokens.css` | 全量换血（T1） |
| `renderer/hooks/useTheme.ts:33` | 默认主题 `"dark"` → `"system"`（T1） |
| `renderer/ui/Button.tsx` `.css` | 新增 `size="icon"`，质感（T2） |
| `renderer/ui/ListRow.tsx` `.css` | 新增 `variant="nav"`，质感（T2） |
| `renderer/components/context/StatusBar.tsx` `.css` | 移出 ContextRail，改全宽（T3） |
| `renderer/components/context/ContextRail.tsx` | 删掉 `<StatusBar />`（T3） |
| `renderer/App.tsx` | 挂 Sidebar / StatusBar / UiPrefsProvider（T3–T6） |
| `renderer/components/shell/AppShell.css` | 外壳 grid（T3–T6） |
| `renderer/components/shell/AppChrome.tsx` `.css` | 压到 40px，nav 移走（T5） |
| `renderer/views/WorkbenchView.tsx` | 移出 SessionRail（T4），限宽（T7） |
| `renderer/components/session/SessionRail.tsx` | 去掉 Panel 外壳，融进 Sidebar（T4） |
| `renderer/views/SettingsView.tsx` | 拆解（T8/T9） |
| `renderer/views/EvidenceView.tsx` | 套 primitives（T10） |
| `renderer/styles.css` `styles/views.css` | 清遗留（T11） |

**任务与 spec §7 的映射**：T1=①、T3–T6=②、T2/T7=③④、T8/T9=⑤、T10=⑥、T11=⑦。**T7 结束后是人工检查点**（spec §7 的「停下来看比例」）。

---

### Task 1: token 换血与对比度闸门

**Files:**
- Create: `renderer/__tests__/styles/contrast.test.ts`
- Modify: `renderer/styles/tokens.css`（全量重写）
- Modify: `renderer/hooks/useTheme.ts:33`

**Interfaces:**
- Consumes: 无
- Produces: 新 token 名 `--accent-hover` / `--accent-text` / `--font-serif` / `--radius-pill` / `--sp-12` / `--sp-16` / `--measure`，供 T2 起所有任务使用。`--bg` / `--surface` 等旧别名**本任务保留**，T11 才删。

- [x] **Step 1: 写失败的对比度测试**

Create `renderer/__tests__/styles/contrast.test.ts`:

```ts
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
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/styles/contrast.test.ts
```
Expected: FAIL —— 现有冷色板里 `--accent-text` / `--accent-hover` 未定义（`undefined` 进 `luminance` 会命中 `不是 #rrggbb` 断言），且深色 `--text-muted` 等多项对 `--layer-2` 不足 4.5。

- [x] **Step 3: 全量重写 `renderer/styles/tokens.css`**

```css
/* CyberGuard desktop — 设计 token
 * 分三组：主题无关标量（字阶/间距阶/圆角/动效）、浅色主题、深色主题。
 * 层级硬规则：相邻嵌套必须差一级，同级不套同级。
 *
 * 【硬规则 · spec §1.3】accent 只做填充（主按钮底、选中态底、focus ring），
 * 作文字时用 --accent-text，**永不作状态点**；状态色只做「点 + 文字」或
 * 细边框染色，**永不做大面积填充**。唯一例外是降级浮出条与异常态状态栏。
 *
 * 【改色前先跑】renderer/__tests__/styles/contrast.test.ts
 * 参与对比度计算的 token 必须是不透明 #rrggbb。
 */

:root {
  /* 字阶 */
  --text-2xs: 12px;
  --text-xs: 13px;
  --text-sm: 14px;
  --text-base: 15px;
  --text-md: 17px;
  --text-lg: 22px;
  --text-xl: 30px;

  /* 行高 */
  --leading-tight: 1.3;
  --leading-normal: 1.6;
  --leading-relaxed: 1.75;

  /* 间距阶（4px 基） */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 20px;
  --sp-6: 24px;
  --sp-8: 32px;
  --sp-10: 40px;
  --sp-12: 48px;
  --sp-16: 64px;

  /* 圆角 */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 18px;
  --radius-xl: 24px;
  --radius-pill: 999px;

  /* 动效：只两档 */
  --motion-fast: 150ms;
  --motion-base: 180ms;
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);

  /* 字体。--font-serif 只用于视图标题与空态大标题（spec §1.4） */
  --font-ui: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
    system-ui, sans-serif;
  --font-serif: ui-serif, "New York", "Iowan Old Style", Georgia, serif;
  --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;

  --measure: 736px; /* 主体内容限宽。实现落为 px 而非 46rem —— 根字号随
                        data-font 变，rem 会让列宽跟着字号伸缩。见 spec §1 */
  --chrome-pad-left: 78px; /* macOS 交通灯留位 */
}

/* 浅色是主形态。默认（无 data-theme）即浅色。 */
:root,
html[data-theme="light"] {
  color-scheme: light;

  /* 层级阶：侧栏沉（深），主体浮（浅），卡片最亮 */
  --layer-0: #f0eee6; /* 左栏 / 状态栏 */
  --layer-1: #faf9f5; /* 主体画布 */
  --layer-2: #ffffff; /* 卡片 / composer */
  --layer-3: #ffffff; /* 浮层（靠 shadow-3 区分） */

  --border-0: rgba(60, 50, 40, 0.06);
  --border-1: rgba(60, 50, 40, 0.1);
  --border-2: rgba(60, 50, 40, 0.18);

  --shadow-1: 0 1px 2px rgba(60, 50, 40, 0.06);
  --shadow-2: 0 4px 12px rgba(60, 50, 40, 0.08);
  --shadow-3: 0 12px 40px rgba(60, 50, 40, 0.14);

  --text: #1f1e1d;
  --text-muted: #6b6a66;
  --text-faint: #87857e; /* 装饰级，不得单独承载信息 */
  --text-inverse: #faf9f5;

  /* 实底比 Claude 的 #d97757 深一档：白字压原色只有 3.2:1，过不了判据 4 */
  --accent: #b4572f;
  --accent-hover: #9e4b27;
  --accent-text: #a8492a;
  --accent-muted: rgba(180, 87, 47, 0.1);
  --accent-glow: rgba(180, 87, 47, 0.22);
  --accent-2: #2c6baa; /* legacy alias — styles.css / views.css */

  /* 状态色基准面是 --layer-0（最深的面），不是主体画布 */
  --ok: #2a7353;
  --ok-muted: rgba(42, 115, 83, 0.1);
  --warn: #9c5d00;
  --warn-muted: rgba(156, 93, 0, 0.12);
  --danger: #b4241c;
  --danger-muted: rgba(180, 36, 28, 0.1);
  --info: #2c6baa;
  --info-muted: rgba(44, 107, 170, 0.1);
  --plan: #6d4fa8;
  --plan-muted: rgba(109, 79, 168, 0.1);
}

html[data-theme="dark"] {
  color-scheme: dark;

  /* Claude 的暖深灰，不是蓝黑 */
  --layer-0: #1f1e1d;
  --layer-1: #262624;
  --layer-2: #30302e;
  --layer-3: #3a3a38;

  --border-0: rgba(245, 244, 239, 0.06);
  --border-1: rgba(245, 244, 239, 0.1);
  --border-2: rgba(245, 244, 239, 0.18);

  --shadow-1: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-2: 0 4px 12px rgba(0, 0, 0, 0.35);
  --shadow-3: 0 12px 40px rgba(0, 0, 0, 0.45);

  --text: #f5f4ef;
  --text-muted: #a8a69f;
  --text-faint: #7a7873;
  --text-inverse: #1f1e1d;

  --accent: #d97757;
  --accent-hover: #e8a087;
  --accent-text: #e08b6b; /* #d97757 作文字对 --layer-2 只有 4.3 */
  --accent-muted: rgba(217, 119, 87, 0.14);
  --accent-glow: rgba(217, 119, 87, 0.28);
  --accent-2: #6fa8dc;

  /* 基准面是 --layer-2（最亮的面） */
  --ok: #5fbf8f;
  --ok-muted: rgba(95, 191, 143, 0.14);
  --warn: #e0a038;
  --warn-muted: rgba(224, 160, 56, 0.14);
  --danger: #f08a80; /* #e8695f 只有 4.2 */
  --danger-muted: rgba(240, 138, 128, 0.14);
  --info: #6fa8dc;
  --info-muted: rgba(111, 168, 220, 0.14);
  --plan: #a78bfa;
  --plan-muted: rgba(167, 139, 250, 0.14);
}

/* 兼容层：旧组件仍引用的别名，T11 随 Settings/Evidence 迁完删除。
 * 新代码禁止使用这些别名。 */
:root,
html[data-theme="dark"],
html[data-theme="light"] {
  --bg: var(--layer-0);
  --bg-elevated: var(--layer-1);
  --bg-deep: var(--layer-0);
  --surface: var(--layer-2);
  --surface-solid: var(--layer-2);
  --surface-hover: var(--layer-3);
  --border: var(--border-1);
  --border-subtle: var(--border-0);
  --border-strong: var(--border-2);
  --panel: var(--layer-1);
  --muted: var(--text-muted);
  --shadow-panel: var(--shadow-3);
  --shadow-soft: none;
}
```

- [x] **Step 4: 跑对比度测试确认通过**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/styles/contrast.test.ts
```
Expected: PASS（两套主题各 10 项）

- [x] **Step 5: 默认主题从 dark 改 system**

`renderer/hooks/useTheme.ts:33`，`readStored()` 的兜底返回值：

```ts
  return "system";
```

理由：浅色升为主形态后，默认应跟随系统而非硬编码深色。

- [x] **Step 6: 跑全套**

```bash
cd apps/desktop && npm run test && npm run typecheck
```
Expected: 全绿。`styles/tokens.test.ts` 的既有断言（成对定义、无 `font-weight: 700`）应原样通过——新文件保留了全部被断言的 token 名。

- [x] **Step 7: 提交**

```bash
git add renderer/styles/tokens.css renderer/hooks/useTheme.ts \
        renderer/__tests__/styles/contrast.test.ts
git commit -m "feat(desktop-ui): token 换血为暖米白 + 赤陶，对比度进测试

浅色升为主形态，默认主题跟随系统。色值全部实算 WCAG 并锁进
contrast.test.ts：文本类对三个面最坏值 ≥4.5，--text-faint 豁免
但 ≥3，accent 实底配反色字 ≥4.5。

浅色 accent 刻意比 Claude 的 #d97757 深一档（白字压原色 3.2:1），
状态色基准面取 --layer-0 而非主体画布（同一个绿差 0.6）。

此时 Settings/Evidence 会配色已变、排布仍旧 —— 预期内，T8-T10 处理。"
```

---

### Task 2: primitives 扩展与质感

**Files:**
- Modify: `renderer/ui/Button.tsx`, `renderer/ui/Button.css`
- Modify: `renderer/ui/ListRow.tsx`, `renderer/ui/ListRow.css`
- Modify: `renderer/ui/Card.css`, `renderer/ui/Panel.css`, `renderer/ui/Select.css`, `renderer/ui/Field.css`
- Test: `renderer/__tests__/ui/Button.test.tsx`（扩充）

**Interfaces:**
- Consumes: T1 的 `--radius-pill` / `--accent-hover` / `--sp-*`
- Produces:
  - `ButtonSize = "sm" | "md" | "icon"` —— T5 顶栏两个开关消费
  - `ListRowProps.variant?: "default" | "nav"` —— T4 左栏会话行与视图导航消费

- [x] **Step 1: 写失败的测试**

追加到 `renderer/__tests__/ui/Button.test.tsx`：

```tsx
it("size=icon 渲染 ui-btn--icon", () => {
  render(<Button size="icon" aria-label="切换侧栏">☰</Button>);
  expect(screen.getByLabelText("切换侧栏").className).toContain("ui-btn--icon");
});
```

新建 `renderer/__tests__/ui/ListRow.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListRow } from "../../ui";

describe("ListRow", () => {
  it("默认不带 variant 类", () => {
    render(<ListRow title="告警分诊" />);
    expect(screen.getByText("告警分诊").closest(".ui-listrow")!.className)
      .not.toContain("ui-listrow--nav");
  });

  it("variant=nav 渲染 ui-listrow--nav", () => {
    render(<ListRow variant="nav" title="设置" />);
    expect(screen.getByText("设置").closest(".ui-listrow")!.className)
      .toContain("ui-listrow--nav");
  });

  it("active 时 aria-current 为 true", () => {
    render(<ListRow variant="nav" active title="调查" onClick={() => {}} />);
    expect(screen.getByRole("button", { name: "调查" }))
      .toHaveAttribute("aria-current", "true");
  });
});
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/ui/
```
Expected: FAIL —— `size="icon"` 不在 `ButtonSize` 联合类型里、`variant` 不是 `ListRowProps` 的属性。

- [x] **Step 3: 扩类型**

`renderer/ui/Button.tsx`：

```ts
export type ButtonSize = "sm" | "md" | "icon";
```

`renderer/ui/ListRow.tsx` 全量：

```tsx
import type { ReactNode } from "react";
import "./ListRow.css";

export type ListRowVariant = "default" | "nav";

export type ListRowProps = {
  active?: boolean;
  title: ReactNode;
  meta?: ReactNode;
  onClick?: () => void;
  actions?: ReactNode;
  variant?: ListRowVariant;
};

export function ListRow({
  active,
  title,
  meta,
  onClick,
  actions,
  variant = "default",
}: ListRowProps) {
  const cls = [
    "ui-listrow",
    variant !== "default" ? `ui-listrow--${variant}` : "",
    active ? "ui-listrow--active" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      <button
        type="button"
        className="ui-listrow-main"
        onClick={onClick}
        aria-current={active || undefined}
      >
        <span className="ui-listrow-title">{title}</span>
        {meta ? <span className="ui-listrow-meta">{meta}</span> : null}
      </button>
      {actions ? <div className="ui-listrow-actions">{actions}</div> : null}
    </div>
  );
}
```

`renderer/ui/index.ts` 追加导出：

```ts
export type { ListRowProps, ListRowVariant } from "./ListRow";
```

- [x] **Step 4: 跑测试确认通过**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/ui/
```
Expected: PASS

- [x] **Step 5: 调质感（纯 CSS）**

`Button.css`：`.ui-btn` 圆角改 `var(--radius-pill)`；`.ui-btn--primary` 用 `background: var(--accent); color: var(--text-inverse)`，hover 换 `--accent-hover`；`.ui-btn--ghost` 的 hover 从描边改为 `background: var(--accent-muted)`；新增

```css
.ui-btn--icon {
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: var(--radius-pill);
  font-size: var(--text-md);
}
```

`ListRow.css` 新增：

```css
.ui-listrow--nav > .ui-listrow-main {
  border-radius: var(--radius-pill);
  padding: var(--sp-2) var(--sp-3);
}
.ui-listrow--nav:hover > .ui-listrow-main {
  background: var(--border-0);
}
.ui-listrow--nav.ui-listrow--active > .ui-listrow-main {
  background: var(--accent-muted);
  color: var(--accent-text);
}
```

`Card.css` / `Panel.css`：背景 `var(--layer-2)`、边框 `var(--border-0)`、`box-shadow: var(--shadow-1)`、圆角 `var(--radius-lg)`。
`Select.css`：触发器 `border-radius: var(--radius-pill)`；浮层 `background: var(--layer-3); box-shadow: var(--shadow-3)`。
`Field.css`：标签降一级字阶（`var(--text-xs)`），`description` 用 `var(--text-muted)`，行间距用 `var(--sp-2)`。

> `StatusDot.css` **不要加底色** —— 状态色只做点 + 文字（Global Constraints）。

- [x] **Step 6: 跑全套并提交**

```bash
cd apps/desktop && npm run test && npm run typecheck
git add renderer/ui renderer/__tests__/ui
git commit -m "feat(desktop-ui): primitives 扩 icon/nav 两个变体并调质感

Button 加 size=icon（顶栏开关用），ListRow 加 variant=nav（左栏会话行
与视图导航共用）。两者都是加法，已有消费方零改动。

其余 primitive 只动 CSS：圆角放大、边框减轻、ghost hover 从描边改为
accent-muted 底。StatusDot 保持只有点+文字，不加底色。"
```

---

### Task 3: 状态栏升为 shell 级全宽贴底栏

这是本轮唯一硬碰安全约束的改动。状态栏现在长在 `ContextRail` 内部（`ContextRail.tsx` 末尾），右栏一旦可折叠它就会跟着消失，违反 INV-36。

**Files:**
- Modify: `renderer/components/context/ContextRail.tsx`（删 `<StatusBar />` 与其 import）
- Modify: `renderer/components/context/StatusBar.css`（改横向全宽）
- Modify: `renderer/App.tsx`（在 view pane 之后挂 `<StatusBar />`）
- Modify: `renderer/components/shell/AppShell.css`
- Test: `renderer/__tests__/shell/statusbar.always.test.tsx`（新建）

**Interfaces:**
- Consumes: T1 token
- Produces: `<StatusBar onOpenSettings={…} />` 由 `App` 直接渲染，与 `activeView` 无关。T6 依赖这一点做四组合断言。

- [x] **Step 1: 写失败的测试**

Create `renderer/__tests__/shell/statusbar.always.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../../App";

/** 六项常显 —— INV-36 / INV-38 / M2 判据 10 */
function expectSixVisible() {
  const bar = screen.getByRole("contentinfo", { name: "运行态" });
  expect(bar).toBeTruthy();
  for (const label of ["沙箱", "权限"]) {
    expect(bar.textContent).toContain(label);
  }
  // 连接态三选一
  expect(bar.textContent).toMatch(/在线|离线|连接中/);
  // Provider 档位二选一
  expect(bar.textContent).toMatch(/live|mock/);
  // 能力档位二选一
  expect(bar.textContent).toMatch(/只读|完整/);
}

describe("状态栏常显", () => {
  it("调查页可见", () => {
    render(<App />);
    expectSixVisible();
  });

  it("切到证据页仍可见", async () => {
    render(<App />);
    screen.getByRole("button", { name: "证据" }).click();
    expectSixVisible();
  });

  it("切到设置页仍可见", async () => {
    render(<App />);
    screen.getByRole("button", { name: "设置" }).click();
    expectSixVisible();
  });

  it("不再是 ContextRail 的子节点", () => {
    render(<App />);
    const bar = screen.getByRole("contentinfo", { name: "运行态" });
    expect(bar.closest(".ctxrail")).toBeNull();
  });
});
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/shell/statusbar.always.test.tsx
```
Expected: FAIL —— `getByRole("contentinfo")` 找不到（`StatusBar` 现在渲染的是无 role 的 `<div className="statusbar">`），且它长在 `.ctxrail` 里。

- [x] **Step 3: 给 StatusBar 加 landmark role**

`renderer/components/context/StatusBar.tsx`，把最外层 `<div className="statusbar">` 换成：

```tsx
    <footer className="statusbar" aria-label="运行态">
```

对应的闭合标签改为 `</footer>`。

- [x] **Step 4: 从 ContextRail 摘掉**

`renderer/components/context/ContextRail.tsx`：删掉 `import { StatusBar } from "./StatusBar";` 与文件末尾的 `<StatusBar onOpenSettings={onOpenSettings} />` 一行。`onOpenSettings` 仍被「数据源」按钮使用，**不要删这个 prop**。

- [x] **Step 5: 在 App 挂上**

`renderer/App.tsx`，在三个 `activeView` 分支之后、`</div>` 之前插入：

```tsx
        <StatusBar onOpenSettings={openSettings} />
```

并在文件顶部 import：

```tsx
import { StatusBar } from "./components/context/StatusBar";
```

- [x] **Step 6: 改成全宽横条**

`renderer/components/context/StatusBar.css`：`.statusbar` 改为

```css
.statusbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  height: 26px;
  padding: 0 var(--sp-4);
  background: var(--layer-0);
  border-top: 1px solid var(--border-0);
  font-size: var(--text-2xs);
  color: var(--text-muted);
}
.statusbar-row { display: flex; align-items: center; gap: var(--sp-3); }
.statusbar-more { margin-left: auto; }
```

`renderer/components/shell/AppShell.css` 的 `.app-shell > .view-pane` 已是 `flex: 1; min-height: 0`，状态栏作为最后一个 flex 子项自然贴底，无需改动。

- [x] **Step 7: 跑测试确认通过**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/shell/
cd apps/desktop && npm run test && npm run typecheck
```
Expected: 全绿。`ContextRail` 的既有测试若断言了状态栏文案，改为在 `App` 层断言。

- [x] **Step 8: 提交**

```bash
git add renderer/App.tsx renderer/components/context renderer/__tests__/shell
git commit -m "fix(desktop-ui): 状态栏移出 ContextRail，升为 shell 级全宽贴底栏

状态栏原本长在右栏内部。右栏在 T6 会变成可折叠面板，届时六项常显
会随折叠一起消失 —— 违反 INV-36/INV-38 与 M2 判据 10。

改由 App 直接渲染，与 activeView 无关：证据页、设置页也常显。加
landmark role=contentinfo + aria-label 便于断言，测试锁死它不再是
.ctxrail 的子节点。"
```

---

### Task 4: 左栏升为 shell 级，底部加视图导航

**Files:**
- Create: `renderer/components/shell/Sidebar.tsx`, `renderer/components/shell/Sidebar.css`
- Create: `renderer/components/shell/ViewNav.tsx`
- Modify: `renderer/components/session/SessionRail.tsx`（去掉 `Panel` 外壳与标题）
- Modify: `renderer/views/WorkbenchView.tsx`（移除 `<SessionRail />`）
- Modify: `renderer/App.tsx`, `renderer/components/shell/AppShell.css`
- Modify: `renderer/components/workbench/WorkbenchLayout.css`（grid 从三列改两列）
- Test: `renderer/__tests__/session/sessionrail.test.tsx`（改渲染入口）

**Interfaces:**
- Consumes: T2 的 `ListRow variant="nav"`
- Produces: `<Sidebar activeView onNavigate />`，T6 给它加 `collapsed` prop

- [x] **Step 1: 写 ViewNav 的失败测试**

Create `renderer/__tests__/shell/viewnav.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ViewNav } from "../../components/shell/ViewNav";

describe("ViewNav", () => {
  it("三个入口都在，当前项标 aria-current", () => {
    render(<ViewNav activeView="evidence" onNavigate={() => {}} />);
    expect(screen.getByRole("button", { name: "调查" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "设置" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "证据" }))
      .toHaveAttribute("aria-current", "true");
  });

  it("点击回调带视图 id", () => {
    const onNavigate = vi.fn();
    render(<ViewNav activeView="workbench" onNavigate={onNavigate} />);
    screen.getByRole("button", { name: "设置" }).click();
    expect(onNavigate).toHaveBeenCalledWith("settings");
  });
});
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/shell/viewnav.test.tsx
```
Expected: FAIL —— 模块不存在。

- [x] **Step 3: 写 ViewNav**

Create `renderer/components/shell/ViewNav.tsx`:

```tsx
import type { ActiveView } from "../../lib/types";
import { ListRow } from "../../ui";

const VIEWS: Array<{ id: ActiveView; label: string }> = [
  { id: "workbench", label: "调查" },
  { id: "evidence", label: "证据" },
  { id: "settings", label: "设置" },
];

export type ViewNavProps = {
  activeView: ActiveView;
  onNavigate: (v: ActiveView) => void;
};

export function ViewNav({ activeView, onNavigate }: ViewNavProps) {
  return (
    <nav className="sidebar-nav" aria-label="主导航">
      {VIEWS.map((v) => (
        <ListRow
          key={v.id}
          variant="nav"
          active={activeView === v.id}
          title={v.label}
          onClick={() => onNavigate(v.id)}
        />
      ))}
    </nav>
  );
}
```

- [x] **Step 4: 跑测试确认通过**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/shell/viewnav.test.tsx
```
Expected: PASS

- [x] **Step 5: 写 Sidebar 容器**

Create `renderer/components/shell/Sidebar.tsx`:

```tsx
import type { ActiveView } from "../../lib/types";
import { useSessions } from "../../state";
import { Button } from "../../ui";
import { SessionRail } from "../session/SessionRail";
import { ViewNav } from "./ViewNav";
import "./Sidebar.css";

export type SidebarProps = {
  activeView: ActiveView;
  onNavigate: (v: ActiveView) => void;
};

export function Sidebar({ activeView, onNavigate }: SidebarProps) {
  const { create } = useSessions();

  return (
    <aside className="sidebar" aria-label="会话与导航">
      <div className="sidebar-top">
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            create();
            onNavigate("workbench");
          }}
        >
          ＋ 新建
        </Button>
      </div>
      <div className="sidebar-sessions">
        <SessionRail />
      </div>
      <div className="sidebar-foot">
        <ViewNav activeView={activeView} onNavigate={onNavigate} />
      </div>
    </aside>
  );
}
```

Create `renderer/components/shell/Sidebar.css`:

```css
.sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  width: 260px;
  background: var(--layer-0);
  padding: var(--sp-3);
  gap: var(--sp-3);
}
.sidebar-top { flex: 0 0 auto; }
.sidebar-sessions { flex: 1; min-height: 0; overflow-y: auto; }
.sidebar-foot {
  flex: 0 0 auto;
  padding-top: var(--sp-3);
  border-top: 1px solid var(--border-0);
}
.sidebar-nav { display: flex; flex-direction: column; gap: var(--sp-1); }
```

- [x] **Step 6: SessionRail 去掉 Panel 外壳**

`renderer/components/session/SessionRail.tsx`：`<Panel className="wb-rail sessionrail" tone="sunken" title="调查" actions={…}>` 换成 `<div className="sessionrail">`（闭合同改），删掉 `Panel` 与 `Button` 的 `+ 新建` —— 新建按钮已由 `Sidebar` 顶部承担，**留在这里会变成两个主操作**。`Panel` import 若无其他用处一并删除。

- [x] **Step 7: 从 WorkbenchView 摘掉，App 挂上**

`renderer/views/WorkbenchView.tsx`：删掉 `<SessionRail />` 与其 import。

`renderer/App.tsx`：把三个 `activeView` 分支包进新的两列布局：

```tsx
        <div className="app-body">
          <Sidebar activeView={activeView} onNavigate={setActiveView} />
          <div className="app-main">
            {/* 原三个 activeView 分支原样搬进来 */}
          </div>
        </div>
        <StatusBar onOpenSettings={openSettings} />
```

`renderer/components/shell/AppShell.css` 追加：

```css
.app-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.app-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--layer-1);
}
```

`renderer/components/workbench/WorkbenchLayout.css`：`.wb` 的 grid 从三列改两列：

```css
.wb {
  grid-template-columns: minmax(0, 1fr) 300px;
}
@media (max-width: 1180px) {
  .wb { grid-template-columns: minmax(0, 1fr) 260px; }
}
```

- [x] **Step 8: 修既有测试的渲染入口**

`renderer/__tests__/session/sessionrail.test.tsx` 里若直接 `render(<SessionRail />)` 并断言「+ 新建」按钮，把该断言迁到新建的 `renderer/__tests__/shell/sidebar.test.tsx`，`SessionRail` 自身的测试只留列表 / 删除 / 撤销三项。

- [x] **Step 9: 跑全套并提交**

```bash
cd apps/desktop && npm run test && npm run typecheck
git add renderer/components renderer/views/WorkbenchView.tsx renderer/App.tsx \
        renderer/__tests__
git commit -m "feat(desktop-ui): 左栏升为 shell 级，底部接管视图导航

Claude 形态里导航在左栏、没有顶部 tab 栏。SessionRail 从 WorkbenchView
移出、去掉 Panel 外壳，与新的 ViewNav 一起装进 Sidebar，由 App 渲染 ——
证据页与设置页也共享同一左栏。

＋新建 收归 Sidebar 顶部：它与 composer 的运行是全局仅有的两个 accent
实底按钮，留在 SessionRail 里会变成第三个。"
```

---

### Task 5: 顶栏压到 40px，UiPrefs 升为 context

**Files:**
- Modify: `renderer/components/shell/AppChrome.tsx`, `renderer/components/shell/AppChrome.css`
- Create: `renderer/state/UiPrefsProvider.tsx`
- Modify: `renderer/App.tsx`
- Test: `renderer/__tests__/shell/appchrome.test.tsx`（新建）

**Interfaces:**
- Consumes: T2 的 `Button size="icon"`
- Produces: `useUiPrefsCtx()` 返回 `{ theme, setTheme, resolved, cycleTheme, fontSize, setFontSize }`，T6 在同一 provider 上追加折叠字段；T9 的 `AppearanceSection` 直接消费，不再走 props

- [x] **Step 1: 写失败的测试**

Create `renderer/__tests__/shell/appchrome.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../../App";

describe("AppChrome", () => {
  it("顶栏不再含视图导航（已下放左栏）", () => {
    render(<App />);
    const header = screen.getByRole("banner");
    expect(header.querySelector("nav")).toBeNull();
  });

  it("顶栏显示当前调查标题", () => {
    render(<App />);
    expect(screen.getByRole("banner").textContent).toContain("新调查");
  });

  it("侧栏开关是 icon 按钮", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "切换侧栏" }).className)
      .toContain("ui-btn--icon");
  });
});
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/shell/appchrome.test.tsx
```
Expected: FAIL —— 顶栏里仍有 `<nav>`，也没有「切换侧栏」按钮。

- [x] **Step 3: 写 UiPrefsProvider**

Create `renderer/state/UiPrefsProvider.tsx`:

```tsx
import { createContext, useContext, type ReactNode } from "react";
import { useUiPrefs } from "../hooks/useUiPrefs";

type UiPrefsValue = ReturnType<typeof useUiPrefs>;

const Ctx = createContext<UiPrefsValue | null>(null);

export function UiPrefsProvider({ children }: { children: ReactNode }) {
  const value = useUiPrefs();
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUiPrefsCtx(): UiPrefsValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useUiPrefsCtx 必须在 UiPrefsProvider 内使用");
  return v;
}
```

`renderer/state/index.ts` 追加导出 `UiPrefsProvider` 与 `useUiPrefsCtx`。

- [x] **Step 4: 重写 AppChrome**

`renderer/components/shell/AppChrome.tsx` 全量：

```tsx
import { Button } from "../../ui";
import { useUiPrefsCtx } from "../../state";
import "./AppChrome.css";

export type AppChromeProps = {
  title: string;
  devTitle: string;
  onToggleSidebar: () => void;
  onToggleRail: () => void;
};

export function AppChrome({
  title,
  devTitle,
  onToggleSidebar,
  onToggleRail,
}: AppChromeProps) {
  const { cycleTheme, resolved } = useUiPrefsCtx();

  return (
    <header className="chrome" role="banner">
      <Button size="icon" variant="ghost" aria-label="切换侧栏" onClick={onToggleSidebar}>
        ☰
      </Button>
      <h1 className="chrome-title">{title}</h1>
      <div className="chrome-right">
        <span className="chrome-dev" title={devTitle}>DEV</span>
        <Button size="icon" variant="ghost" aria-label="切换主题" onClick={cycleTheme}>
          {resolved === "dark" ? "◐" : "◑"}
        </Button>
        <Button size="icon" variant="ghost" aria-label="切换侧板" onClick={onToggleRail}>
          ⌄
        </Button>
      </div>
    </header>
  );
}
```

`AppChrome.css`：`.chrome` 高度 `40px`、`padding-left: var(--chrome-pad-left)`、`-webkit-app-region: drag`，`.chrome > *` 设 `-webkit-app-region: no-drag`；`.chrome-title` 用 `var(--text-sm)` + `var(--text-muted)`，居中靠 `margin: 0 auto`。删除 `.chrome2-nav` / `.chrome2-tab` 相关规则。

- [x] **Step 5: App 接线**

`renderer/App.tsx`：
- `App()` 里在 `<TooltipProvider>` 与 `<RuntimeProvider>` 之间包一层 `<UiPrefsProvider>`
- `AppInner` 里 `const { theme, setTheme, resolved, fontSize, setFontSize } = useUiPrefsCtx();` 取代 `useUiPrefs()`
- `<AppChrome>` 改传 `title` / `devTitle` / `onToggleSidebar` / `onToggleRail`（后两个先传空函数，T6 接真实状态）
- `title` 取自当前会话：与 `WorkbenchView` 同一套逻辑，抽成 `AppInner` 里的一行 `const title = sessions.find(s => s.session_id === sessionId)?.title || run.lastSubmitted || "新调查";`，并把 `InvestigationHeader` 从 `WorkbenchView` 删除（标题已上移顶栏，留着是重复）

- [x] **Step 6: 跑全套并提交**

```bash
cd apps/desktop && npm run test && npm run typecheck
git add renderer/components/shell renderer/state renderer/App.tsx \
        renderer/views/WorkbenchView.tsx renderer/__tests__/shell
git commit -m "feat(desktop-ui): 顶栏压到 40px，UiPrefs 升为 context

nav 已在 T4 下放左栏，顶栏只剩拖拽区 + 标题 + 三个 icon 开关。调查
标题从中间栏的 InvestigationHeader 上移顶栏，原组件删除（重复）。

useUiPrefs 升 context 不是顺带重构：nav 下放后主题与字号要穿过三层
新壳手传，收进 provider 才不会把 props 又传回去。"
```

---

### Task 6: 折叠、响应式与持久化

**Files:**
- Modify: `renderer/hooks/useUiPrefs.ts`（新增两个折叠字段）
- Modify: `renderer/App.tsx`, `renderer/components/shell/Sidebar.tsx`, `renderer/views/WorkbenchView.tsx`
- Modify: `renderer/hooks/useHotkeys.ts`（`⌘\`）
- Test: `renderer/__tests__/shell/responsive.test.tsx`（新建）、`statusbar.always.test.tsx`（扩四组合）

**Interfaces:**
- Consumes: T5 的 `useUiPrefsCtx()`
- Produces: `sidebarCollapsed` / `railCollapsed` / `setSidebarCollapsed` / `setRailCollapsed`

- [x] **Step 1: 写失败的测试**

Create `renderer/__tests__/shell/responsive.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../../App";

/** 覆盖 setup.ts 里恒 false 的 matchMedia 桩 */
function setViewport(width: number) {
  window.matchMedia = ((query: string) => {
    const m = /max-width:\s*(\d+)px/.exec(query);
    return {
      matches: m ? width <= Number(m[1]) : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    };
  }) as unknown as typeof window.matchMedia;
}

describe("响应式与折叠持久化", () => {
  beforeEach(() => localStorage.clear());

  it("窄于 1180px 自动收右侧板", () => {
    setViewport(1100);
    render(<App />);
    expect(screen.queryByRole("complementary", { name: "本次调查" })).toBeNull();
  });

  it("窄于 900px 自动收左栏", () => {
    setViewport(860);
    render(<App />);
    expect(screen.queryByRole("complementary", { name: "会话与导航" })).toBeNull();
  });

  it("宽屏两者都在", () => {
    setViewport(1440);
    render(<App />);
    expect(screen.getByRole("complementary", { name: "本次调查" })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "会话与导航" })).toBeTruthy();
  });

  it("手动折叠写入 localStorage 并在重挂载后恢复", () => {
    setViewport(1440);
    const first = render(<App />);
    screen.getByRole("button", { name: "切换侧栏" }).click();
    expect(localStorage.getItem("cg.sidebar_collapsed")).toBe("1");
    first.unmount();
    render(<App />);
    expect(screen.queryByRole("complementary", { name: "会话与导航" })).toBeNull();
  });
});
```

追加到 `renderer/__tests__/shell/statusbar.always.test.tsx`（复用该文件已有的 `expectSixVisible`）：

```tsx
  it.each([
    ["都展开", false, false],
    ["只收左栏", true, false],
    ["只收侧板", false, true],
    ["都收起", true, true],
  ])("%s 时六项仍常显", (_n, sidebar, rail) => {
    localStorage.setItem("cg.sidebar_collapsed", sidebar ? "1" : "0");
    localStorage.setItem("cg.rail_collapsed", rail ? "1" : "0");
    render(<App />);
    expectSixVisible();
  });
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/shell/
```
Expected: FAIL —— 折叠能力不存在，两个 rail 也还没有 `role="complementary"` + `aria-label`。

- [x] **Step 3: useUiPrefs 加折叠状态**

`renderer/hooks/useUiPrefs.ts` 内新增（与 `FONT_KEY` 同样的 localStorage 模式）：

```ts
const SIDEBAR_KEY = "cg.sidebar_collapsed";
const RAIL_KEY = "cg.rail_collapsed";

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  return fallback;
}

function mediaBelow(px: number): boolean {
  return window.matchMedia?.(`(max-width: ${px}px)`).matches ?? false;
}
```

在 `useUiPrefs()` 里：

```ts
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(() =>
    readFlag(SIDEBAR_KEY, mediaBelow(900))
  );
  const [railCollapsed, setRailCollapsedState] = useState(() =>
    readFlag(RAIL_KEY, mediaBelow(1180))
  );

  const setSidebarCollapsed = useCallback((v: boolean) => {
    setSidebarCollapsedState(v);
    try {
      localStorage.setItem(SIDEBAR_KEY, v ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);
  // setRailCollapsed 同型，键换 RAIL_KEY
```

并加进返回对象。

> 断点只在初始化时读一次（`useState` 的惰性初值）。**不监听 resize** —— 用户手动选择必须优先于窗口尺寸，加监听会在拖窗口时覆盖用户意图。

- [x] **Step 4: 两个 rail 加 landmark**

`renderer/components/shell/Sidebar.tsx` 的 `<aside className="sidebar" aria-label="会话与导航">` 已带 label，浏览器对 `<aside>` 自动给 `complementary` role —— 无需改动。

`renderer/components/context/ContextRail.tsx`：最外层 `<div className="wb-rail ctxrail">` 改为

```tsx
    <aside className="wb-rail ctxrail" aria-label="本次调查">
```

（闭合标签同改；内部原有的 `<h2 className="ctxrail-title">本次调查</h2>` 保留，视觉标题与 aria-label 一致。）

- [x] **Step 5: App 与 WorkbenchView 接线**

`renderer/App.tsx`：从 `useUiPrefsCtx()` 取四个新字段，`<AppChrome onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)} onToggleRail={() => setRailCollapsed(!railCollapsed)} />`，并 `{!sidebarCollapsed && <Sidebar … />}`。

`renderer/views/WorkbenchView.tsx`：`{!railCollapsed && <ContextRail … />}`，同时 `.wb` 的列数随之变化——用类名切换而非改 grid 定义：

```tsx
  <div className={`wb${railCollapsed ? " wb--norail" : ""}`}>
```

`WorkbenchLayout.css` 追加 `.wb--norail { grid-template-columns: minmax(0, 1fr); }`。

`renderer/hooks/useHotkeys.ts`：新增 `⌘\` → `onToggleSidebar`，与既有快捷键同一套注册方式。

- [x] **Step 6: 跑测试确认通过**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/shell/
```
Expected: PASS —— 含状态栏四组合。

- [x] **Step 7: 跑全套并提交**

```bash
cd apps/desktop && npm run test && npm run typecheck
git add renderer/hooks renderer/App.tsx renderer/components renderer/views \
        renderer/__tests__/shell
git commit -m "feat(desktop-ui): 左栏/侧板可折叠，断点自动收起并记住选择

<1180 收侧板、<900 收左栏，仅初始化时判定一次：不监听 resize，
否则拖窗口会覆盖用户手动选择。

状态栏测试补齐四种折叠组合 —— 这是把状态栏移出右栏（T3）真正要
挡住的回归：任何一种组合下六项都必须在。"
```

---

### Task 7: 主体限宽、composer 浮起、Prose

**Files:**
- Create: `renderer/ui/Prose.tsx`, `renderer/ui/Prose.css`
- Modify: `renderer/components/Markdown.tsx`
- Modify: `renderer/components/investigation/Composer.css`
- Modify: `renderer/components/workbench/WorkbenchLayout.css`
- Test: `renderer/__tests__/ui/Prose.test.tsx`（新建）

**Interfaces:**
- Consumes: T1 的 `--measure` / `--radius-xl` / `--leading-relaxed`
- Produces: `<Prose>{children}</Prose>`，T10 的证据详情复用

- [x] **Step 1: 写失败的测试**

Create `renderer/__tests__/ui/Prose.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Prose } from "../../ui";

describe("Prose", () => {
  it("包一层 ui-prose 容器", () => {
    render(<Prose><p>报告正文</p></Prose>);
    expect(screen.getByText("报告正文").closest(".ui-prose")).toBeTruthy();
  });
});
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/ui/Prose.test.tsx
```
Expected: FAIL —— 模块不存在。

- [x] **Step 3: 写 Prose**

Create `renderer/ui/Prose.tsx`:

```tsx
import type { ReactNode } from "react";
import "./Prose.css";

export function Prose({ children }: { children: ReactNode }) {
  return <div className="ui-prose">{children}</div>;
}
```

Create `renderer/ui/Prose.css`：`.ui-prose` 设 `max-width: var(--measure); line-height: var(--leading-relaxed); color: var(--text)`；`.ui-prose h1,h2,h3` 用 `font-family: var(--font-serif); font-weight: 600`；`.ui-prose code` 用 `background: var(--border-0); border-radius: var(--radius-sm); font-family: var(--font-mono)`；`.ui-prose table` 边框走 `var(--border-0)`；`.ui-prose pre` 加 `overflow-x: auto`。

`renderer/ui/index.ts` 追加 `export { Prose } from "./Prose";`。

`renderer/components/Markdown.tsx`：把渲染结果包进 `<Prose>`。

- [x] **Step 4: 跑测试确认通过 + 主体限宽与 composer**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/ui/Prose.test.tsx
```
Expected: PASS

随后改 CSS：

`WorkbenchLayout.css` 的 `.wb-timeline` 内容居中限宽——

```css
.wb-timeline > * {
  max-width: var(--measure);
  margin: 0 auto;
  padding: var(--sp-6) var(--sp-4);
}
```

`Composer.css`：外层加 `max-width: var(--measure); margin: 0 auto var(--sp-6);`，输入框 `background: var(--layer-2); border-radius: var(--radius-xl); box-shadow: var(--shadow-2); border: 1px solid var(--border-0);`，内边距用 `var(--sp-4)`。

- [x] **Step 5: 跑全套并提交**

```bash
cd apps/desktop && npm run test && npm run typecheck
git add renderer/ui renderer/components renderer/__tests__/ui
git commit -m "feat(desktop-ui): 主体限宽 46rem，composer 浮起，新增 Prose

留白是 Claude 观感的主要来源，不是颜色：主体两侧留白直接吃掉上一版
诊断里那片死区，窗口再宽内容也不拉伸。

Prose 收拢原本散在 styles.css 里的 Markdown 排版，标题走 --font-serif，
正文仍是无衬线 —— 衬线只用于标题（spec §1.4）。"
```

- [ ] **Step 6: ⏸ 人工检查点（spec §7 的「停下来看比例」）** —— *未留证据。实现已合并，但两档窗口的目视核对没有截图或记录，与判据 7 一并挂着。*

```bash
cd apps/desktop && npm run dev
```

看两件事，**只看比例不看细节**：主体限宽后左右留白是否舒服；字阶 15px + 行高 1.6 在 1440×900 下是否偏大。比例不对现在掉头，只需回滚 T7 与 T1 的字阶段落；等 T8–T10 铺完再改要动三个视图。

---

### Task 8: Settings 原样拆七文件（行为不变）

**Files:**
- Create: `renderer/views/settings/SettingsShell.tsx`, `HubSection.tsx`, `LlmSection.tsx`, `McpSection.tsx`, `SkillsSection.tsx`, `AppearanceSection.tsx`, `DataSection.tsx`, `AboutSection.tsx`
- Modify: `renderer/views/SettingsView.tsx`（缩成转发壳）

**Interfaces:**
- Consumes: 现有 `SettingsViewProps`（本任务**不改签名**）
- Produces: 七个 `*Section` 组件，各自 props 与其原分区实际用到的字段一致

- [x] **Step 1: 记录基线**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts 2>&1 | tail -5
wc -l renderer/views/SettingsView.tsx
```
把测试数与行数记进提交信息。**本任务的验收是「行为零变化」**，与 M0a-1 同一个判据。

- [x] **Step 2: 逐个分区搬运**

按 `SettingsView.tsx` 现有的 `{section === "llm" && (…)}` 等七处边界（`:760` hub、`:811` llm、`:967` mcp、`:1151` skills、`:1372` appearance、`:1410` data、`:1437` about），**原样**剪切进各自文件，只补 import 与 props 类型。**这一步不许改任何 JSX 结构、类名或文案。**

`SettingsShell.tsx` 承接原文件 `:733` 起的分区切换逻辑与 `hubStatus`，分区导航先保持现有排布（改成左侧竖排是 T9 的事）。

- [x] **Step 3: SettingsView 缩成转发壳**

```tsx
export function SettingsView(props: SettingsViewProps) {
  return <SettingsShell {...props} />;
}
```

- [x] **Step 4: 验证行为零变化**

```bash
cd apps/desktop && npm run test && npm run typecheck
wc -l renderer/views/SettingsView.tsx renderer/views/settings/*.tsx
```
Expected: 测试数与 Step 1 一致且全绿；每个新文件 ≤300 行。

- [x] **Step 5: 提交**

```bash
git add renderer/views
git commit -m "refactor(desktop-ui): Settings 原样拆七文件，行为零变化

1454 行拆成壳 + 七个分区，JSX/类名/文案一字未改，与 M0a-1 同一个
判据：测试数不变且全绿。美化在下一个提交 —— 拆错时回滚成本低。"
```

---

### Task 9: Settings 套新 primitives，props 10 → 2

**Files:**
- Modify: `renderer/views/settings/*.tsx`
- Modify: `renderer/App.tsx`

**Interfaces:**
- Consumes: T2 primitives、T5 的 `useUiPrefsCtx()`
- Produces: `SettingsViewProps = { focusSection?: SettingsSection; onProviderSaved: (mode: string) => void }`

- [x] **Step 1: 分区导航改左侧竖排**

`SettingsShell.tsx` 的分区切换改用 `ListRow variant="nav"`（与 T4 的 `ViewNav` 同一形态），布局为左 200px 导航 + 右内容，内容区 `max-width: var(--measure)`。

- [x] **Step 2: 表单换 Field**

七个分区里的裸 `<label>` + `<input>` 组合换成 `Field`；按钮换 `Button`（**只有保存类主操作用 `variant="primary"`，其余 ghost/secondary**）；折叠块换 `Disclosure`；卡片换 `Card`。

- [x] **Step 3: 收 props**

`AppearanceSection` 改为直接 `useUiPrefsCtx()` 取 `theme` / `fontSize` / `setTheme` / `setFontSize`；`DataSection` 与 `AboutSection` 从 `useEnvironment()` 取 `dataRoot` / `providerMode`。随后把 `SettingsViewProps` 收成两个字段，`App.tsx` 对应删掉 8 个传参。

- [x] **Step 4: 跑全套**

```bash
cd apps/desktop && npm run test && npm run typecheck
```
Expected: 全绿。`App.tsx` 里 `theme` / `resolved` / `fontSize` 若已无其他消费方，一并从解构里删除，否则 `tsc` 会报未使用变量。

- [x] **Step 5: 提交**

```bash
git add renderer/views/settings renderer/App.tsx
git commit -m "feat(desktop-ui): Settings 套新 primitives，props 10→2

分区导航改左侧竖排（与左栏 ViewNav 同一形态），表单统一走 Field。
主题与字号改为直接消费 UiPrefsProvider，App 不再手传八个参数。"
```

---

### Task 10: Evidence 迁移

**Files:**
- Modify: `renderer/views/EvidenceView.tsx`
- Modify: `renderer/styles/views.css`（删本视图的遗留规则）

**Interfaces:**
- Consumes: T2 primitives、T7 的 `Prose`
- Produces: 无

- [x] **Step 1: 列表换 ListRow，详情换 Panel**

证据列表每行用 `ListRow`（`title` 为文件名、`meta` 为 `Timestamp` + 短哈希）；选中项详情用 `Panel`；整体外层 `max-width: var(--measure); margin: 0 auto`。哈希与路径保持 `var(--font-mono)`。

- [ ] **Step 2: 保留高亮跳转** —— *代码保留了（`EvidenceView.tsx:64-70`），但既无自动化测试也无手工验证记录。*

`highlightId` 的滚动定位与高亮行为**不许丢** —— 它是 Workbench 右栏「证据」跳转的落点。改完手工验证：Workbench 右栏点任一证据 id → 证据页对应行高亮。

- [x] **Step 3: 跑全套并提交**

```bash
cd apps/desktop && npm run test && npm run typecheck
git add renderer/views/EvidenceView.tsx renderer/styles/views.css
git commit -m "feat(desktop-ui): Evidence 套新 primitives 并限宽居中

功能不动，只换排布。highlightId 的跳转高亮保留 —— 那是右栏证据
链接的落点。"
```

---

### Task 11: 删兼容层、清 CSS、核对出口判据

**Files:**
- Modify: `renderer/styles/tokens.css`（删末尾兼容块）
- Modify: `renderer/styles.css`, `renderer/styles/views.css`
- Modify: `renderer/__tests__/styles/legacy.test.ts`

**Interfaces:**
- Consumes: T1–T10 全部
- Produces: 无

- [x] **Step 1: 写失败的测试**

`renderer/__tests__/styles/legacy.test.ts` 追加：

```ts
/** T11 已删除的兼容别名，任何文件不得再引用（spec §1.6 / 判据 1） */
const RETIRED_ALIASES = [
  "--bg",
  "--bg-elevated",
  "--bg-deep",
  "--surface",
  "--surface-solid",
  "--surface-hover",
  "--border:",
  "--border-subtle",
  "--border-strong",
  "--panel",
  "--muted",
  "--shadow-panel",
  "--shadow-soft",
];

describe("token 兼容别名已删除", () => {
  const all = [
    read("styles.css"),
    read("styles/views.css"),
    read("styles/tokens.css"),
    read("styles/base.css"),
  ].join("\n");

  it.each(RETIRED_ALIASES)("%s 不再出现", (alias) => {
    expect(all).not.toContain(alias);
  });
});
```

> `--border:` 带冒号是为了不误伤 `--border-0/1/2`。

- [x] **Step 2: 跑测试确认失败**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/styles/legacy.test.ts
```
Expected: FAIL —— 兼容块还在。

- [x] **Step 3: 删兼容块，改所有引用点**

删掉 `tokens.css` 末尾整个兼容层。然后：

```bash
cd apps/desktop && grep -rn "var(--bg\|var(--surface\|var(--panel)\|var(--muted)\|var(--border)\|var(--shadow-panel\|var(--shadow-soft" renderer/
```

逐个替换为对应新 token：`--bg`/`--bg-deep` → `--layer-0`，`--bg-elevated`/`--panel` → `--layer-1`，`--surface`/`--surface-solid` → `--layer-2`，`--surface-hover` → `--layer-3`，`--border` → `--border-1`，`--border-subtle` → `--border-0`，`--border-strong` → `--border-2`，`--muted` → `--text-muted`，`--shadow-panel` → `--shadow-3`，`--shadow-soft` → `none`。

- [x] **Step 4: 跑测试确认通过**

```bash
cd apps/desktop && npx vitest run --config vitest.config.ts renderer/__tests__/styles/
```
Expected: PASS

- [ ] **Step 5: 核对全部七条出口判据** —— *判据 1–6 已核（见下方复核记录），**判据 7 未留证据**，故整步不勾。*

```bash
cd apps/desktop && npm run test && npm run typecheck
wc -l renderer/styles.css renderer/styles/views.css   # 判据 6：合计 ≤1000（起点 1844）
cd ../.. && PYTHONPATH="packages:$(pwd)" .venv/bin/python -m pytest -q tests/test_desktop_*.py
```

判据 7 需人工：`npm run dev`，在 1440×900 与 1024×768 两档各过一遍三个视图。

再核对 spec §1.3 的两条形态规则（grep 即可）：

```bash
# 全局只应有两个 accent 实底按钮：Sidebar 的＋新建、Composer 的运行
grep -rn 'variant="primary"' renderer/ | grep -v __tests__
# StatusDot 不得引入底色（状态色只做点 + 文字）
grep -n "background" renderer/ui/StatusDot.css
```

判据 6 若未达标，**不许为凑数硬删** —— 在提交信息里交代剩余规则归属哪个组件、为什么没迁。

- [x] **Step 6: 提交**

```bash
git add renderer
git commit -m "chore(desktop-ui): 删 token 兼容层，清遗留样式

三个视图迁完，tokens.css 末尾那组旧别名（上一轮为 Settings/Evidence
留的）随之删除，legacy.test.ts 加断言挡住回流。

出口判据逐条核对：1 兼容别名已删（测试）· 2 六项常显四组合（测试）
· 3 降级显著告警（测试）· 4 对比度（测试）· 5 全套 + sidecar 138
未改一字 · 6 CSS 行数 · 7 两档人工。"
```

---

## 附：降级告警测试（判据 3）

判据 3 的测试在 T3 建立 landmark 后即可写，建议随 T6 一起提交（那时折叠组合也已就位）。

Create `renderer/__tests__/shell/degradation.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../App";

/** 桩法与 __tests__/state/useEnvironment.provider.test.tsx 同款 */
function stubSandboxNone() {
  window.cyberguard = {
    ping: vi.fn().mockResolvedValue({ sandbox: { sandbox_impl: "none" } }),
    providerGet: vi.fn().mockResolvedValue({ mode: "mock" }),
    capabilities: vi.fn().mockResolvedValue({}),
  } as unknown as typeof window.cyberguard;
}

/**
 * INV-38：安全降级必须显式标注，不得伪装。
 * sandbox_impl=none 时状态栏须**显著**告警 —— 只挂 tooltip 不算。
 */
describe("降级显著告警", () => {
  afterEach(() => {
    delete (window as { cyberguard?: unknown }).cyberguard;
  });

  it("sandbox_impl=none 时状态栏整条进入 danger 态", async () => {
    stubSandboxNone();
    render(<App />);
    await waitFor(() => {
      const bar = screen.getByRole("contentinfo", { name: "运行态" });
      expect(bar.className).toContain("statusbar--danger");
    });
    expect(
      screen.getByRole("contentinfo", { name: "运行态" }).textContent
    ).toContain("沙箱");
  });

  it("用户收起降级浮出条后，状态栏仍保持降级态", async () => {
    stubSandboxNone();
    render(<App />);
    await waitFor(() => screen.getByRole("alert"));
    // 浮出条可收起；状态栏不可 —— 可收起的提示条不是安全边界（INV-38）
    screen.getAllByRole("button", { name: "收起" })[0].click();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("contentinfo", { name: "运行态" }).className
    ).toContain("statusbar--danger");
  });
});
```

对应实现：`StatusBar.tsx` 从 `useEnvironment()` 取已有的 `securityDegradations`，计算

```tsx
const degraded = env.securityDegradations.length > 0;
```

`<footer className={`statusbar${degraded ? " statusbar--danger" : ""}`} …>`；CSS `.statusbar--danger { background: var(--danger-muted); color: var(--danger); }` —— 这是 spec §1.3 允许的两处大面积染色例外之一。

> **不要发明 `env.auditBacklog`**：渲染层没有审计积压的数据源（见 spec §8.1 的缺口登记）。降级态一律由既有的 `securityDegradations` 派生，它已覆盖离线 / 沙箱不可用 / FileVault / TCC 四类。

---

## 复核记录（2026-08-18，合并后）

分支已合并进 `main`（`b43f16d`）。以下命令在复核当天重跑，结果如下：

| 项 | 命令 / 依据 | 结果 |
|---|---|---|
| 渲染层测试 | `npm run test` | 27 文件 / 204 测试通过 |
| 类型 | `npm run typecheck` | exit 0 |
| sidecar 闸门 | `pytest -q tests/test_desktop_*.py` | 138 passed，**未改一字** |
| 构建 | `npm run build:renderer` | 成功 |
| 判据 1 | 兼容别名 grep + `legacy.test.ts` | 零命中 / 30 断言 |
| 判据 2 | `statusbar.always.test.tsx` | 3 视图 + 4 折叠组合，**断言的是常显五项** |
| 判据 3 | `degradation.test.tsx` | 2 测试 |
| 判据 4 | `contrast.test.ts` | 两套主题 × 20 断言 |
| 判据 5 | 上列四行 | 全绿 |
| 判据 6 | `wc -l` | `styles.css 202 + views.css 276 = 478` ≤ 1000（起点 1844） |
| 判据 7 | 1440×900 / 1024×768 目视 | **未留证据** —— 仓库内无当日截图，提交信息只写了「两档人工（控制器）」 |

复核中修正的三处措辞与取值偏差：

1. **「六项常显」改为「常显五项 + 按需暂停项」。** `paused` 为假时第六项不渲染（改造前即如此，非本轮引入）。测试断言的一直是五项，措辞比断言强。同步改了 `StatusBar.tsx`、`statusbar.always.test.tsx`、spec §2/§4.2/§5/§8.1、`11-OPEN-QUESTIONS.md` §J。
2. **`--measure` 实际落为 `736px` 而非 spec 原写的 `46rem`。** 这是刻意的（根字号随 `data-font` 变，rem 限宽会让列宽跟着字号伸缩），已把理由写进 spec §1 与 `tokens.css` 注释。
3. **accent 实底按钮全局 5 个而非本计划 T11 Step 5 预期的 2 个。** 多出的三个是 Settings 三个分区各自的保存 / 批准键，偏离已在提交 `4da788b` 的信息里交代，判定为可接受。

未了：判据 7 与 T7 Step 6 的两档目视，以及 T10 Step 2 的 `highlightId` 跳转手工验证。
