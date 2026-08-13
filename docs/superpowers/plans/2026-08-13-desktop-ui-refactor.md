# 桌面端 UI 重构实施计划（结构 + 视觉）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CyberGuard 桌面端调查页（Workbench）从"功能可用但观感毛胚"重做成一个有设计系统、有组件边界、有交互反馈的调查工作台。

**Architecture:** 路线 B（主屏先行，反向萃取）。先收紧 token 层并建 10 个 primitives，再把 529 行 / 33 个 `useState` 的 `useDesktopRuntime` 拆成六个域（其中五个本轮落地），用纯 reducer + Context 承载，最后重做 Workbench 三栏。Settings / Evidence 本轮只被动继承新 token，不重做。

**Tech Stack:** React 19 + Vite 6 + TypeScript 5.7 + 手写 CSS（CSS 自定义属性 token）+ Radix 无头原语 + vitest / React Testing Library / jsdom

**Spec:** `docs/superpowers/specs/2026-08-13-desktop-ui-refactor-design.md`

## Global Constraints

- 工作目录一律为 `apps/desktop/`；除 Task 11 触及 `SettingsView.tsx` 外，本轮不改 `renderer/views/SettingsView.tsx` 与 `renderer/views/EvidenceView.tsx` 的观感
- 不触碰 Python sidecar；`tests/test_desktop_*.py`（138 个）必须始终全绿
- 新依赖**仅限**这 5 个，不得追加：`@radix-ui/react-select`、`@radix-ui/react-tooltip`、`vitest`、`@testing-library/react`、`jsdom`
- 不引入 Tailwind、不引入完整 UI 组件库、不做快照测试、不做全局 toast、不做 ⌘K 命令面板
- 新代码**一行都不许**写进 `renderer/styles.css` 与 `renderer/styles/views.css`
- 层级硬规则：相邻嵌套必须差一级，同级不套同级
- 字重只用 400 / 500 / 600，**禁用 700**
- 所有进入动效与脉冲必须在 `prefers-reduced-motion: reduce` 下关闭
- 状态栏六项（连接态 / sandbox / tcc / 模型 / 档位 / 暂停态）**常显、不可折叠**（INV-36、M2 判据 10）
- 安全降级必须与普通运行错误在视觉上区分（INV-38）
- 每个 Task 结束时 `npm run typecheck` 与 `npm test` 必须全绿

---

### Task 1: 测试基建

**Files:**
- Modify: `apps/desktop/package.json`
- Create: `apps/desktop/vitest.config.ts`
- Create: `apps/desktop/renderer/__tests__/setup.ts`
- Test: `apps/desktop/renderer/__tests__/smoke.test.ts`

**Interfaces:**
- Consumes: 无
- Produces: `npm test`（单跑）与 `npm run test:watch`；后续所有 Task 的测试都放在 `renderer/__tests__/` 下

- [ ] **Step 1: 装依赖**

```bash
cd apps/desktop
npm i -D vitest@^2.1.8 @testing-library/react@^16.1.0 jsdom@^25.0.1
```

- [ ] **Step 2: 写 vitest 配置**

Create `apps/desktop/vitest.config.ts`：

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    root: path.resolve(__dirname),
    environment: "jsdom",
    include: ["renderer/__tests__/**/*.test.{ts,tsx}"],
    setupFiles: ["renderer/__tests__/setup.ts"],
    css: false,
  },
});
```

- [ ] **Step 3: 写 setup**

Create `apps/desktop/renderer/__tests__/setup.ts`：

```ts
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// jsdom 不实现 matchMedia，主题与 reduced-motion 代码会用到
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
```

- [ ] **Step 4: 写冒烟测试（先失败）**

Create `apps/desktop/renderer/__tests__/smoke.test.ts`：

```ts
import { describe, expect, it } from "vitest";

describe("test harness", () => {
  it("runs in jsdom", () => {
    expect(typeof window).toBe("object");
    expect(typeof document.createElement("div")).toBe("object");
  });
});
```

- [ ] **Step 5: 接 npm 脚本**

在 `apps/desktop/package.json` 的 `scripts` 中加入：

```json
"test": "vitest run --config vitest.config.ts",
"test:watch": "vitest --config vitest.config.ts"
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd apps/desktop && npm test`
Expected: PASS，1 passed

- [ ] **Step 7: 确认 typecheck 未被破坏**

Run: `cd apps/desktop && npm run typecheck`
Expected: 无输出、退出码 0

> `tsconfig.json` 的 `include` 已是 `renderer/**/*`，新测试文件自动纳入。若报 `Cannot find name 'describe'`，在 `tsconfig.json` 的 `compilerOptions` 加 `"types": ["vitest/globals"]` 并在 `vitest.config.ts` 的 `test` 中加 `globals: true`。本计划的测试均显式 `import { describe, it, expect } from "vitest"`，正常情况下不需要改。

- [ ] **Step 8: 提交**

```bash
git add apps/desktop/package.json apps/desktop/package-lock.json apps/desktop/vitest.config.ts apps/desktop/renderer/__tests__/
git commit -m "test(desktop): 接入 vitest + RTL + jsdom 测试基建"
```

---

### Task 2: Token 层收紧（字阶 / 间距阶 / 层级阶 / 色彩职责）

**Files:**
- Modify: `apps/desktop/renderer/styles/tokens.css`
- Test: `apps/desktop/renderer/__tests__/styles/tokens.test.ts`

**Interfaces:**
- Consumes: 无
- Produces: 后续所有组件使用的 CSS 自定义属性。**必须成对定义**（`:root`/`html[data-theme="dark"]` 与 `html[data-theme="light"]` 均有）的 token 清单见 Step 1 的 `REQUIRED_PAIRED`；只需定义一次（与主题无关）的见 `REQUIRED_ONCE`

- [ ] **Step 1: 写 token 完整性测试（先失败）**

Create `apps/desktop/renderer/__tests__/styles/tokens.test.ts`：

```ts
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- tokens`
Expected: FAIL，`--layer-0` / `--text-2xs` / `--sp-1` 等大量 token 未定义

- [ ] **Step 3: 改写 tokens.css**

替换 `apps/desktop/renderer/styles/tokens.css` 全文：

```css
/* CyberGuard desktop — 设计 token
 * 分三组：主题无关标量（字阶/间距阶/动效）、深色主题、浅色主题。
 * 层级硬规则：相邻嵌套必须差一级，同级不套同级。
 */

:root {
  /* 字阶 */
  --text-2xs: 11px;
  --text-xs: 12px;
  --text-sm: 13px;
  --text-base: 14px;
  --text-md: 16px;
  --text-lg: 20px;
  --text-xl: 26px;

  /* 行高 */
  --leading-tight: 1.3;
  --leading-normal: 1.5;
  --leading-relaxed: 1.65;

  /* 间距阶（4px 基） */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 20px;
  --sp-6: 24px;
  --sp-8: 32px;
  --sp-10: 40px;

  /* 圆角 */
  --radius-sm: 7px;
  --radius-md: 11px;
  --radius-lg: 16px;
  --radius-xl: 20px;

  /* 动效：只两档 */
  --motion-fast: 150ms;
  --motion-base: 180ms;
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);

  /* 字体 */
  --font-ui: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
    system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;

  --chrome-pad-left: 78px; /* macOS 交通灯留位 */
}

:root,
html[data-theme="dark"] {
  color-scheme: dark;

  /* 层级阶 */
  --layer-0: #07090d; /* 沉底 —— 左右栏 */
  --layer-1: #0e1219; /* 基准 —— 中间栏 */
  --layer-2: #161b25; /* 卡片 */
  --layer-3: #1d2431; /* 浮层 */

  --border-0: rgba(140, 160, 200, 0.08);
  --border-1: rgba(140, 160, 200, 0.14);
  --border-2: rgba(140, 160, 200, 0.22);

  --shadow-1: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-2: 0 4px 12px rgba(0, 0, 0, 0.35);
  --shadow-3: 0 12px 40px rgba(0, 0, 0, 0.45);

  --text: #e9eef8;
  --text-muted: #8b96ab;
  --text-faint: #5c6678;
  --text-inverse: #041016;

  /* accent 只表示「主操作」与「当前选中」，不表示任何状态 */
  --accent: #3ee0c5;
  --accent-muted: rgba(62, 224, 197, 0.12);
  --accent-glow: rgba(62, 224, 197, 0.28);

  /* 状态色各归各位 */
  --ok: #3dd68c;
  --ok-muted: rgba(61, 214, 140, 0.12);
  --warn: #f5b942;
  --warn-muted: rgba(245, 185, 66, 0.14);
  --danger: #f07178;
  --danger-muted: rgba(240, 113, 120, 0.14);
  --info: #6eb6ff;
  --info-muted: rgba(110, 182, 255, 0.12);
  --plan: #a78bfa;
  --plan-muted: rgba(167, 139, 250, 0.14);
}

html[data-theme="light"] {
  color-scheme: light;

  --layer-0: #e7ebf1;
  --layer-1: #f4f6fa;
  --layer-2: #ffffff;
  --layer-3: #ffffff;

  --border-0: rgba(15, 23, 42, 0.06);
  --border-1: rgba(15, 23, 42, 0.1);
  --border-2: rgba(15, 23, 42, 0.16);

  --shadow-1: 0 1px 2px rgba(15, 23, 42, 0.06);
  --shadow-2: 0 4px 12px rgba(15, 23, 42, 0.08);
  --shadow-3: 0 12px 40px rgba(15, 23, 42, 0.12);

  --text: #0f172a;
  --text-muted: #64748b;
  --text-faint: #94a3b8;
  --text-inverse: #f8fafc;

  --accent: #0d9488;
  --accent-muted: rgba(13, 148, 136, 0.1);
  --accent-glow: rgba(13, 148, 136, 0.18);

  --ok: #059669;
  --ok-muted: rgba(5, 150, 105, 0.1);
  --warn: #d97706;
  --warn-muted: rgba(217, 119, 6, 0.12);
  --danger: #dc2626;
  --danger-muted: rgba(220, 38, 38, 0.1);
  --info: #2563eb;
  --info-muted: rgba(37, 99, 235, 0.1);
  --plan: #7c3aed;
  --plan-muted: rgba(124, 58, 237, 0.1);
}

/* 兼容层：旧组件仍引用的别名，随迁移逐步删除。
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

> 兼容层是有意保留的：`styles.css`(1455 行) 与 `views.css`(746 行) 里的旧规则仍在引用 `--bg` / `--surface` 等。没有它，Settings 与 Evidence 会立刻破版。Task 16 收尾时评估还能删掉多少。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- tokens`
Expected: PASS

- [ ] **Step 5: 目视确认三个视图未破版**

```bash
cd apps/desktop && npm run dev:renderer
```

浏览器打开 `http://localhost:5173`，深浅主题各切一次，确认调查 / 证据 / 设置三页均无破版（此时观感尚未改动，只是配色轻微变化）。确认后 `Ctrl-C` 停掉。

- [ ] **Step 6: 提交**

```bash
git add apps/desktop/renderer/styles/tokens.css apps/desktop/renderer/__tests__/styles/
git commit -m "feat(desktop-ui): 收紧 token 层 — 字阶/间距阶/四级层级阶/色彩职责拆分"
```

---

### Task 3: Primitives A —— Button / StatusDot / Card / Panel

**Files:**
- Create: `apps/desktop/renderer/ui/Button.tsx` `Button.css`
- Create: `apps/desktop/renderer/ui/StatusDot.tsx` `StatusDot.css`
- Create: `apps/desktop/renderer/ui/Card.tsx` `Card.css`
- Create: `apps/desktop/renderer/ui/Panel.tsx` `Panel.css`
- Create: `apps/desktop/renderer/ui/index.ts`
- Test: `apps/desktop/renderer/__tests__/ui/Button.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 token
- Produces:
  - `Button`: `props { variant?: "primary"|"secondary"|"ghost"|"danger"; size?: "sm"|"md"; } & React.ButtonHTMLAttributes<HTMLButtonElement>`，根元素 `<button type="button">`，类名 `ui-btn ui-btn--{variant} ui-btn--{size}`
  - `StatusDot`: `props { level: "ok"|"warn"|"danger"|"info"|"idle"; pulse?: boolean; label?: string }`
  - `Card`: `props { tone?: "default"|"ok"|"warn"|"danger"|"info"|"plan"; children: React.ReactNode; className?: string }`
  - `Panel`: `props { title?: React.ReactNode; actions?: React.ReactNode; tone?: "sunken"|"raised"; children: React.ReactNode; footer?: React.ReactNode }`

- [ ] **Step 1: 写 Button 测试（先失败）**

Create `apps/desktop/renderer/__tests__/ui/Button.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../../ui/Button";

describe("Button", () => {
  it("默认是 secondary + md，且 type=button", () => {
    render(<Button>运行</Button>);
    const btn = screen.getByRole("button", { name: "运行" });
    expect(btn.className).toContain("ui-btn--secondary");
    expect(btn.className).toContain("ui-btn--md");
    expect(btn.getAttribute("type")).toBe("button");
  });

  it.each([
    ["primary", "ui-btn--primary"],
    ["danger", "ui-btn--danger"],
    ["ghost", "ui-btn--ghost"],
  ] as const)("variant=%s 落到类名 %s", (variant, cls) => {
    render(<Button variant={variant}>x</Button>);
    expect(screen.getByRole("button").className).toContain(cls);
  });

  it("disabled 时不触发 onClick 且带 aria-disabled", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        x
      </Button>
    );
    const btn = screen.getByRole("button");
    btn.click();
    expect(onClick).not.toHaveBeenCalled();
    expect(btn.getAttribute("aria-disabled")).toBe("true");
  });

  it("允许外部追加 className", () => {
    render(<Button className="extra">x</Button>);
    expect(screen.getByRole("button").className).toContain("extra");
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- Button`
Expected: FAIL，`Failed to resolve import "../../ui/Button"`

- [ ] **Step 3: 实现 Button**

Create `apps/desktop/renderer/ui/Button.tsx`：

```tsx
import type { ButtonHTMLAttributes } from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`ui-btn ui-btn--${variant} ui-btn--${size} ${className}`.trim()}
      disabled={disabled}
      aria-disabled={disabled || undefined}
      {...rest}
    />
  );
}
```

Create `apps/desktop/renderer/ui/Button.css`：

```css
.ui-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  font-family: var(--font-ui);
  font-weight: 500;
  line-height: var(--leading-normal);
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--motion-fast) var(--ease-out),
    border-color var(--motion-fast) var(--ease-out),
    color var(--motion-fast) var(--ease-out);
}

.ui-btn--sm {
  height: 26px;
  padding: 0 var(--sp-3);
  font-size: var(--text-xs);
}

.ui-btn--md {
  height: 32px;
  padding: 0 var(--sp-4);
  font-size: var(--text-sm);
}

.ui-btn--primary {
  background: var(--accent);
  color: var(--text-inverse);
}
.ui-btn--primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 88%, white);
}

.ui-btn--secondary {
  background: var(--layer-2);
  border-color: var(--border-1);
  color: var(--text);
}
.ui-btn--secondary:hover:not(:disabled) {
  background: var(--layer-3);
  border-color: var(--border-2);
}

.ui-btn--ghost {
  background: transparent;
  color: var(--text-muted);
}
.ui-btn--ghost:hover:not(:disabled) {
  background: var(--layer-2);
  color: var(--text);
}

.ui-btn--danger {
  background: var(--danger-muted);
  border-color: color-mix(in srgb, var(--danger) 40%, transparent);
  color: var(--danger);
}
.ui-btn--danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--danger) 22%, transparent);
}

.ui-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ui-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- Button`
Expected: PASS，7 passed

- [ ] **Step 5: 实现 StatusDot**

Create `apps/desktop/renderer/ui/StatusDot.tsx`：

```tsx
import "./StatusDot.css";

export type StatusLevel = "ok" | "warn" | "danger" | "info" | "idle";

export type StatusDotProps = {
  level: StatusLevel;
  pulse?: boolean;
  label?: string;
  title?: string;
};

export function StatusDot({ level, pulse, label, title }: StatusDotProps) {
  return (
    <span className="ui-dot-wrap" title={title}>
      <span
        className={`ui-dot ui-dot--${level}${pulse ? " ui-dot--pulse" : ""}`}
        aria-hidden
      />
      {label ? <span className="ui-dot-label">{label}</span> : null}
    </span>
  );
}
```

Create `apps/desktop/renderer/ui/StatusDot.css`：

```css
.ui-dot-wrap {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-1);
  font-size: var(--text-2xs);
  color: var(--text-muted);
}

.ui-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
  background: var(--text-faint);
}

.ui-dot--ok { background: var(--ok); }
.ui-dot--warn { background: var(--warn); }
.ui-dot--danger { background: var(--danger); }
.ui-dot--info { background: var(--info); }
.ui-dot--idle { background: var(--text-faint); }

.ui-dot--pulse {
  animation: ui-dot-pulse 2s var(--ease-out) infinite;
}

@keyframes ui-dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (prefers-reduced-motion: reduce) {
  .ui-dot--pulse { animation: none; }
}
```

- [ ] **Step 6: 实现 Card 与 Panel**

Create `apps/desktop/renderer/ui/Card.tsx`：

```tsx
import type { ReactNode } from "react";
import "./Card.css";

export type CardTone = "default" | "ok" | "warn" | "danger" | "info" | "plan";

export type CardProps = {
  tone?: CardTone;
  className?: string;
  children: ReactNode;
};

export function Card({ tone = "default", className = "", children }: CardProps) {
  return (
    <div className={`ui-card ui-card--${tone} ${className}`.trim()}>
      {children}
    </div>
  );
}
```

Create `apps/desktop/renderer/ui/Card.css`：

```css
/* 卡片是 layer-2，必须放在 layer-1 容器里（层级差一级） */
.ui-card {
  background: var(--layer-2);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-md);
  padding: var(--sp-4);
  box-shadow: var(--shadow-1);
}

.ui-card--ok { border-left: 2px solid var(--ok); }
.ui-card--warn { border-left: 2px solid var(--warn); }
.ui-card--danger { border-left: 2px solid var(--danger); }
.ui-card--info { border-left: 2px solid var(--info); }
.ui-card--plan { border-left: 2px solid var(--plan); }
```

Create `apps/desktop/renderer/ui/Panel.tsx`：

```tsx
import type { ReactNode } from "react";
import "./Panel.css";

export type PanelProps = {
  title?: ReactNode;
  actions?: ReactNode;
  tone?: "sunken" | "raised";
  footer?: ReactNode;
  className?: string;
  children: ReactNode;
};

export function Panel({
  title,
  actions,
  tone = "sunken",
  footer,
  className = "",
  children,
}: PanelProps) {
  return (
    <section className={`ui-panel ui-panel--${tone} ${className}`.trim()}>
      {title || actions ? (
        <header className="ui-panel-head">
          {title ? <h2 className="ui-panel-title">{title}</h2> : <span />}
          {actions ? <div className="ui-panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="ui-panel-body">{children}</div>
      {footer ? <footer className="ui-panel-foot">{footer}</footer> : null}
    </section>
  );
}
```

Create `apps/desktop/renderer/ui/Panel.css`：

```css
.ui-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.ui-panel--sunken { background: var(--layer-0); }
.ui-panel--raised { background: var(--layer-1); }

.ui-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  flex: none;
}

.ui-panel-title {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.ui-panel-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.ui-panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 var(--sp-4) var(--sp-4);
}

.ui-panel-foot {
  flex: none;
  border-top: 1px solid var(--border-0);
  padding: var(--sp-3) var(--sp-4);
}
```

- [ ] **Step 7: 建桶文件**

Create `apps/desktop/renderer/ui/index.ts`：

```ts
export { Button } from "./Button";
export type { ButtonProps, ButtonSize, ButtonVariant } from "./Button";
export { Card } from "./Card";
export type { CardProps, CardTone } from "./Card";
export { Panel } from "./Panel";
export type { PanelProps } from "./Panel";
export { StatusDot } from "./StatusDot";
export type { StatusDotProps, StatusLevel } from "./StatusDot";
```

- [ ] **Step 8: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

- [ ] **Step 9: 提交**

```bash
git add apps/desktop/renderer/ui/ apps/desktop/renderer/__tests__/ui/
git commit -m "feat(desktop-ui): primitives A — Button/StatusDot/Card/Panel"
```

---

### Task 4: Primitives B —— Select / Tooltip（Radix）

**Files:**
- Create: `apps/desktop/renderer/ui/Select.tsx` `Select.css`
- Create: `apps/desktop/renderer/ui/Tooltip.tsx` `Tooltip.css`
- Modify: `apps/desktop/renderer/ui/index.ts`
- Test: `apps/desktop/renderer/__tests__/ui/Select.test.tsx`

**Interfaces:**
- Consumes: Task 3 的 token 与类名约定
- Produces:
  - `Select<T extends string>`: `props { value: T; onChange: (v: T) => void; options: Array<{ value: T; label: string }>; disabled?: boolean; ariaLabel: string; size?: "sm"|"md" }`
  - `Tooltip`: `props { content: React.ReactNode; children: React.ReactElement; side?: "top"|"right"|"bottom"|"left" }`
  - `TooltipProvider`（Radix Provider 的再导出，需挂在 App 根）

- [ ] **Step 1: 装依赖**

```bash
cd apps/desktop
npm i @radix-ui/react-select@^2.1.4 @radix-ui/react-tooltip@^1.1.6
```

- [ ] **Step 2: 写 Select 测试（先失败）**

Create `apps/desktop/renderer/__tests__/ui/Select.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Select } from "../../ui/Select";

const OPTIONS = [
  { value: "readonly", label: "只读" },
  { value: "full", label: "完整" },
];

describe("Select", () => {
  it("渲染为 combobox 角色并带 aria-label", () => {
    render(
      <Select
        value="readonly"
        onChange={() => {}}
        options={OPTIONS}
        ariaLabel="能力档位"
      />
    );
    const trigger = screen.getByRole("combobox", { name: "能力档位" });
    expect(trigger).toBeTruthy();
  });

  it("显示当前选中项的 label 而非 value", () => {
    render(
      <Select
        value="full"
        onChange={() => {}}
        options={OPTIONS}
        ariaLabel="能力档位"
      />
    );
    expect(screen.getByRole("combobox").textContent).toContain("完整");
  });

  it("disabled 时 trigger 不可用", () => {
    render(
      <Select
        value="readonly"
        onChange={() => {}}
        options={OPTIONS}
        ariaLabel="能力档位"
        disabled
      />
    );
    expect(screen.getByRole("combobox").getAttribute("data-disabled")).not.toBe(
      null
    );
  });

  it("不使用原生 select 元素", () => {
    const { container } = render(
      <Select
        value="readonly"
        onChange={vi.fn()}
        options={OPTIONS}
        ariaLabel="能力档位"
      />
    );
    expect(container.querySelector("select")).toBe(null);
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- Select`
Expected: FAIL，无法解析 `../../ui/Select`

- [ ] **Step 4: 实现 Select**

Create `apps/desktop/renderer/ui/Select.tsx`：

```tsx
import * as RS from "@radix-ui/react-select";
import "./Select.css";

export type SelectOption<T extends string> = { value: T; label: string };

export type SelectProps<T extends string> = {
  value: T;
  onChange: (v: T) => void;
  options: Array<SelectOption<T>>;
  ariaLabel: string;
  disabled?: boolean;
  size?: "sm" | "md";
};

export function Select<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  disabled,
  size = "md",
}: SelectProps<T>) {
  return (
    <RS.Root
      value={value}
      onValueChange={(v) => onChange(v as T)}
      disabled={disabled}
    >
      <RS.Trigger
        className={`ui-select-trigger ui-select-trigger--${size}`}
        aria-label={ariaLabel}
      >
        <RS.Value />
        <RS.Icon className="ui-select-icon">▾</RS.Icon>
      </RS.Trigger>
      <RS.Portal>
        <RS.Content className="ui-select-content" position="popper" sideOffset={4}>
          <RS.Viewport>
            {options.map((o) => (
              <RS.Item key={o.value} value={o.value} className="ui-select-item">
                <RS.ItemText>{o.label}</RS.ItemText>
                <RS.ItemIndicator className="ui-select-check">✓</RS.ItemIndicator>
              </RS.Item>
            ))}
          </RS.Viewport>
        </RS.Content>
      </RS.Portal>
    </RS.Root>
  );
}
```

Create `apps/desktop/renderer/ui/Select.css`：

```css
.ui-select-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  background: var(--layer-2);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-family: var(--font-ui);
  font-weight: 500;
  cursor: pointer;
  transition: border-color var(--motion-fast) var(--ease-out);
}

.ui-select-trigger--sm {
  height: 26px;
  padding: 0 var(--sp-2) 0 var(--sp-3);
  font-size: var(--text-xs);
}

.ui-select-trigger--md {
  height: 32px;
  padding: 0 var(--sp-3) 0 var(--sp-4);
  font-size: var(--text-sm);
}

.ui-select-trigger:hover:not([data-disabled]) {
  border-color: var(--border-2);
}

.ui-select-trigger[data-disabled] {
  opacity: 0.45;
  cursor: not-allowed;
}

.ui-select-trigger:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.ui-select-icon {
  color: var(--text-faint);
  font-size: var(--text-2xs);
}

/* 浮层是 layer-3 */
.ui-select-content {
  background: var(--layer-3);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-3);
  padding: var(--sp-1);
  z-index: 60;
  min-width: var(--radix-select-trigger-width);
}

.ui-select-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--text);
  cursor: pointer;
  user-select: none;
  outline: none;
}

.ui-select-item[data-highlighted] {
  background: var(--accent-muted);
  color: var(--accent);
}

.ui-select-check {
  color: var(--accent);
  font-size: var(--text-xs);
}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- Select`
Expected: PASS，4 passed

- [ ] **Step 6: 实现 Tooltip**

Create `apps/desktop/renderer/ui/Tooltip.tsx`：

```tsx
import * as RT from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";
import "./Tooltip.css";

export const TooltipProvider = RT.Provider;

export type TooltipProps = {
  content: ReactNode;
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
};

export function Tooltip({ content, children, side = "top" }: TooltipProps) {
  if (!content) return children;
  return (
    <RT.Root delayDuration={300}>
      <RT.Trigger asChild>{children}</RT.Trigger>
      <RT.Portal>
        <RT.Content className="ui-tooltip" side={side} sideOffset={6}>
          {content}
          <RT.Arrow className="ui-tooltip-arrow" />
        </RT.Content>
      </RT.Portal>
    </RT.Root>
  );
}
```

Create `apps/desktop/renderer/ui/Tooltip.css`：

```css
.ui-tooltip {
  background: var(--layer-3);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-2);
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  color: var(--text);
  max-width: 320px;
  z-index: 70;
}

.ui-tooltip-arrow {
  fill: var(--layer-3);
}
```

- [ ] **Step 7: 补桶文件导出**

在 `apps/desktop/renderer/ui/index.ts` 追加：

```ts
export { Select } from "./Select";
export type { SelectOption, SelectProps } from "./Select";
export { Tooltip, TooltipProvider } from "./Tooltip";
export type { TooltipProps } from "./Tooltip";
```

- [ ] **Step 8: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

- [ ] **Step 9: 提交**

```bash
git add apps/desktop/package.json apps/desktop/package-lock.json apps/desktop/renderer/ui/ apps/desktop/renderer/__tests__/ui/
git commit -m "feat(desktop-ui): primitives B — Radix Select/Tooltip，替换原生控件"
```

---

### Task 5: Primitives C —— Field / Disclosure / ListRow / Timestamp

**Files:**
- Create: `apps/desktop/renderer/ui/Field.tsx` `Field.css`
- Create: `apps/desktop/renderer/ui/Disclosure.tsx` `Disclosure.css`
- Create: `apps/desktop/renderer/ui/ListRow.tsx` `ListRow.css`
- Create: `apps/desktop/renderer/ui/Timestamp.tsx` `Timestamp.css`
- Modify: `apps/desktop/renderer/ui/index.ts`

**Interfaces:**
- Consumes: Task 3 / Task 4
- Produces:
  - `Field`: `props { label: string; hint?: string; error?: string; htmlFor?: string; children: ReactNode }`
  - `Disclosure`: `props { summary: ReactNode; defaultOpen?: boolean; children: ReactNode; className?: string }`
  - `ListRow`: `props { active?: boolean; title: ReactNode; meta?: ReactNode; onClick?: () => void; actions?: ReactNode }`
  - `Timestamp`: `props { value: number | string; relative?: boolean }`，`formatRelative(ms: number, now?: number): string` 一并导出供测试与复用

- [ ] **Step 1: 实现 Field**

Create `apps/desktop/renderer/ui/Field.tsx`：

```tsx
import type { ReactNode } from "react";
import "./Field.css";

export type FieldProps = {
  label: string;
  hint?: string;
  error?: string;
  htmlFor?: string;
  children: ReactNode;
};

export function Field({ label, hint, error, htmlFor, children }: FieldProps) {
  return (
    <div className={`ui-field${error ? " ui-field--error" : ""}`}>
      <label className="ui-field-label" htmlFor={htmlFor}>
        {label}
      </label>
      <div className="ui-field-control">{children}</div>
      {error ? (
        <p className="ui-field-msg ui-field-msg--error" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="ui-field-msg">{hint}</p>
      ) : null}
    </div>
  );
}
```

Create `apps/desktop/renderer/ui/Field.css`：

```css
.ui-field {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.ui-field-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-muted);
}

.ui-field-msg {
  margin: 0;
  font-size: var(--text-2xs);
  line-height: var(--leading-normal);
  color: var(--text-faint);
}

.ui-field-msg--error {
  color: var(--danger);
}

.ui-field--error .ui-field-control :is(input, textarea) {
  border-color: var(--danger);
}
```

- [ ] **Step 2: 实现 Disclosure**

Create `apps/desktop/renderer/ui/Disclosure.tsx`：

```tsx
import type { ReactNode } from "react";
import "./Disclosure.css";

export type DisclosureProps = {
  summary: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
};

export function Disclosure({
  summary,
  defaultOpen = false,
  className = "",
  children,
}: DisclosureProps) {
  return (
    <details className={`ui-disclosure ${className}`.trim()} open={defaultOpen}>
      <summary className="ui-disclosure-summary">
        <span className="ui-disclosure-caret" aria-hidden>
          ▸
        </span>
        <span className="ui-disclosure-label">{summary}</span>
      </summary>
      <div className="ui-disclosure-body">{children}</div>
    </details>
  );
}
```

Create `apps/desktop/renderer/ui/Disclosure.css`：

```css
.ui-disclosure {
  border-radius: var(--radius-sm);
}

.ui-disclosure-summary {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.ui-disclosure-summary::-webkit-details-marker {
  display: none;
}

.ui-disclosure-summary:hover {
  color: var(--text);
}

.ui-disclosure-summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

.ui-disclosure-caret {
  font-size: var(--text-2xs);
  color: var(--text-faint);
  transition: transform var(--motion-fast) var(--ease-out);
}

.ui-disclosure[open] .ui-disclosure-caret {
  transform: rotate(90deg);
}

.ui-disclosure-body {
  padding-bottom: var(--sp-2);
}

@media (prefers-reduced-motion: reduce) {
  .ui-disclosure-caret { transition: none; }
}
```

- [ ] **Step 3: 实现 ListRow**

Create `apps/desktop/renderer/ui/ListRow.tsx`：

```tsx
import type { ReactNode } from "react";
import "./ListRow.css";

export type ListRowProps = {
  active?: boolean;
  title: ReactNode;
  meta?: ReactNode;
  onClick?: () => void;
  actions?: ReactNode;
};

export function ListRow({ active, title, meta, onClick, actions }: ListRowProps) {
  return (
    <div className={`ui-listrow${active ? " ui-listrow--active" : ""}`}>
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

Create `apps/desktop/renderer/ui/ListRow.css`：

```css
.ui-listrow {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  border-radius: var(--radius-sm);
  transition: background var(--motion-fast) var(--ease-out);
}

.ui-listrow:hover {
  background: var(--layer-1);
}

.ui-listrow--active {
  background: var(--accent-muted);
}

.ui-listrow-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  background: none;
  border: none;
  padding: var(--sp-3);
  cursor: pointer;
  text-align: left;
  font-family: var(--font-ui);
}

.ui-listrow-title {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ui-listrow--active .ui-listrow-title {
  color: var(--accent);
}

.ui-listrow-meta {
  font-size: var(--text-2xs);
  color: var(--text-faint);
}

.ui-listrow-actions {
  flex: none;
  padding-right: var(--sp-2);
  opacity: 0;
  transition: opacity var(--motion-fast) var(--ease-out);
}

.ui-listrow:hover .ui-listrow-actions,
.ui-listrow:focus-within .ui-listrow-actions {
  opacity: 1;
}

.ui-listrow-main:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
  border-radius: var(--radius-sm);
}

@media (prefers-reduced-motion: reduce) {
  .ui-listrow,
  .ui-listrow-actions { transition: none; }
}
```

- [ ] **Step 4: 实现 Timestamp**

Create `apps/desktop/renderer/ui/Timestamp.tsx`：

```tsx
import "./Timestamp.css";

/** 把毫秒时间戳格式化成中文相对时间。now 可注入以便测试。 */
export function formatRelative(ms: number, now: number = Date.now()): string {
  const diff = Math.max(0, now - ms);
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(ms).toLocaleDateString("zh-CN");
}

export type TimestampProps = {
  /** 毫秒时间戳；秒级时间戳会被自动放大 */
  value: number | string;
  relative?: boolean;
};

export function Timestamp({ value, relative = true }: TimestampProps) {
  const raw = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(raw)) return <span className="ui-ts">—</span>;
  const ms = raw < 1e12 ? raw * 1000 : raw;
  const iso = new Date(ms).toISOString();
  return (
    <time className="ui-ts" dateTime={iso} title={new Date(ms).toLocaleString("zh-CN")}>
      {relative ? formatRelative(ms) : new Date(ms).toLocaleTimeString("zh-CN")}
    </time>
  );
}
```

Create `apps/desktop/renderer/ui/Timestamp.css`：

```css
.ui-ts {
  font-size: var(--text-2xs);
  font-variant-numeric: tabular-nums;
  color: var(--text-faint);
}
```

- [ ] **Step 5: 补桶文件导出**

在 `apps/desktop/renderer/ui/index.ts` 追加：

```ts
export { Disclosure } from "./Disclosure";
export type { DisclosureProps } from "./Disclosure";
export { Field } from "./Field";
export type { FieldProps } from "./Field";
export { ListRow } from "./ListRow";
export type { ListRowProps } from "./ListRow";
export { formatRelative, Timestamp } from "./Timestamp";
export type { TimestampProps } from "./Timestamp";
```

- [ ] **Step 6: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add apps/desktop/renderer/ui/
git commit -m "feat(desktop-ui): primitives C — Field/Disclosure/ListRow/Timestamp"
```

---

### Task 6: 状态层 A —— runReducer + useRun

**Files:**
- Create: `apps/desktop/renderer/state/runReducer.ts`
- Create: `apps/desktop/renderer/state/useRun.tsx`
- Test: `apps/desktop/renderer/__tests__/state/useRun.test.ts`

**Interfaces:**
- Consumes: `renderer/lib/types.ts` 的 `Ev` / `Tier`
- Produces:
  - `type RunStatus = "idle" | "running" | "paused" | "done" | "failed"`
  - `type RunState = { status: RunStatus; runId: string | null; pausedRunId: string | null; events: Ev[]; mcpTools: string[]; lastSubmitted: string | null }`
  - `const initialRunState: RunState`
  - `type RunAction`（见 Step 3）
  - `function runReducer(state: RunState, action: RunAction): RunState`
  - `useRun(): RunState & { tier: Tier; setTier: (t: Tier) => void; task: string; setTask: (v: string) => void; steerText: string; setSteerText: (v: string) => void; running: boolean; paused: boolean; run: () => Promise<void>; abort: () => Promise<void>; resume: () => Promise<void>; steer: () => Promise<void>; loadEvents: (events: Ev[]) => void; reset: () => void; dispatch: (a: RunAction) => void }`
  - `RunProvider`（Context Provider，Task 10 挂载）

> **这个 Task 顺带修一个 INV-13 相关的旧问题。** 现状 `WorkbenchView.tsx:66` 写的是
> `props.runStatus === "已暂停" || props.runStatus === "paused"` —— 拿**中文显示字符串驱动控制流**。
> `runStatus` 现在由 `useDesktopRuntime` 塞进中英混杂的显示文案（`"已暂停"` / `"已恢复"` / `"running"` / `"idle"`）。
> 本 Task 把它换成 `RunStatus` 类型枚举，显示文案只在渲染层映射，控制流一律走枚举。

- [ ] **Step 1: 写 reducer 状态机测试（先失败）**

Create `apps/desktop/renderer/__tests__/state/useRun.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import {
  initialRunState,
  runReducer,
  type RunState,
} from "../../state/runReducer";

function apply(state: RunState, evs: Array<Record<string, unknown>>): RunState {
  return evs.reduce(
    (s, ev) => runReducer(s, { type: "event", ev: ev as never }),
    state
  );
}

describe("runReducer 状态机", () => {
  it("初始为 idle", () => {
    expect(initialRunState.status).toBe("idle");
    expect(initialRunState.runId).toBe(null);
  });

  it("submit 进入 running 并记录 lastSubmitted，同时清空旧事件", () => {
    const dirty = { ...initialRunState, events: [{ type: "old" }] };
    const s = runReducer(dirty, { type: "submit", text: "分诊告警" });
    expect(s.status).toBe("running");
    expect(s.lastSubmitted).toBe("分诊告警");
    expect(s.events).toEqual([]);
  });

  it("run_started 记录 runId 与 mcp_tools", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1", mcp_tools: ["mcp__a", "mcp__b"] },
    ]);
    expect(s.status).toBe("running");
    expect(s.runId).toBe("r-1");
    expect(s.mcpTools).toEqual(["mcp__a", "mcp__b"]);
  });

  it("run_paused → paused 并记录 pausedRunId", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "run_paused", run_id: "r-1" },
    ]);
    expect(s.status).toBe("paused");
    expect(s.pausedRunId).toBe("r-1");
  });

  it("run_resumed → running 并清掉 pausedRunId", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "run_paused", run_id: "r-1" },
      { type: "run_resumed", run_id: "r-1" },
    ]);
    expect(s.status).toBe("running");
    expect(s.pausedRunId).toBe(null);
  });

  it("answer_ready → done", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "answer_ready" },
    ]);
    expect(s.status).toBe("done");
  });

  it("error → failed", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "error", error: "boom" },
    ]);
    expect(s.status).toBe("failed");
  });

  it("状态不由中文显示串驱动：ui_status 不影响 status", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "run_paused", run_id: "r-1", ui_status: "随便什么文案" },
    ]);
    expect(s.status).toBe("paused");
  });

  it("token / token_done 事件不进时间线（由 stream 域处理）", () => {
    const s = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
      { type: "token", delta: "abc" },
      { type: "token_done" },
    ]);
    expect(s.events.map((e) => e.type)).toEqual(["run_started"]);
  });

  it("settled 把 running 收敛为 done，但不覆盖 paused", () => {
    const running = apply(initialRunState, [
      { type: "run_started", run_id: "r-1" },
    ]);
    expect(runReducer(running, { type: "settled" }).status).toBe("done");

    const paused = apply(running, [{ type: "run_paused", run_id: "r-1" }]);
    expect(runReducer(paused, { type: "settled" }).status).toBe("paused");
  });

  it("failed 动作把错误写进时间线", () => {
    const s = runReducer(initialRunState, { type: "failed", error: "网络断了" });
    expect(s.status).toBe("failed");
    expect(s.events.at(-1)).toMatchObject({ type: "error", error: "网络断了" });
  });

  it("loadEvents 覆盖时间线并回到 idle", () => {
    const s = runReducer(initialRunState, {
      type: "loadEvents",
      events: [{ type: "user_task", task: "旧任务" }],
    });
    expect(s.status).toBe("idle");
    expect(s.events).toHaveLength(1);
  });

  it("reset 回到初始态", () => {
    const s = apply(initialRunState, [{ type: "run_started", run_id: "r-1" }]);
    expect(runReducer(s, { type: "reset" })).toEqual(initialRunState);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- useRun`
Expected: FAIL，无法解析 `../../state/runReducer`

- [ ] **Step 3: 实现 runReducer**

Create `apps/desktop/renderer/state/runReducer.ts`：

```ts
import type { Ev } from "../lib/types";

/** 运行态枚举。控制流只许比较这个，禁止比较显示文案。 */
export type RunStatus = "idle" | "running" | "paused" | "done" | "failed";

export type RunState = {
  status: RunStatus;
  runId: string | null;
  pausedRunId: string | null;
  events: Ev[];
  mcpTools: string[];
  lastSubmitted: string | null;
};

export const initialRunState: RunState = {
  status: "idle",
  runId: null,
  pausedRunId: null,
  events: [],
  mcpTools: [],
  lastSubmitted: null,
};

export type RunAction =
  | { type: "event"; ev: Ev }
  | { type: "submit"; text: string }
  | { type: "settled" }
  | { type: "failed"; error: string }
  | { type: "loadEvents"; events: Ev[] }
  | { type: "reset" };

/** 流式 token 由 stream 域独占，不进时间线 */
const STREAM_ONLY = new Set(["token", "token_done"]);

function str(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

function reduceEvent(state: RunState, ev: Ev): RunState {
  if (STREAM_ONLY.has(ev.type)) return state;

  let next: RunState = { ...state, events: [...state.events, ev] };

  switch (ev.type) {
    case "run_started": {
      const rid = str(ev.run_id);
      next = {
        ...next,
        status: "running",
        runId: rid ?? next.runId,
        pausedRunId: null,
        mcpTools: Array.isArray(ev.mcp_tools)
          ? ev.mcp_tools.map(String)
          : next.mcpTools,
      };
      break;
    }
    case "start": {
      const rid = str(ev.agent_run_id);
      if (rid) next = { ...next, runId: rid };
      break;
    }
    case "run_paused": {
      // 只看事件类型，不看 ui_status 文案
      next = {
        ...next,
        status: "paused",
        pausedRunId: str(ev.run_id) ?? next.runId,
      };
      break;
    }
    case "run_resumed": {
      next = { ...next, status: "running", pausedRunId: null };
      break;
    }
    case "answer_ready": {
      next = { ...next, status: "done" };
      break;
    }
    case "error": {
      next = { ...next, status: "failed" };
      break;
    }
    default:
      break;
  }

  return next;
}

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case "event":
      return reduceEvent(state, action.ev);

    case "submit":
      return {
        ...state,
        status: "running",
        runId: null,
        pausedRunId: null,
        events: [],
        lastSubmitted: action.text,
      };

    case "settled":
      // IPC 调用返回时收口；暂停态由事件决定，不被覆盖
      return state.status === "running" ? { ...state, status: "done" } : state;

    case "failed":
      return {
        ...state,
        status: "failed",
        events: [
          ...state.events,
          { type: "error", error: action.error, status: "failed" },
        ],
      };

    case "loadEvents":
      return {
        ...state,
        status: "idle",
        runId: null,
        pausedRunId: null,
        events: action.events,
      };

    case "reset":
      return initialRunState;

    default:
      return state;
  }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- useRun`
Expected: PASS，13 passed

- [ ] **Step 5: 实现 useRun + RunProvider**

Create `apps/desktop/renderer/state/useRun.tsx`：

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Ev, Tier } from "../lib/types";
import {
  initialRunState,
  runReducer,
  type RunAction,
  type RunState,
} from "./runReducer";

export type RunContextValue = RunState & {
  tier: Tier;
  setTier: (t: Tier) => void;
  task: string;
  setTask: (v: string) => void;
  steerText: string;
  setSteerText: (v: string) => void;
  running: boolean;
  paused: boolean;
  run: () => Promise<void>;
  abort: () => Promise<void>;
  resume: () => Promise<void>;
  steer: () => Promise<void>;
  loadEvents: (events: Ev[]) => void;
  reset: () => void;
  dispatch: (a: RunAction) => void;
};

const RunContext = createContext<RunContextValue | null>(null);

export type RunProviderProps = {
  children: ReactNode;
  /** 运行成功后回调，用于让 sessions 域刷新列表并选中新会话 */
  onRunSettled?: (sessionId: string | null) => void;
};

export function RunProvider({ children, onRunSettled }: RunProviderProps) {
  const [state, dispatch] = useReducer(runReducer, initialRunState);
  const [tier, setTier] = useState<Tier>("readonly");
  const [task, setTask] = useState("");
  const [steerText, setSteerText] = useState("");

  const taskRef = useRef(task);
  taskRef.current = task;

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;
  const running = state.status === "running";
  const paused = state.status === "paused";

  const run = useCallback(async () => {
    if (!api || running) return;
    const text = taskRef.current.trim();
    if (!text) return;

    dispatch({ type: "submit", text });
    try {
      const res = await api.run(text, tier, undefined);
      const sid =
        (res?.result as { session_id?: string } | undefined)?.session_id || null;
      onRunSettled?.(sid);
      dispatch({ type: "settled" });
    } catch (e) {
      dispatch({ type: "failed", error: String(e) });
    }
  }, [api, tier, running, onRunSettled]);

  const abort = useCallback(async () => {
    if (!api || !state.runId) return;
    await api.abort(state.runId);
  }, [api, state.runId]);

  const resume = useCallback(async () => {
    const rid = state.pausedRunId || state.runId;
    if (!api?.resume || !rid) return;
    try {
      await api.resume(rid);
    } catch (e) {
      dispatch({ type: "failed", error: `resume failed: ${e}` });
    }
  }, [api, state.pausedRunId, state.runId]);

  const steer = useCallback(async () => {
    if (!api || !state.runId || !steerText.trim()) return;
    await api.steer(state.runId, steerText.trim());
    setSteerText("");
  }, [api, state.runId, steerText]);

  const loadEvents = useCallback((events: Ev[]) => {
    dispatch({ type: "loadEvents", events });
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: "reset" });
    setTask("");
  }, []);

  const value = useMemo<RunContextValue>(
    () => ({
      ...state,
      tier,
      setTier,
      task,
      setTask,
      steerText,
      setSteerText,
      running,
      paused,
      run,
      abort,
      resume,
      steer,
      loadEvents,
      reset,
      dispatch,
    }),
    [
      state,
      tier,
      task,
      steerText,
      running,
      paused,
      run,
      abort,
      resume,
      steer,
      loadEvents,
      reset,
    ]
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRun must be used within RunProvider");
  return ctx;
}
```

- [ ] **Step 6: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add apps/desktop/renderer/state/ apps/desktop/renderer/__tests__/state/
git commit -m "feat(desktop-state): 抽出 run 域 — 类型化状态机取代中文串驱动控制流"
```

---

### Task 7: 状态层 B —— useSessions

**Files:**
- Create: `apps/desktop/renderer/state/sessionsReducer.ts`
- Create: `apps/desktop/renderer/state/useSessions.tsx`
- Test: `apps/desktop/renderer/__tests__/state/useSessions.test.ts`

**Interfaces:**
- Consumes: `SessionRow`（`lib/types.ts`）
- Produces:
  - `type SessionsState = { sessions: SessionRow[]; sessionId: string | null }`
  - `const initialSessionsState: SessionsState`
  - `type SessionsAction = { type: "setList"; sessions: SessionRow[] } | { type: "select"; sessionId: string | null } | { type: "removed"; sessionId: string } | { type: "clearAll" }`
  - `function sessionsReducer(state, action): SessionsState`
  - `useSessions(): SessionsState & { refresh: () => void; select: (id: string) => Promise<void>; create: () => void; remove: (id: string) => Promise<void> }`
  - `SessionsProvider`

- [ ] **Step 1: 写测试（先失败）**

Create `apps/desktop/renderer/__tests__/state/useSessions.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import type { SessionRow } from "../../lib/types";
import {
  initialSessionsState,
  sessionsReducer,
} from "../../state/sessionsReducer";

const row = (id: string): SessionRow => ({
  session_id: id,
  title: `会话 ${id}`,
  tier: "readonly",
  updated_at: 1,
  event_count: 0,
});

describe("sessionsReducer", () => {
  it("setList 写入列表且不动当前选中", () => {
    const base = { ...initialSessionsState, sessionId: "a" };
    const s = sessionsReducer(base, { type: "setList", sessions: [row("a")] });
    expect(s.sessions).toHaveLength(1);
    expect(s.sessionId).toBe("a");
  });

  it("select 切换当前会话", () => {
    const s = sessionsReducer(initialSessionsState, {
      type: "select",
      sessionId: "b",
    });
    expect(s.sessionId).toBe("b");
  });

  it("删除当前选中的会话时，sessionId 收敛为 null", () => {
    const base = {
      sessions: [row("a"), row("b")],
      sessionId: "a",
    };
    const s = sessionsReducer(base, { type: "removed", sessionId: "a" });
    expect(s.sessionId).toBe(null);
    expect(s.sessions.map((x) => x.session_id)).toEqual(["b"]);
  });

  it("删除非当前会话时，sessionId 不变", () => {
    const base = {
      sessions: [row("a"), row("b")],
      sessionId: "a",
    };
    const s = sessionsReducer(base, { type: "removed", sessionId: "b" });
    expect(s.sessionId).toBe("a");
    expect(s.sessions.map((x) => x.session_id)).toEqual(["a"]);
  });

  it("clearAll 清空列表与选中（卸载后使用）", () => {
    const base = { sessions: [row("a")], sessionId: "a" };
    expect(sessionsReducer(base, { type: "clearAll" })).toEqual(
      initialSessionsState
    );
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- useSessions`
Expected: FAIL，无法解析 `../../state/sessionsReducer`

- [ ] **Step 3: 实现 reducer**

Create `apps/desktop/renderer/state/sessionsReducer.ts`：

```ts
import type { SessionRow } from "../lib/types";

export type SessionsState = {
  sessions: SessionRow[];
  sessionId: string | null;
};

export const initialSessionsState: SessionsState = {
  sessions: [],
  sessionId: null,
};

export type SessionsAction =
  | { type: "setList"; sessions: SessionRow[] }
  | { type: "select"; sessionId: string | null }
  | { type: "removed"; sessionId: string }
  | { type: "clearAll" };

export function sessionsReducer(
  state: SessionsState,
  action: SessionsAction
): SessionsState {
  switch (action.type) {
    case "setList":
      return { ...state, sessions: action.sessions };

    case "select":
      return { ...state, sessionId: action.sessionId };

    case "removed":
      return {
        sessions: state.sessions.filter(
          (s) => s.session_id !== action.sessionId
        ),
        sessionId:
          state.sessionId === action.sessionId ? null : state.sessionId,
      };

    case "clearAll":
      return initialSessionsState;

    default:
      return state;
  }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- useSessions`
Expected: PASS，5 passed

- [ ] **Step 5: 实现 useSessions + SessionsProvider**

Create `apps/desktop/renderer/state/useSessions.tsx`：

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import type { Ev } from "../lib/types";
import {
  initialSessionsState,
  sessionsReducer,
  type SessionsState,
} from "./sessionsReducer";

export type SessionsContextValue = SessionsState & {
  refresh: () => void;
  select: (id: string) => Promise<void>;
  create: () => void;
  remove: (id: string) => Promise<void>;
  clearAll: () => void;
};

const SessionsContext = createContext<SessionsContextValue | null>(null);

export type SessionsProviderProps = {
  children: ReactNode;
  /** 选中会话后把历史事件交给 run 域 */
  onEventsLoaded: (events: Ev[], lastTask: string | null) => void;
  /** 新建调查时清空 run 域 */
  onReset: () => void;
};

export function SessionsProvider({
  children,
  onEventsLoaded,
  onReset,
}: SessionsProviderProps) {
  const [state, dispatch] = useReducer(sessionsReducer, initialSessionsState);
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const refresh = useCallback(() => {
    if (!api?.listSessions) return;
    api
      .listSessions()
      .then((r) => dispatch({ type: "setList", sessions: r.sessions || [] }))
      .catch(() => dispatch({ type: "setList", sessions: [] }));
  }, [api]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const select = useCallback(
    async (sid: string) => {
      if (!api) return;
      dispatch({ type: "select", sessionId: sid });
      try {
        const r = await api.sessionEvents(sid);
        const evs = r.events || [];
        let lastTask: string | null = null;
        for (let i = evs.length - 1; i >= 0; i--) {
          if (evs[i].type === "user_task" && typeof evs[i].task === "string") {
            lastTask = String(evs[i].task);
            break;
          }
        }
        onEventsLoaded(evs, lastTask);
      } catch {
        onEventsLoaded([], null);
      }
    },
    [api, onEventsLoaded]
  );

  const create = useCallback(() => {
    dispatch({ type: "select", sessionId: null });
    onReset();
  }, [onReset]);

  const remove = useCallback(
    async (sid: string) => {
      if (!api?.deleteSession) return;
      await api.deleteSession(sid);
      dispatch({ type: "removed", sessionId: sid });
      if (state.sessionId === sid) onReset();
      refresh();
    },
    [api, state.sessionId, onReset, refresh]
  );

  const clearAll = useCallback(() => {
    dispatch({ type: "clearAll" });
    onReset();
  }, [onReset]);

  const value = useMemo<SessionsContextValue>(
    () => ({ ...state, refresh, select, create, remove, clearAll }),
    [state, refresh, select, create, remove, clearAll]
  );

  return (
    <SessionsContext.Provider value={value}>
      {children}
    </SessionsContext.Provider>
  );
}

export function useSessions(): SessionsContextValue {
  const ctx = useContext(SessionsContext);
  if (!ctx) throw new Error("useSessions must be used within SessionsProvider");
  return ctx;
}
```

- [ ] **Step 6: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add apps/desktop/renderer/state/ apps/desktop/renderer/__tests__/state/
git commit -m "feat(desktop-state): 抽出 sessions 域"
```

---

### Task 8: 状态层 C —— useStream 隔离 + usePlan

**Files:**
- Create: `apps/desktop/renderer/state/useStream.tsx`
- Create: `apps/desktop/renderer/state/usePlan.tsx`

**Interfaces:**
- Consumes: `Ev` / `PendingPlan`
- Produces:
  - `useStream(): { streamText: string; streaming: boolean }`
  - `useStreamDispatch(): (ev: Ev) => void`（**独立 context**，供 Task 10 的事件扇出调用，避免高频更新拖动消费者）
  - `StreamProvider`
  - `usePlan(): { pendingPlan: PendingPlan | null; planEdit: string; setPlanEdit: (v: string) => void; approve: () => Promise<void>; reject: () => Promise<void>; ingest: (ev: Ev) => void }`
  - `PlanProvider`

> **为什么 stream 必须自成一域**：流式输出每 token 触发一次 setState。若与 `running` / `tier` 同处一个 context，
> 每个 token 都会让三栏全部重渲染。这里把「读」（`useStream`）与「写」（`useStreamDispatch`）拆成两个 context，
> 写侧引用恒定，读侧只被流式卡片消费。

- [ ] **Step 1: 实现 StreamProvider**

Create `apps/desktop/renderer/state/useStream.tsx`：

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Ev } from "../lib/types";

type StreamValue = { streamText: string; streaming: boolean };

const StreamStateContext = createContext<StreamValue | null>(null);
const StreamDispatchContext = createContext<((ev: Ev) => void) | null>(null);

export function StreamProvider({ children }: { children: ReactNode }) {
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);

  // 引用恒定：不随 streamText 变化，故写侧消费者永不因流式更新重渲染
  const ingest = useCallback((ev: Ev) => {
    if (ev.type === "token" && typeof ev.delta === "string") {
      setStreaming(true);
      setStreamText((prev) => prev + String(ev.delta));
      return;
    }
    if (ev.type === "token_done") {
      setStreaming(false);
      return;
    }
    // 新一轮工具调用：清掉中间模型碎碎念，保证最终流式输出干净
    if (ev.type === "tool_call_start" || ev.type === "run_started") {
      setStreamText("");
      setStreaming(false);
      return;
    }
    // 完整答案已成卡片，清空实时缓冲
    if (ev.type === "answer_ready" || ev.type === "error") {
      setStreamText("");
      setStreaming(false);
    }
  }, []);

  const value = useMemo<StreamValue>(
    () => ({ streamText, streaming }),
    [streamText, streaming]
  );

  return (
    <StreamDispatchContext.Provider value={ingest}>
      <StreamStateContext.Provider value={value}>
        {children}
      </StreamStateContext.Provider>
    </StreamDispatchContext.Provider>
  );
}

export function useStream(): StreamValue {
  const ctx = useContext(StreamStateContext);
  if (!ctx) throw new Error("useStream must be used within StreamProvider");
  return ctx;
}

export function useStreamDispatch(): (ev: Ev) => void {
  const ctx = useContext(StreamDispatchContext);
  if (!ctx)
    throw new Error("useStreamDispatch must be used within StreamProvider");
  return ctx;
}
```

- [ ] **Step 2: 实现 PlanProvider**

Create `apps/desktop/renderer/state/usePlan.tsx`：

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Ev, PendingPlan } from "../lib/types";

export type PlanContextValue = {
  pendingPlan: PendingPlan | null;
  planEdit: string;
  setPlanEdit: (v: string) => void;
  approve: () => Promise<void>;
  reject: () => Promise<void>;
  ingest: (ev: Ev) => void;
};

const PlanContext = createContext<PlanContextValue | null>(null);

export type PlanProviderProps = {
  children: ReactNode;
  /** 审批调用失败时把错误交回 run 域的时间线 */
  onError: (message: string) => void;
};

export function PlanProvider({ children, onError }: PlanProviderProps) {
  const [pendingPlan, setPendingPlan] = useState<PendingPlan | null>(null);
  const [planEdit, setPlanEdit] = useState("");
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const ingest = useCallback((ev: Ev) => {
    if (
      (ev.type === "plan_ready" || ev.type === "privilege_required") &&
      typeof ev.plan_id === "string"
    ) {
      const plan = (ev.plan || {}) as PendingPlan["plan"];
      // approval_type 必须原样透传：standalone 下为 self，不得与职责分离审批混同（INV-06 / INV-38）
      const approvalType = String(ev.approval_type || "self");
      const base = String(ev.ui_label || "自批准");
      setPendingPlan({
        plan_id: String(ev.plan_id),
        plan,
        approval_type: approvalType,
        ui_label: ev.type === "privilege_required" ? `${base} · 提权` : base,
        local_approve_allowed: ev.local_approve_allowed !== false,
        timeout_seconds:
          typeof ev.timeout_seconds === "number" ? ev.timeout_seconds : undefined,
      });
      setPlanEdit(String(plan?.summary || ""));
      return;
    }
    if (
      ev.type === "plan_approved" ||
      ev.type === "plan_rejected" ||
      ev.type === "privilege_decided"
    ) {
      setPendingPlan(null);
    }
  }, []);

  const approve = useCallback(async () => {
    if (!api?.planApprove || !pendingPlan) return;
    if (!pendingPlan.local_approve_allowed) return;
    const trimmed = planEdit.trim();
    const revised =
      trimmed && trimmed !== (pendingPlan.plan?.summary || "")
        ? trimmed
        : undefined;
    try {
      await api.planApprove(pendingPlan.plan_id, revised);
    } catch (e) {
      onError(`plan approve failed: ${e}`);
    }
  }, [api, pendingPlan, planEdit, onError]);

  const reject = useCallback(async () => {
    if (!api?.planReject || !pendingPlan) return;
    try {
      await api.planReject(pendingPlan.plan_id, "rejected_by_user");
    } catch (e) {
      onError(`plan reject failed: ${e}`);
    }
  }, [api, pendingPlan, onError]);

  const value = useMemo<PlanContextValue>(
    () => ({ pendingPlan, planEdit, setPlanEdit, approve, reject, ingest }),
    [pendingPlan, planEdit, approve, reject, ingest]
  );

  return <PlanContext.Provider value={value}>{children}</PlanContext.Provider>;
}

export function usePlan(): PlanContextValue {
  const ctx = useContext(PlanContext);
  if (!ctx) throw new Error("usePlan must be used within PlanProvider");
  return ctx;
}
```

- [ ] **Step 3: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add apps/desktop/renderer/state/
git commit -m "feat(desktop-state): 抽出 stream 域（读写双 context 隔离高频更新）与 plan 域"
```

---

### Task 9: 状态层 D —— useEnvironment + 降级派生

**Files:**
- Create: `apps/desktop/renderer/state/degradations.ts`
- Create: `apps/desktop/renderer/state/useEnvironment.tsx`
- Test: `apps/desktop/renderer/__tests__/state/useEnvironment.test.ts`

**Interfaces:**
- Consumes: `Caps`
- Produces:
  - `type EnvState = { pingOk: boolean | null; caps: Caps | null; dataRoot: string; providerMode: string; sandboxImpl: string; sandboxMode: string; fvWarning: string | null; tccSummary: string; tccWarning: string | null; tccGuidance: string | null; evidenceCount: number; mcpTools: string[] }`
  - `const initialEnvState: EnvState`
  - `type DegradationLevel = "warn" | "danger"`
  - `type Degradation = { id: "offline" | "sandbox" | "filevault" | "tcc" | "mock"; level: DegradationLevel; label: string; detail?: string; security: boolean }`
  - `function deriveDegradations(env: EnvState): Degradation[]`
  - `useEnvironment(): EnvState & { degradations: Degradation[]; securityDegradations: Degradation[]; refreshProvider: () => Promise<void>; setProviderMode: (m: string) => void; setEvidenceCount: (n: number) => void; ingest: (ev: Ev) => void }`
  - `EnvironmentProvider`

> `security: true` 的降级项走顶部浮出条与专属视觉（INV-38：降级不得伪装成普通错误）；
> `security: false` 的（如 mock 模型）只在状态栏标注。

- [ ] **Step 1: 写降级派生测试（先失败）**

Create `apps/desktop/renderer/__tests__/state/useEnvironment.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import {
  deriveDegradations,
  initialEnvState,
  type EnvState,
} from "../../state/degradations";

const healthy: EnvState = {
  ...initialEnvState,
  pingOk: true,
  providerMode: "live",
  sandboxImpl: "seatbelt",
  tccSummary: "fda_likely",
};

describe("deriveDegradations", () => {
  it("全健康时无降级", () => {
    expect(deriveDegradations(healthy)).toEqual([]);
  });

  it("sidecar 离线 → danger + security", () => {
    const d = deriveDegradations({ ...healthy, pingOk: false });
    const item = d.find((x) => x.id === "offline");
    expect(item?.level).toBe("danger");
    expect(item?.security).toBe(true);
  });

  it("sandbox_impl=none → danger + security（INV-16）", () => {
    const d = deriveDegradations({ ...healthy, sandboxImpl: "none" });
    const item = d.find((x) => x.id === "sandbox");
    expect(item?.level).toBe("danger");
    expect(item?.security).toBe(true);
  });

  it("FileVault 告警 → danger + security", () => {
    const d = deriveDegradations({ ...healthy, fvWarning: "FileVault 未开启" });
    const item = d.find((x) => x.id === "filevault");
    expect(item?.level).toBe("danger");
    expect(item?.security).toBe(true);
    expect(item?.detail).toContain("FileVault");
  });

  it("TCC 受限 → warn + security", () => {
    const d = deriveDegradations({ ...healthy, tccSummary: "restricted" });
    const item = d.find((x) => x.id === "tcc");
    expect(item?.level).toBe("warn");
    expect(item?.security).toBe(true);
  });

  it("mock 模型 → warn 但不是安全降级（不占顶部浮出）", () => {
    const d = deriveDegradations({ ...healthy, providerMode: "mock" });
    const item = d.find((x) => x.id === "mock");
    expect(item?.level).toBe("warn");
    expect(item?.security).toBe(false);
  });

  it("多项同时降级时按 danger 在前排序", () => {
    const d = deriveDegradations({
      ...healthy,
      providerMode: "mock",
      tccSummary: "restricted",
      sandboxImpl: "none",
    });
    expect(d[0].level).toBe("danger");
    expect(d.map((x) => x.id)).toContain("mock");
  });

  it("pingOk=null（连接中）不算降级", () => {
    const d = deriveDegradations({ ...healthy, pingOk: null });
    expect(d.find((x) => x.id === "offline")).toBeUndefined();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- useEnvironment`
Expected: FAIL，无法解析 `../../state/degradations`

- [ ] **Step 3: 实现 degradations**

Create `apps/desktop/renderer/state/degradations.ts`：

```ts
import type { Caps } from "../lib/types";

export type EnvState = {
  pingOk: boolean | null;
  caps: Caps | null;
  dataRoot: string;
  providerMode: string;
  sandboxImpl: string;
  sandboxMode: string;
  fvWarning: string | null;
  tccSummary: string;
  tccWarning: string | null;
  tccGuidance: string | null;
  evidenceCount: number;
  mcpTools: string[];
};

export const initialEnvState: EnvState = {
  pingOk: null,
  caps: null,
  dataRoot: "",
  providerMode: "mock",
  sandboxImpl: "unknown",
  sandboxMode: "—",
  fvWarning: null,
  tccSummary: "—",
  tccWarning: null,
  tccGuidance: null,
  evidenceCount: 0,
  mcpTools: [],
};

export type DegradationLevel = "warn" | "danger";

export type DegradationId =
  | "offline"
  | "sandbox"
  | "filevault"
  | "tcc"
  | "mock";

export type Degradation = {
  id: DegradationId;
  level: DegradationLevel;
  label: string;
  detail?: string;
  /** true = 安全边界降级，必须顶部浮出且用专属视觉（INV-38） */
  security: boolean;
};

/**
 * 从环境状态派生降级清单。
 * 纯函数，便于测试；顺序为 danger 在前、warn 在后。
 */
export function deriveDegradations(env: EnvState): Degradation[] {
  const out: Degradation[] = [];

  if (env.pingOk === false) {
    out.push({
      id: "offline",
      level: "danger",
      label: "sidecar 离线",
      detail: "本地执行进程未连接，运行已禁用",
      security: true,
    });
  }

  if (env.sandboxImpl === "none") {
    out.push({
      id: "sandbox",
      level: "danger",
      label: "沙箱不可用",
      detail: "仅允许只读档位（INV-16）",
      security: true,
    });
  }

  if (env.fvWarning) {
    out.push({
      id: "filevault",
      level: "danger",
      label: "FileVault 未开启",
      detail: env.fvWarning,
      security: true,
    });
  }

  if (env.tccSummary === "restricted" || env.tccWarning) {
    out.push({
      id: "tcc",
      level: "warn",
      label: "磁盘访问受限",
      detail: env.tccGuidance || env.tccWarning || "部分目录读取会失败",
      security: true,
    });
  }

  if (env.providerMode !== "live") {
    out.push({
      id: "mock",
      level: "warn",
      label: "模型为 mock",
      detail: "未配置真实模型，输出不可用于结论",
      security: false,
    });
  }

  return out.sort((a, b) => {
    if (a.level === b.level) return 0;
    return a.level === "danger" ? -1 : 1;
  });
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- useEnvironment`
Expected: PASS，8 passed

- [ ] **Step 5: 实现 EnvironmentProvider**

Create `apps/desktop/renderer/state/useEnvironment.tsx`：

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Caps, Ev, Tier } from "../lib/types";
import {
  deriveDegradations,
  initialEnvState,
  type Degradation,
  type EnvState,
} from "./degradations";

export type EnvironmentContextValue = EnvState & {
  degradations: Degradation[];
  securityDegradations: Degradation[];
  refreshProvider: () => Promise<void>;
  setProviderMode: (m: string) => void;
  setEvidenceCount: (n: number) => void;
  ingest: (ev: Ev) => void;
};

const EnvironmentContext = createContext<EnvironmentContextValue | null>(null);

export function EnvironmentProvider({
  children,
  tier,
}: {
  children: ReactNode;
  tier: Tier;
}) {
  const [env, setEnv] = useState<EnvState>(initialEnvState);
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const patch = useCallback((p: Partial<EnvState>) => {
    setEnv((prev) => ({ ...prev, ...p }));
  }, []);

  // ping：拉一次环境全貌
  useEffect(() => {
    if (!api) {
      patch({ pingOk: false });
      return;
    }
    api
      .ping()
      .then((r: Record<string, unknown>) => {
        const prov = r?.provider as { mode?: string } | undefined;
        const sb = r?.sandbox as { sandbox_impl?: string } | undefined;
        const defaults = r?.policy_defaults as
          | { readonly?: { sandbox_mode?: string } }
          | undefined;
        const fv = r?.filevault as { warning?: string | null } | undefined;
        const tcc = r?.tcc as
          | {
              summary?: string;
              warning?: string | null;
              guidance?: string | null;
              full_disk_access?: boolean | null;
            }
          | undefined;

        let tccSummary = initialEnvState.tccSummary;
        if (tcc?.summary) tccSummary = String(tcc.summary);
        else if (tcc?.full_disk_access === true) tccSummary = "fda_likely";
        else if (tcc?.full_disk_access === false) tccSummary = "restricted";

        patch({
          pingOk: true,
          dataRoot: typeof r?.data_root === "string" ? r.data_root : "",
          providerMode: prov?.mode ? String(prov.mode) : "mock",
          sandboxImpl: sb?.sandbox_impl ? String(sb.sandbox_impl) : "unknown",
          sandboxMode: defaults?.readonly?.sandbox_mode
            ? String(defaults.readonly.sandbox_mode)
            : "—",
          fvWarning: fv?.warning || null,
          tccSummary,
          tccWarning: tcc?.warning || null,
          tccGuidance: tcc?.guidance || null,
          evidenceCount:
            typeof r?.evidence_count === "number" ? r.evidence_count : 0,
        });

        // 与 provider.get 对账（secrets 载入后的实际 live/mock）
        void api.providerGet?.().then((p) => {
          const eff = p?.effective?.mode || p?.mode;
          if (eff) patch({ providerMode: String(eff) });
        });
      })
      .catch(() => patch({ pingOk: false }));
  }, [api, patch]);

  // caps 随档位变化
  useEffect(() => {
    if (!api) return;
    api
      .capabilities(tier)
      .then((c: Caps) => {
        patch({
          caps: c,
          sandboxMode: c.policy?.sandbox_mode
            ? String(c.policy.sandbox_mode)
            : initialEnvState.sandboxMode,
        });
      })
      .catch(() => patch({ caps: null }));
  }, [api, tier, patch]);

  const ingest = useCallback(
    (ev: Ev) => {
      if (ev.type === "run_started" && Array.isArray(ev.mcp_tools)) {
        patch({ mcpTools: ev.mcp_tools.map(String) });
      }
    },
    [patch]
  );

  const refreshProvider = useCallback(async () => {
    if (!api?.providerGet) return;
    try {
      const p = await api.providerGet();
      patch({ providerMode: String(p.effective?.mode || p.mode || "mock") });
    } catch {
      /* 功能性失败，best-effort */
    }
  }, [api, patch]);

  const setProviderMode = useCallback(
    (m: string) => patch({ providerMode: m }),
    [patch]
  );
  const setEvidenceCount = useCallback(
    (n: number) => patch({ evidenceCount: n }),
    [patch]
  );

  const degradations = useMemo(() => deriveDegradations(env), [env]);
  const securityDegradations = useMemo(
    () => degradations.filter((d) => d.security),
    [degradations]
  );

  const value = useMemo<EnvironmentContextValue>(
    () => ({
      ...env,
      degradations,
      securityDegradations,
      refreshProvider,
      setProviderMode,
      setEvidenceCount,
      ingest,
    }),
    [
      env,
      degradations,
      securityDegradations,
      refreshProvider,
      setProviderMode,
      setEvidenceCount,
      ingest,
    ]
  );

  return (
    <EnvironmentContext.Provider value={value}>
      {children}
    </EnvironmentContext.Provider>
  );
}

export function useEnvironment(): EnvironmentContextValue {
  const ctx = useContext(EnvironmentContext);
  if (!ctx)
    throw new Error("useEnvironment must be used within EnvironmentProvider");
  return ctx;
}
```

- [ ] **Step 6: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add apps/desktop/renderer/state/ apps/desktop/renderer/__tests__/state/
git commit -m "feat(desktop-state): 抽出 environment 域与降级派生（INV-16/38 落点）"
```

---

### Task 10: RuntimeProvider —— 单一事件订阅扇出

**Files:**
- Create: `apps/desktop/renderer/state/RuntimeProvider.tsx`
- Create: `apps/desktop/renderer/state/index.ts`

**Interfaces:**
- Consumes: Task 6–9 的四个 Provider
- Produces: `RuntimeProvider`（组合全部域，内部只订阅一次 `api.onEvent` 并扇出）；`state/index.ts` 统一导出所有 hook

> **为什么只订阅一次**：`api.onEvent` 是单条 IPC 事件流。若每个域各自 `onEvent`，会注册四个监听器、
> 四份闭包、四种解绑时机。改为 `RuntimeProvider` 订阅一次，把事件同步扇给各域的 `ingest` / `dispatch`。

- [ ] **Step 1: 实现 RuntimeProvider**

Create `apps/desktop/renderer/state/RuntimeProvider.tsx`：

```tsx
import { useCallback, useEffect, useRef, type ReactNode } from "react";
import type { Ev } from "../lib/types";
import { EnvironmentProvider, useEnvironment } from "./useEnvironment";
import { PlanProvider, usePlan } from "./usePlan";
import { RunProvider, useRun } from "./useRun";
import { SessionsProvider, useSessions } from "./useSessions";
import { StreamProvider, useStreamDispatch } from "./useStream";

/**
 * 订阅一次 IPC 事件流，扇出给各域。
 * 必须挂在所有 Provider 内部（要用到各域的 ingest）。
 */
function EventFanout({ children }: { children: ReactNode }) {
  const run = useRun();
  const plan = usePlan();
  const env = useEnvironment();
  const streamIngest = useStreamDispatch();

  // 用 ref 持有最新回调，避免因回调引用变化反复解绑/重订阅 IPC
  const sinks = useRef({ run, plan, env, streamIngest });
  sinks.current = { run, plan, env, streamIngest };

  useEffect(() => {
    const api = typeof window !== "undefined" ? window.cyberguard : undefined;
    if (!api) return;
    return api.onEvent((ev: Ev) => {
      const s = sinks.current;
      s.streamIngest(ev);
      s.run.dispatch({ type: "event", ev });
      s.plan.ingest(ev);
      s.env.ingest(ev);
    });
  }, []);

  return <>{children}</>;
}

/** 把 sessions 与 run 两个域接起来（选中会话 → 载入事件；新建 → 清空） */
function SessionsBridge({ children }: { children: ReactNode }) {
  const run = useRun();

  const onEventsLoaded = useCallback(
    (events: Ev[], lastTask: string | null) => {
      run.loadEvents(events);
      if (lastTask) run.setTask(lastTask);
    },
    [run]
  );

  const onReset = useCallback(() => {
    run.reset();
  }, [run]);

  return (
    <SessionsProvider onEventsLoaded={onEventsLoaded} onReset={onReset}>
      {children}
    </SessionsProvider>
  );
}

/** run 域需要在跑完后刷新会话列表，但 SessionsProvider 在其内层 —— 用事件回调桥接 */
function RunLayer({ children }: { children: ReactNode }) {
  const pendingRefresh = useRef<(() => void) | null>(null);

  const onRunSettled = useCallback(() => {
    pendingRefresh.current?.();
  }, []);

  return (
    <RunProvider onRunSettled={onRunSettled}>
      <SessionsBridge>
        <RefreshRegistrar target={pendingRefresh} />
        {children}
      </SessionsBridge>
    </RunProvider>
  );
}

function RefreshRegistrar({
  target,
}: {
  target: React.MutableRefObject<(() => void) | null>;
}) {
  const sessions = useSessions();
  target.current = sessions.refresh;
  return null;
}

function PlanLayer({ children }: { children: ReactNode }) {
  const run = useRun();
  const onError = useCallback(
    (message: string) => run.dispatch({ type: "failed", error: message }),
    [run]
  );
  return <PlanProvider onError={onError}>{children}</PlanProvider>;
}

function EnvLayer({ children }: { children: ReactNode }) {
  const run = useRun();
  return <EnvironmentProvider tier={run.tier}>{children}</EnvironmentProvider>;
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  return (
    <StreamProvider>
      <RunLayer>
        <PlanLayer>
          <EnvLayer>
            <EventFanout>{children}</EventFanout>
          </EnvLayer>
        </PlanLayer>
      </RunLayer>
    </StreamProvider>
  );
}
```

- [ ] **Step 2: 建状态层桶文件**

Create `apps/desktop/renderer/state/index.ts`：

```ts
export { RuntimeProvider } from "./RuntimeProvider";
export {
  deriveDegradations,
  initialEnvState,
  type Degradation,
  type DegradationId,
  type DegradationLevel,
  type EnvState,
} from "./degradations";
export { initialRunState, runReducer, type RunAction, type RunState, type RunStatus } from "./runReducer";
export {
  initialSessionsState,
  sessionsReducer,
  type SessionsAction,
  type SessionsState,
} from "./sessionsReducer";
export { useEnvironment } from "./useEnvironment";
export { usePlan } from "./usePlan";
export { useRun } from "./useRun";
export { useSessions } from "./useSessions";
export { useStream } from "./useStream";
```

- [ ] **Step 3: 跑全量测试与 typecheck**

Run: `cd apps/desktop && npm test && npm run typecheck`
Expected: 全部 PASS

> 此时 `RuntimeProvider` 尚未接入 `App.tsx`，`useDesktopRuntime` 仍在服役 —— 两套并存是预期的，Task 12 才切换。

- [ ] **Step 4: 提交**

```bash
git add apps/desktop/renderer/state/
git commit -m "feat(desktop-state): RuntimeProvider 组合六域并单点订阅事件扇出"
```

---

### Task 11: 导出 / 卸载迁出 Workbench

**Files:**
- Create: `apps/desktop/renderer/state/useDataLifecycle.tsx`
- Modify: `apps/desktop/renderer/App.tsx`
- Modify: `apps/desktop/renderer/views/SettingsView.tsx`
- Modify: `apps/desktop/renderer/views/WorkbenchView.tsx`
- Modify: `apps/desktop/renderer/hooks/useDesktopRuntime.ts`

**Interfaces:**
- Consumes: 无（独立域）
- Produces: `useDataLifecycle(): { exportPass: string; setExportPass: (v: string) => void; exportBusy: boolean; exportMsg: string | null; exportAvailable: boolean; runExport: () => Promise<void>; uninstallBusy: boolean; uninstallPreview: string | null; inventory: () => Promise<void>; dryRun: () => Promise<void>; execute: () => Promise<void> }`；`DataLifecycleProvider`

> **本 Task 的收益是纯减法**：`WorkbenchView` 的 45 个 props 掉 13 个，且不改任何业务逻辑。
> 导出/卸载只在设置页出现，右栏杂物间少一大块。

- [ ] **Step 1: 实现 DataLifecycleProvider（逻辑从 useDesktopRuntime 原样搬运）**

Create `apps/desktop/renderer/state/useDataLifecycle.tsx`：

```tsx
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type DataLifecycleValue = {
  exportPass: string;
  setExportPass: (v: string) => void;
  exportBusy: boolean;
  exportMsg: string | null;
  exportAvailable: boolean;
  runExport: () => Promise<void>;
  uninstallBusy: boolean;
  uninstallPreview: string | null;
  inventory: () => Promise<void>;
  dryRun: () => Promise<void>;
  execute: () => Promise<void>;
};

const DataLifecycleContext = createContext<DataLifecycleValue | null>(null);

export function DataLifecycleProvider({
  children,
  onUninstalled,
}: {
  children: ReactNode;
  /** 真实卸载执行成功后清空会话状态 */
  onUninstalled?: () => void;
}) {
  const [exportPass, setExportPass] = useState("");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [uninstallPreview, setUninstallPreview] = useState<string | null>(null);
  const [uninstallBusy, setUninstallBusy] = useState(false);

  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const runExport = useCallback(async () => {
    if (!api?.exportEncrypted) {
      setExportMsg("导出 API 不可用（请在 Electron 中打开）");
      return;
    }
    if (exportPass.trim().length < 8) {
      setExportMsg("口令至少 8 位");
      return;
    }
    setExportBusy(true);
    setExportMsg(null);
    try {
      const r = await api.exportEncrypted(exportPass);
      if (r?.canceled) {
        setExportMsg("已取消");
      } else if (r?.ok === false) {
        setExportMsg(String(r.error || "导出失败"));
      } else {
        const dest = r.dest || r.path || "file";
        const hash = r.plaintext_sha256 || r.sha256;
        setExportMsg(
          `已导出（${r.method || "encrypted"}）→ ${dest}` +
            (hash ? ` · sha256 ${String(hash).slice(0, 12)}…` : "")
        );
        setExportPass("");
      }
    } catch (e) {
      setExportMsg(String(e));
    } finally {
      setExportBusy(false);
    }
  }, [api, exportPass]);

  const inventory = useCallback(async () => {
    if (!api?.uninstallInventory) {
      setUninstallPreview("卸载 API 不可用");
      return;
    }
    setUninstallBusy(true);
    try {
      const inv = await api.uninstallInventory();
      const del = (inv.will_delete || [])
        .map((c) => `  - ${c.name} (${c.approx_bytes ?? "?"} B)`)
        .join("\n");
      const keep = (inv.will_not_delete?.evidence_outside_data_root || []).join(
        "\n  - "
      );
      const manual = (inv.manual_steps || [])
        .map((m) => `  - ${m.item}: ${m.action}`)
        .join("\n");
      setUninstallPreview(
        `data_root: ${inv.data_root || "?"}\n` +
          `will delete:\n${del || "  (empty)"}\n` +
          `will NOT delete (external evidence):\n  - ${keep || "(none)"}\n` +
          `manual steps:\n${manual || "  (none)"}`
      );
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api]);

  const dryRun = useCallback(async () => {
    if (!api?.uninstallExecute) return;
    setUninstallBusy(true);
    try {
      const r = await api.uninstallExecute({ confirm: true, dryRun: true });
      setUninstallPreview(
        (prev) =>
          (prev ? prev + "\n\n" : "") +
          `dry_run result: executed=${String(r.executed)} ok=${String(r.ok)}`
      );
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api]);

  const execute = useCallback(async () => {
    if (!api?.uninstallExecute) return;
    setUninstallBusy(true);
    try {
      const r = await api.uninstallExecute({ confirm: true, dryRun: false });
      if (r?.canceled) {
        setUninstallPreview("已取消");
      } else {
        setUninstallPreview(
          `executed=${String(r.executed)} deleted=${
            (r.deleted || []).join(", ") || "—"
          }`
        );
        if (r.executed) onUninstalled?.();
      }
    } catch (e) {
      setUninstallPreview(String(e));
    } finally {
      setUninstallBusy(false);
    }
  }, [api, onUninstalled]);

  const value = useMemo<DataLifecycleValue>(
    () => ({
      exportPass,
      setExportPass,
      exportBusy,
      exportMsg,
      exportAvailable: Boolean(api?.exportEncrypted),
      runExport,
      uninstallBusy,
      uninstallPreview,
      inventory,
      dryRun,
      execute,
    }),
    [
      exportPass,
      exportBusy,
      exportMsg,
      api,
      runExport,
      uninstallBusy,
      uninstallPreview,
      inventory,
      dryRun,
      execute,
    ]
  );

  return (
    <DataLifecycleContext.Provider value={value}>
      {children}
    </DataLifecycleContext.Provider>
  );
}

export function useDataLifecycle(): DataLifecycleValue {
  const ctx = useContext(DataLifecycleContext);
  if (!ctx)
    throw new Error(
      "useDataLifecycle must be used within DataLifecycleProvider"
    );
  return ctx;
}
```

- [ ] **Step 2: 从 useDesktopRuntime 删掉导出/卸载相关状态与函数**

在 `apps/desktop/renderer/hooks/useDesktopRuntime.ts` 中删除：

- `useState` 行：`exportPass` / `exportBusy` / `exportMsg` / `uninstallPreview` / `uninstallBusy` / `showDataPanel`（第 32–37 行）
- `useEffect`：`api.onOpenDataPanel` 订阅（第 206–209 行）
- `useCallback`：`onExport` / `onUninstallInventory` / `onUninstallDryRun` / `onUninstallExecute`（第 360–461 行）
- `return` 对象中的对应键：`exportPass` `setExportPass` `exportBusy` `exportMsg` `uninstallPreview` `uninstallBusy` `showDataPanel` `setShowDataPanel` `onExport` `onUninstallInventory` `onUninstallDryRun` `onUninstallExecute`

同时删掉因此不再使用的 `import`（若 `useMemo` / `useRef` 仍被使用则保留）。

- [ ] **Step 3: 从 WorkbenchView 删掉 13 个 props 与 DataPanel**

在 `apps/desktop/renderer/views/WorkbenchView.tsx` 中：

- `Props` 类型删除这 13 项：`dataRoot` `showDataPanel` `onToggleDataPanel` `exportPass` `onExportPass` `exportBusy` `exportMsg` `onExport` `exportAvailable` `uninstallBusy` `uninstallPreview` `onUninstallInventory` `onUninstallDryRun` `onUninstallExecute`

  > 注意：`dataRoot` 目前还被 `context-advanced` 的调试信息用到（第 350–353 行）。**一并删掉那两行**，`data_root` 归属 Task 13 的状态栏展开面板。

- 删除 `import { DataPanel } from "../components/DataPanel";`
- 删除 JSX 中 `{props.showDataPanel && (<DataPanel … />)}` 整块（第 358–374 行）

- [ ] **Step 4: 在 App.tsx 挂 DataLifecycleProvider 并只传给 SettingsView**

在 `apps/desktop/renderer/App.tsx`：

- 顶部加 `import { DataLifecycleProvider } from "./state/useDataLifecycle";`
- 用 `<DataLifecycleProvider>` 包裹 `return` 的整个 `<div className="app">`
- 删除传给 `WorkbenchView` 的那 14 个 props（13 项 + `dataRoot`）
- 删除传给 `SettingsView` 的 `showDataPanel` / `onToggleDataPanel` / `exportPass` / `onExportPass` / `exportBusy` / `exportMsg` / `onExport` / `exportAvailable` / `uninstallBusy` / `uninstallPreview` / `onUninstallInventory` / `onUninstallDryRun` / `onUninstallExecute` —— 改由 `SettingsView` 内部 `useDataLifecycle()` 自取

- [ ] **Step 5: 让 SettingsView 自取**

在 `apps/desktop/renderer/views/SettingsView.tsx`：

- 加 `import { useDataLifecycle } from "../state/useDataLifecycle";`
- 组件内首行加 `const data = useDataLifecycle();`
- 把 `Props` 中上述 13 项删掉，函数体内所有 `props.exportPass` → `data.exportPass`、`props.onExport` → `data.runExport`、`props.onUninstallInventory` → `data.inventory`、`props.onUninstallDryRun` → `data.dryRun`、`props.onUninstallExecute` → `data.execute`，其余同名映射

  > 只做机械替换，**不改 Settings 的观感与结构**（Global Constraints）。

- [ ] **Step 6: 确认 props 数量**

Run:
```bash
cd apps/desktop && grep -c "^  [a-zA-Z]" renderer/views/WorkbenchView.tsx | head -1
```
人工核对 `Props` 类型块，应从 45 项降到 31 项。

- [ ] **Step 7: 跑全量测试、typecheck 与目视验证**

```bash
cd apps/desktop && npm test && npm run typecheck && npm run dev:renderer
```
浏览器确认：调查页右栏不再有数据面板；设置页「数据」分区的导出与卸载功能仍在。

- [ ] **Step 8: 提交**

```bash
git add apps/desktop/renderer/state/useDataLifecycle.tsx apps/desktop/renderer/App.tsx apps/desktop/renderer/views/ apps/desktop/renderer/hooks/useDesktopRuntime.ts
git commit -m "refactor(desktop): 导出/卸载迁出调查页 — WorkbenchView props 45→31"
```

---

### Task 12: 三栏骨架 + 顶部压到 48px + 安全降级浮出条 + 左栏

**Files:**
- Create: `apps/desktop/renderer/components/shell/AppChrome.tsx` `AppChrome.css`
- Create: `apps/desktop/renderer/components/shell/DegradationStrip.tsx` `DegradationStrip.css`
- Create: `apps/desktop/renderer/components/session/SessionRail.tsx` `SessionRail.css`
- Create: `apps/desktop/renderer/components/workbench/WorkbenchLayout.css`
- Modify: `apps/desktop/renderer/App.tsx`
- Modify: `apps/desktop/renderer/views/WorkbenchView.tsx`

**Interfaces:**
- Consumes: Task 3–5 primitives；Task 10 `RuntimeProvider`；Task 9 `useEnvironment().securityDegradations`
- Produces:
  - `AppChrome`: `props { activeView: ActiveView; onNavigate: (v: ActiveView) => void; themeLabel: string; onCycleTheme: () => void; devTitle: string }`
  - `DegradationStrip`: 无 props，内部 `useEnvironment()`；只渲染 `securityDegradations`
  - `SessionRail`: 无 props，内部 `useSessions()` / `useRun()`
  - CSS 类：`.wb`（三栏 grid）、`.wb-main`（layer-1）、`.wb-rail`（layer-0）

- [ ] **Step 1: 切换 App 到 RuntimeProvider**

在 `apps/desktop/renderer/App.tsx`：

- 删除 `import { useDesktopRuntime } from "./hooks/useDesktopRuntime";` 与 `const rt = useDesktopRuntime();`
- 加 `import { RuntimeProvider } from "./state";` 与 `import { TooltipProvider } from "./ui";`
- 把 `App` 拆成外壳与内容两层：

```tsx
export function App() {
  return (
    <TooltipProvider>
      <RuntimeProvider>
        <AppInner />
      </RuntimeProvider>
    </TooltipProvider>
  );
}
```

- `AppInner` 内用 `useRun()` / `useEnvironment()` / `usePlan()` 取代原先的 `rt.*`
- 删除原 `<header className="chrome">` 整块、`alert-strip` 整块、`<StatusBar …/>` 一行，替换为：

```tsx
<AppChrome
  activeView={activeView}
  onNavigate={setActiveView}
  themeLabel={resolved === "dark" ? "Dark" : "Light"}
  onCycleTheme={cycleTheme}
  devTitle={DEV_TITLE}
/>
<DegradationStrip />
```

- `WorkbenchView` 的 props 此时全部删除，改为 `<WorkbenchView onViewEvidence={openEvidence} onOpenSettings={openSettings} />`（保留这两个跨视图导航回调，其余自取）

- [ ] **Step 2: 实现 AppChrome（48px）**

Create `apps/desktop/renderer/components/shell/AppChrome.tsx`：

```tsx
import type { ActiveView } from "../../lib/types";
import { Button } from "../../ui";
import "./AppChrome.css";

const TABS: Array<{ id: ActiveView; label: string }> = [
  { id: "workbench", label: "调查" },
  { id: "evidence", label: "证据" },
  { id: "settings", label: "设置" },
];

export type AppChromeProps = {
  activeView: ActiveView;
  onNavigate: (v: ActiveView) => void;
  themeLabel: string;
  onCycleTheme: () => void;
  devTitle: string;
};

export function AppChrome({
  activeView,
  onNavigate,
  themeLabel,
  onCycleTheme,
  devTitle,
}: AppChromeProps) {
  return (
    <header className="chrome2">
      <div className="chrome2-brand">
        <span className="chrome2-mark" aria-hidden />
        <span className="chrome2-name">CyberGuard</span>
      </div>
      <nav className="chrome2-nav" aria-label="主导航">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`chrome2-tab${activeView === t.id ? " is-active" : ""}`}
            aria-current={activeView === t.id || undefined}
            onClick={() => onNavigate(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="chrome2-right">
        <span className="chrome2-dev" title={devTitle}>
          DEV
        </span>
        <Button variant="ghost" size="sm" onClick={onCycleTheme}>
          {themeLabel}
        </Button>
      </div>
    </header>
  );
}
```

Create `apps/desktop/renderer/components/shell/AppChrome.css`：

```css
.chrome2 {
  height: 48px;
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--sp-6);
  padding: 0 var(--sp-4) 0 var(--chrome-pad-left);
  background: var(--layer-0);
  border-bottom: 1px solid var(--border-0);
  -webkit-app-region: drag;
}

.chrome2 button,
.chrome2 .chrome2-dev {
  -webkit-app-region: no-drag;
}

.chrome2-brand {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: none;
}

.chrome2-mark {
  width: 16px;
  height: 16px;
  border-radius: 5px;
  background: linear-gradient(140deg, var(--accent), var(--info));
}

.chrome2-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.01em;
}

.chrome2-nav {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}

.chrome2-tab {
  height: 28px;
  padding: 0 var(--sp-3);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: color var(--motion-fast) var(--ease-out),
    background var(--motion-fast) var(--ease-out);
}

.chrome2-tab:hover { color: var(--text); }

/* accent 只表示「当前选中」与「主操作」 */
.chrome2-tab.is-active {
  background: var(--accent-muted);
  color: var(--accent);
}

.chrome2-tab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.chrome2-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.chrome2-dev {
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--warn);
  border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent);
  border-radius: 999px;
  padding: 2px var(--sp-2);
  cursor: help;
}

@media (prefers-reduced-motion: reduce) {
  .chrome2-tab { transition: none; }
}
```

- [ ] **Step 3: 实现 DegradationStrip（仅安全降级浮出，平时零高度）**

Create `apps/desktop/renderer/components/shell/DegradationStrip.tsx`：

```tsx
import { useState } from "react";
import { useEnvironment } from "../../state";
import "./DegradationStrip.css";

export function DegradationStrip() {
  const { securityDegradations } = useEnvironment();
  const [dismissed, setDismissed] = useState<string[]>([]);

  const visible = securityDegradations.filter((d) => !dismissed.includes(d.id));
  if (visible.length === 0) return null;

  return (
    <div className="degstrip" role="alert">
      {visible.map((d) => (
        <div key={d.id} className={`degstrip-item degstrip-item--${d.level}`}>
          <span className="degstrip-lock" aria-hidden>
            🔒
          </span>
          <span className="degstrip-label">{d.label}</span>
          {d.detail ? (
            <span className="degstrip-detail">· {d.detail}</span>
          ) : null}
          <button
            type="button"
            className="degstrip-dismiss"
            onClick={() => setDismissed((prev) => [...prev, d.id])}
          >
            收起
          </button>
        </div>
      ))}
    </div>
  );
}
```

Create `apps/desktop/renderer/components/shell/DegradationStrip.css`：

```css
/* 安全降级专属视觉：锁形标记 + danger/warn 底色。
 * 与普通运行错误（时间线内的失败卡）在视觉上必须可区分（INV-38）。 */
.degstrip {
  flex: none;
  display: flex;
  flex-direction: column;
}

.degstrip-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  border-bottom: 1px solid var(--border-0);
}

.degstrip-item--danger {
  background: var(--danger-muted);
  color: var(--danger);
}

.degstrip-item--warn {
  background: var(--warn-muted);
  color: var(--warn);
}

.degstrip-lock { font-size: var(--text-2xs); }

.degstrip-label { font-weight: 600; }

.degstrip-detail {
  color: inherit;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.degstrip-dismiss {
  margin-left: auto;
  flex: none;
  background: transparent;
  border: 1px solid currentColor;
  border-radius: 999px;
  color: inherit;
  font-size: var(--text-2xs);
  padding: 1px var(--sp-2);
  cursor: pointer;
  opacity: 0.7;
}

.degstrip-dismiss:hover { opacity: 1; }
```

> 「收起」只影响本次会话内的显示；刷新或降级项变化后重新出现。**不做持久化的永久关闭** —— 用户能永久关掉的开关不是安全边界（INV-38）。

- [ ] **Step 4: 实现三栏 grid**

Create `apps/desktop/renderer/components/workbench/WorkbenchLayout.css`：

```css
.wb {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 300px;
  background: var(--layer-0);
}

/* 中间栏抬起当主角，左右沉下当背景 —— 不用边框，靠层级色阶分割 */
.wb-main {
  background: var(--layer-1);
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.wb-rail {
  background: var(--layer-0);
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

@media (max-width: 1180px) {
  .wb { grid-template-columns: 220px minmax(0, 1fr) 260px; }
}
```

- [ ] **Step 5: 实现 SessionRail（含空态示例入口）**

Create `apps/desktop/renderer/components/session/SessionRail.tsx`：

```tsx
import { useRun, useSessions } from "../../state";
import { Button, ListRow, Panel, Timestamp } from "../../ui";
import "./SessionRail.css";

export const SAMPLE_TASKS: Array<{ id: string; label: string; text: string }> = [
  {
    id: "triage",
    label: "告警分诊",
    text: "分诊当前 high/critical 告警，给出优先级与建议动作",
  },
  {
    id: "cve",
    label: "CVE 影响面",
    text: "评估 CVE-2024-3094 在本机环境的影响面与缓解措施",
  },
  {
    id: "alerts",
    label: "读本地告警",
    text: "读取本地告警数据源，总结最近 24 小时的异常模式",
  },
];

export function SessionRail() {
  const { sessions, sessionId, select, create, remove } = useSessions();
  const { setTask, running } = useRun();

  return (
    <Panel
      className="wb-rail sessionrail"
      tone="sunken"
      title="调查"
      actions={
        <Button size="sm" variant="ghost" onClick={create}>
          + 新建
        </Button>
      }
    >
      {sessions.length === 0 ? (
        <div className="sessionrail-empty">
          <p className="sessionrail-empty-hint">还没有调查记录。挑一个开始：</p>
          <div className="sessionrail-samples">
            {SAMPLE_TASKS.map((s) => (
              <button
                key={s.id}
                type="button"
                className="sessionrail-sample"
                disabled={running}
                onClick={() => setTask(s.text)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="sessionrail-list">
          {sessions.map((s) => (
            <ListRow
              key={s.session_id}
              active={s.session_id === sessionId}
              title={s.title || "未命名调查"}
              meta={<Timestamp value={s.updated_at} />}
              onClick={() => void select(s.session_id)}
              actions={
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`删除 ${s.title}`}
                  onClick={() => void remove(s.session_id)}
                >
                  ✕
                </Button>
              }
            />
          ))}
        </div>
      )}
    </Panel>
  );
}
```

Create `apps/desktop/renderer/components/session/SessionRail.css`：

```css
.sessionrail-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sessionrail-empty {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding-top: var(--sp-2);
}

.sessionrail-empty-hint {
  margin: 0;
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--text-muted);
}

.sessionrail-samples {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.sessionrail-sample {
  text-align: left;
  background: var(--layer-1);
  border: 1px solid var(--border-0);
  border-radius: var(--radius-sm);
  padding: var(--sp-3);
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text);
  cursor: pointer;
  transition: border-color var(--motion-fast) var(--ease-out);
}

.sessionrail-sample:hover:not(:disabled) {
  border-color: var(--border-2);
}

.sessionrail-sample:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .sessionrail-sample { transition: none; }
}
```

- [ ] **Step 6: 把 WorkbenchView 改成三栏骨架**

`apps/desktop/renderer/views/WorkbenchView.tsx` 整体替换为：

```tsx
import "../components/workbench/WorkbenchLayout.css";
import { SessionRail } from "../components/session/SessionRail";
import type { SettingsSection } from "../lib/types";

export type WorkbenchViewProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (section?: SettingsSection) => void;
};

export function WorkbenchView(props: WorkbenchViewProps) {
  return (
    <div className="wb">
      <SessionRail />
      <div className="wb-main">
        {/* 时间线与 composer 在 Task 14 / 15 填入 */}
      </div>
      <div className="wb-rail">
        {/* 右栏在 Task 13 填入 */}
      </div>
    </div>
  );
}
```

> `onViewEvidence` / `onOpenSettings` 在 Task 13 被右栏消费；本步先占位不使用，TypeScript 不会报错（未使用的 props 不触发 `noUnusedLocals`，该选项未开启）。

- [ ] **Step 7: 跑测试、typecheck 与目视验证**

```bash
cd apps/desktop && npm test && npm run typecheck && npm run dev:renderer
```

目视确认：顶部只剩一条 48px；三栏中间明显比左右亮一档；左栏空态是三个可点示例；深浅主题各切一次均正常。

- [ ] **Step 8: 提交**

```bash
git add apps/desktop/renderer/components/ apps/desktop/renderer/App.tsx apps/desktop/renderer/views/WorkbenchView.tsx
git commit -m "feat(desktop-ui): 三栏骨架与层级差、顶部压至 48px、安全降级浮出条、左栏空态"
```

---

### Task 13: 右栏 —— 事实区 + 贴底状态栏（六项常显）

**Files:**
- Create: `apps/desktop/renderer/components/context/ContextRail.tsx` `ContextRail.css`
- Create: `apps/desktop/renderer/components/context/StatusBar.tsx` `StatusBar.css`
- Modify: `apps/desktop/renderer/views/WorkbenchView.tsx`
- Delete: `apps/desktop/renderer/components/StatusBar.tsx`（旧版，已无引用）
- Delete: `apps/desktop/renderer/components/DataPanel.tsx`（Task 11 后已无引用）

**Interfaces:**
- Consumes: `useRun()` / `useEnvironment()` / primitives
- Produces: `ContextRail`: `props { onViewEvidence: (id?: string) => void; onOpenSettings: (s?: SettingsSection) => void }`；`StatusBar`: `props { onOpenSettings: (s?: SettingsSection) => void }`

> **合规要点（出口判据 3）**：状态栏六项——连接态 / sandbox / tcc / 模型 / 档位 / 暂停态——**常显且不可折叠**。
> 展开面板只放详情（caps 明细、data_root、sandbox 模式、TCC 指引）。

- [ ] **Step 1: 实现 StatusBar**

Create `apps/desktop/renderer/components/context/StatusBar.tsx`：

```tsx
import { useEnvironment, useRun } from "../../state";
import type { SettingsSection } from "../../lib/types";
import { Disclosure, StatusDot, Tooltip } from "../../ui";
import type { StatusLevel } from "../../ui";
import "./StatusBar.css";

function sandboxLevel(impl: string): StatusLevel {
  if (impl === "none") return "danger";
  if (impl === "unknown") return "warn";
  return "ok";
}

function tccLevel(summary: string): StatusLevel {
  if (summary === "restricted") return "warn";
  if (summary === "fda_likely") return "ok";
  return "idle";
}

export function StatusBar({
  onOpenSettings,
}: {
  onOpenSettings: (s?: SettingsSection) => void;
}) {
  const env = useEnvironment();
  const { tier, paused, pausedRunId } = useRun();

  const online: StatusLevel =
    env.pingOk === null ? "idle" : env.pingOk ? "ok" : "danger";

  return (
    <div className="statusbar">
      {/* 六项常显，不可折叠 —— INV-36 / M2 判据 10 */}
      <div className="statusbar-row">
        <Tooltip content={env.pingOk === false ? "sidecar 未连接" : "sidecar"}>
          <span>
            <StatusDot level={online} label="在线" />
          </span>
        </Tooltip>
        <Tooltip content={`sandbox_impl: ${env.sandboxImpl}`}>
          <span>
            <StatusDot level={sandboxLevel(env.sandboxImpl)} label="沙箱" />
          </span>
        </Tooltip>
        <Tooltip content={env.tccGuidance || `tcc: ${env.tccSummary}`}>
          <span>
            <StatusDot level={tccLevel(env.tccSummary)} label="权限" />
          </span>
        </Tooltip>
      </div>

      <div className="statusbar-row statusbar-row--text">
        <button
          type="button"
          className={`statusbar-chip${
            env.providerMode === "live" ? " is-ok" : " is-warn"
          }`}
          onClick={() => onOpenSettings("llm")}
        >
          {env.providerMode === "live" ? "live" : "mock"}
        </button>
        <span className="statusbar-sep">·</span>
        <span className="statusbar-tier">
          {tier === "readonly" ? "只读" : "完整"}
        </span>
        {paused ? (
          <span className="statusbar-paused">
            ⏸ 已暂停
            {pausedRunId ? ` ${pausedRunId.slice(0, 8)}` : ""}
          </span>
        ) : null}
      </div>

      <Disclosure summary="环境详情" className="statusbar-more">
        <dl className="statusbar-kv">
          <dt>read</dt>
          <dd>
            {env.caps?.has_read ? "yes" : "no"}
            {env.caps?.real_read ? " · real" : ""}
          </dd>
          <dt>exec / edit</dt>
          <dd>
            {env.caps?.has_exec ? "exec" : "—"} /{" "}
            {env.caps?.has_edit ? "edit" : "—"}
          </dd>
          <dt>sandbox_mode</dt>
          <dd>{env.sandboxMode}</dd>
          <dt>tcc</dt>
          <dd>{env.tccSummary}</dd>
          <dt>data_root</dt>
          <dd title={env.dataRoot}>
            …/{env.dataRoot.split("/").slice(-2).join("/") || "—"}
          </dd>
        </dl>
      </Disclosure>
    </div>
  );
}
```

Create `apps/desktop/renderer/components/context/StatusBar.css`：

```css
.statusbar {
  flex: none;
  border-top: 1px solid var(--border-0);
  padding: var(--sp-3) var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.statusbar-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
}

.statusbar-row--text {
  gap: var(--sp-2);
  font-size: var(--text-2xs);
  color: var(--text-muted);
}

.statusbar-chip {
  background: transparent;
  border: 1px solid var(--border-1);
  border-radius: 999px;
  padding: 1px var(--sp-2);
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--text-muted);
  cursor: pointer;
}

.statusbar-chip.is-ok { color: var(--ok); border-color: color-mix(in srgb, var(--ok) 35%, transparent); }
.statusbar-chip.is-warn { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }

.statusbar-sep { color: var(--text-faint); }

.statusbar-tier { font-weight: 500; }

.statusbar-paused {
  color: var(--warn);
  font-weight: 500;
}

.statusbar-more { margin-top: -4px; }

.statusbar-kv {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--sp-1) var(--sp-3);
  margin: 0;
  font-size: var(--text-2xs);
}

.statusbar-kv dt { color: var(--text-faint); }

.statusbar-kv dd {
  margin: 0;
  color: var(--text-muted);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

- [ ] **Step 2: 实现 ContextRail（事实区）**

Create `apps/desktop/renderer/components/context/ContextRail.tsx`：

```tsx
import type { SettingsSection } from "../../lib/types";
import { useEnvironment, useRun } from "../../state";
import { Button, Tooltip } from "../../ui";
import { StatusBar } from "./StatusBar";
import "./ContextRail.css";

/** 从时间线事件里数出「发现」——工具返回的高危计数与证据登记数 */
function useFindings() {
  const { events } = useRun();
  const evidenceIds: string[] = [];
  let highCount = 0;

  for (const ev of events) {
    if (ev.type === "evidence_registered" && typeof ev.evidence_id === "string") {
      evidenceIds.push(ev.evidence_id);
    }
    if (ev.type === "tool_call_end" && typeof ev.summary === "string") {
      const m = /(\d+)\s*(?:条)?\s*(?:high|critical|高危)/i.exec(ev.summary);
      if (m) highCount += Number(m[1]);
    }
  }
  return { evidenceIds, highCount };
}

export type ContextRailProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (s?: SettingsSection) => void;
};

export function ContextRail({
  onViewEvidence,
  onOpenSettings,
}: ContextRailProps) {
  const env = useEnvironment();
  const { evidenceIds, highCount } = useFindings();

  return (
    <div className="wb-rail ctxrail">
      <header className="ctxrail-head">
        <h2 className="ctxrail-title">本次调查</h2>
      </header>

      <div className="ctxrail-body">
        <section className="ctxsec">
          <h3 className="ctxsec-h">发现</h3>
          {highCount > 0 ? (
            <p className="ctxsec-stat ctxsec-stat--danger">{highCount} 条高危</p>
          ) : (
            <p className="ctxsec-empty">尚无</p>
          )}
        </section>

        <section className="ctxsec">
          <div className="ctxsec-hrow">
            <h3 className="ctxsec-h">证据</h3>
            <Button size="sm" variant="ghost" onClick={() => onViewEvidence()}>
              全部
            </Button>
          </div>
          {evidenceIds.length > 0 ? (
            <ul className="ctxsec-list">
              {evidenceIds.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    className="ctxsec-link"
                    onClick={() => onViewEvidence(id)}
                  >
                    {id.slice(0, 12)}…
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ctxsec-empty">本轮未登记 · 库中 {env.evidenceCount} 件</p>
          )}
        </section>

        <section className="ctxsec">
          <div className="ctxsec-hrow">
            <h3 className="ctxsec-h">工具</h3>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onOpenSettings("mcp")}
            >
              数据源
            </Button>
          </div>
          {env.mcpTools.length > 0 ? (
            <ul className="ctxsec-chips">
              {env.mcpTools.map((n) => (
                <li key={n}>
                  <Tooltip content={n}>
                    <span className="ctxsec-chip">
                      {n.replace(/^mcp__/, "").slice(0, 24)}
                    </span>
                  </Tooltip>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ctxsec-empty">未发现 · 可选</p>
          )}
        </section>
      </div>

      <StatusBar onOpenSettings={onOpenSettings} />
    </div>
  );
}
```

Create `apps/desktop/renderer/components/context/ContextRail.css`：

```css
.ctxrail {
  border-left: 1px solid var(--border-0);
}

.ctxrail-head {
  flex: none;
  padding: var(--sp-3) var(--sp-4);
}

.ctxrail-title {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.ctxrail-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
}

.ctxsec { display: flex; flex-direction: column; gap: var(--sp-2); }

.ctxsec-hrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.ctxsec-h {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
}

.ctxsec-stat {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text);
}

.ctxsec-stat--danger { color: var(--danger); }

.ctxsec-empty {
  margin: 0;
  font-size: var(--text-2xs);
  color: var(--text-faint);
}

.ctxsec-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--sp-1); }

.ctxsec-link {
  background: none;
  border: none;
  padding: 0;
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--info);
  cursor: pointer;
}

.ctxsec-link:hover { text-decoration: underline; }

.ctxsec-chips {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-1);
}

.ctxsec-chip {
  display: inline-block;
  background: var(--layer-1);
  border: 1px solid var(--border-0);
  border-radius: 999px;
  padding: 1px var(--sp-2);
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--text-muted);
}
```

- [ ] **Step 3: 接进 WorkbenchView**

在 `apps/desktop/renderer/views/WorkbenchView.tsx` 中把右栏占位替换为：

```tsx
<ContextRail
  onViewEvidence={props.onViewEvidence}
  onOpenSettings={props.onOpenSettings}
/>
```

并加 `import { ContextRail } from "../components/context/ContextRail";`；删掉外层多余的 `<div className="wb-rail">` 包裹（`ContextRail` 自带该类名）。

- [ ] **Step 4: 删掉旧组件**

```bash
cd apps/desktop
git rm renderer/components/StatusBar.tsx renderer/components/DataPanel.tsx
grep -rn "components/StatusBar\|components/DataPanel" renderer/ || echo "无残留引用"
```
Expected: 输出「无残留引用」

- [ ] **Step 5: 跑测试、typecheck 与目视验证**

```bash
cd apps/desktop && npm test && npm run typecheck && npm run dev:renderer
```

目视确认（**这是出口判据 3 的人工核对点**）：右栏底部六项常显；点「环境详情」展开后 caps / data_root 出现，但上方六项不受影响仍在。

- [ ] **Step 6: 提交**

```bash
git add -A apps/desktop/renderer/components apps/desktop/renderer/views/WorkbenchView.tsx
git commit -m "feat(desktop-ui): 右栏拆为事实区 + 贴底状态栏（六项常显，INV-36/M2 判据 10）"
```

---

### Task 14: 时间线 —— 四类事件卡拆分

**Files:**
- Create: `apps/desktop/renderer/components/investigation/Timeline.tsx` `Timeline.css`
- Create: `apps/desktop/renderer/components/investigation/events/ToolEvent.tsx`
- Create: `apps/desktop/renderer/components/investigation/events/PlanEvent.tsx`
- Create: `apps/desktop/renderer/components/investigation/events/MessageEvent.tsx`
- Create: `apps/desktop/renderer/components/investigation/events/StreamEvent.tsx`
- Create: `apps/desktop/renderer/components/investigation/events/events.css`
- Create: `apps/desktop/renderer/components/investigation/events/index.tsx`
- Modify: `apps/desktop/renderer/views/WorkbenchView.tsx`
- Delete: `apps/desktop/renderer/components/EventCard.tsx`

**Interfaces:**
- Consumes: `Ev`；`useRun()`；`useStream()`；`Markdown`（复用现有 `components/Markdown.tsx`）
- Produces:
  - `function classify(ev: Ev): "tool" | "plan" | "message" | "system"`
  - `ToolEvent` / `PlanEvent` / `MessageEvent`：均为 `props { ev: Ev; onViewEvidence?: (id?: string) => void }`
  - `StreamEvent`：无 props，内部 `useStream()`（**唯一消费流式 context 的组件**）
  - `Timeline`：`props { onViewEvidence: (id?: string) => void }`

> **这是"内容太干"的正解。** 现状 `EventCard`(391 行) 把 16 种事件都渲染成同一种灰卡片。
> 拆开后：工具调用出参数与结果摘要、计划出步骤进度、报告出排版、系统事件收成一行细文本。
>
> **必须保留的既有行为**：`tool_call_end` 中 `source_trust === "hostile"` 的标注不得丢失
> —— 敌对来源内容作为结论依据时须可溯源（INV-39）。

- [ ] **Step 1: 实现事件分类与工具卡**

Create `apps/desktop/renderer/components/investigation/events/ToolEvent.tsx`：

```tsx
import { useEffect, useRef, useState } from "react";
import type { Ev } from "../../../lib/types";
import { Card, Disclosure, Tooltip } from "../../../ui";
import "./events.css";

function fmtArgs(raw: unknown): string {
  if (raw == null || raw === "") return "";
  if (typeof raw === "string") return raw;
  try {
    return JSON.stringify(raw, null, 2);
  } catch {
    return String(raw);
  }
}

/** 运行中的实时计时器；结束后定格在 durationMs */
function Elapsed({ startedAt, durationMs }: { startedAt: number; durationMs?: number }) {
  const [now, setNow] = useState(Date.now());
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (durationMs != null) return;
    timer.current = window.setInterval(() => setNow(Date.now()), 100);
    return () => {
      if (timer.current != null) window.clearInterval(timer.current);
    };
  }, [durationMs]);

  const ms = durationMs ?? now - startedAt;
  return <span className="ev-dur">{(ms / 1000).toFixed(1)}s</span>;
}

export function ToolEvent({ ev }: { ev: Ev; onViewEvidence?: (id?: string) => void }) {
  const name = String(ev.tool_name || ev.name || "tool");
  const running = ev.type === "tool_call_start";
  const failed = Boolean(ev.error) || String(ev.status || "") === "failed";
  const hostile = String(ev.source_trust || "") === "hostile";
  const summary = typeof ev.summary === "string" ? ev.summary : "";
  const args = fmtArgs(ev.args ?? ev.arguments);
  const startedAt =
    typeof ev.started_at === "number" ? ev.started_at * 1000 : Date.now();
  const durationMs =
    typeof ev.duration_ms === "number"
      ? ev.duration_ms
      : running
        ? undefined
        : 0;

  return (
    <Card tone={failed ? "danger" : running ? "info" : "default"} className="ev2">
      <div className="ev2-head">
        <span className="ev2-kind">工具</span>
        <code className="ev2-name">{name}</code>
        <Elapsed startedAt={startedAt} durationMs={durationMs} />
        {hostile ? (
          <Tooltip content="外部来源内容，默认不可信；作为结论依据时须标注可溯源（INV-39）">
            <span className="ev2-hostile">外部来源</span>
          </Tooltip>
        ) : null}
      </div>

      {failed ? (
        <div className="ev2-fail">
          <span className="ev2-fail-kind">
            {String(ev.error_type || "执行失败")}
          </span>
          <span className="ev2-fail-msg">{String(ev.error || "")}</span>
          {ev.retryable === true ? (
            <span className="ev2-fail-retry">可重试</span>
          ) : null}
        </div>
      ) : summary ? (
        <p className="ev2-summary">→ {summary}</p>
      ) : null}

      {args ? (
        <Disclosure summary="参数">
          <pre className="ev2-pre">{args}</pre>
        </Disclosure>
      ) : null}
    </Card>
  );
}
```

- [ ] **Step 2: 实现计划卡**

Create `apps/desktop/renderer/components/investigation/events/PlanEvent.tsx`：

```tsx
import type { Ev } from "../../../lib/types";
import { Card } from "../../../ui";
import "./events.css";

export function PlanEvent({ ev }: { ev: Ev; onViewEvidence?: (id?: string) => void }) {
  const t = ev.type;
  const plan = (ev.plan || {}) as { summary?: string; steps?: string[] };
  const steps = Array.isArray(plan.steps) ? plan.steps : [];

  const decided =
    t === "plan_approved" ||
    t === "plan_rejected" ||
    t === "privilege_decided";
  const rejected =
    t === "plan_rejected" ||
    (t === "privilege_decided" && String(ev.status || "") !== "approved");

  const label =
    t === "plan_ready"
      ? "计划"
      : t === "privilege_required"
        ? "提权申请"
        : rejected
          ? "计划 · 已拒绝"
          : "计划 · 已批准";

  return (
    <Card tone={rejected ? "danger" : decided ? "ok" : "plan"} className="ev2">
      <div className="ev2-head">
        <span className="ev2-kind">{label}</span>
        {/* approval_type 必须原样展示：standalone 的 self 不得与职责分离审批混同（INV-38） */}
        {ev.approval_type ? (
          <span className="ev2-approval">
            approval_type: {String(ev.approval_type)}
          </span>
        ) : null}
      </div>

      {plan.summary ? <p className="ev2-summary">{plan.summary}</p> : null}

      {steps.length > 0 ? (
        <ol className="ev2-steps">
          {steps.map((s, i) => (
            <li key={i} className="ev2-step">
              <span className="ev2-step-n">{i + 1}</span>
              <span className="ev2-step-t">{s}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </Card>
  );
}
```

- [ ] **Step 3: 实现消息卡与流式卡**

Create `apps/desktop/renderer/components/investigation/events/MessageEvent.tsx`：

```tsx
import type { Ev } from "../../../lib/types";
import { Markdown } from "../../Markdown";
import { Button, Card } from "../../../ui";
import "./events.css";

export function MessageEvent({
  ev,
  onViewEvidence,
}: {
  ev: Ev;
  onViewEvidence?: (id?: string) => void;
}) {
  if (ev.type === "user_task") {
    return (
      <div className="ev2-user">
        <span className="ev2-user-label">我</span>
        <p className="ev2-user-text">{String(ev.task || "")}</p>
      </div>
    );
  }

  if (ev.type === "evidence_register" || ev.type === "evidence_registered") {
    const id = typeof ev.evidence_id === "string" ? ev.evidence_id : undefined;
    return (
      <Card tone="info" className="ev2">
        <div className="ev2-head">
          <span className="ev2-kind">证据</span>
          <code className="ev2-name">{String(ev.name || id || "—")}</code>
        </div>
        {typeof ev.sha256 === "string" ? (
          <p className="ev2-hash">sha256 {ev.sha256.slice(0, 16)}…</p>
        ) : null}
        {onViewEvidence ? (
          <Button size="sm" variant="ghost" onClick={() => onViewEvidence(id)}>
            在证据库中查看
          </Button>
        ) : null}
      </Card>
    );
  }

  if (ev.type === "error") {
    return (
      <Card tone="danger" className="ev2">
        <div className="ev2-head">
          <span className="ev2-kind">错误</span>
        </div>
        <p className="ev2-summary">{String(ev.error || "未知错误")}</p>
      </Card>
    );
  }

  // answer_ready：报告正文，用 Markdown 排版
  const text =
    (typeof ev.text === "string" && ev.text) ||
    (typeof ev.candidate_text === "string" && ev.candidate_text) ||
    "";
  return (
    <Card tone="default" className="ev2 ev2--report">
      <div className="ev2-head">
        <span className="ev2-kind">报告</span>
      </div>
      <Markdown text={text} />
    </Card>
  );
}
```

Create `apps/desktop/renderer/components/investigation/events/StreamEvent.tsx`：

```tsx
import { useStream } from "../../../state";
import { Markdown } from "../../Markdown";
import { Card } from "../../../ui";
import "./events.css";

/** 唯一消费流式 context 的组件 —— 高频重渲染被隔离在这里 */
export function StreamEvent() {
  const { streamText, streaming } = useStream();
  if (!streaming && !streamText) return null;

  return (
    <Card tone="info" className="ev2 ev2--report">
      <div className="ev2-head">
        <span className="ev2-kind">{streaming ? "生成中" : "草稿"}</span>
        {streaming ? (
          <span className="ev2-cursor" aria-hidden>
            ▍
          </span>
        ) : null}
      </div>
      {streamText ? <Markdown text={streamText} /> : <SkeletonLines />}
    </Card>
  );
}

/** 首包之前的三条脉冲骨架 */
export function SkeletonLines() {
  return (
    <div className="ev2-skeleton" aria-label="等待模型首包">
      <span className="ev2-skel-line" />
      <span className="ev2-skel-line" />
      <span className="ev2-skel-line" />
    </div>
  );
}
```

- [ ] **Step 4: 实现分类器与 Timeline**

Create `apps/desktop/renderer/components/investigation/events/index.tsx`：

```tsx
import type { Ev } from "../../../lib/types";

export type EventKind = "tool" | "plan" | "message" | "system";

const TOOL = new Set(["tool_call_start", "tool_call_end"]);
const PLAN = new Set([
  "plan_ready",
  "plan_approved",
  "plan_rejected",
  "privilege_required",
  "privilege_decided",
]);
const MESSAGE = new Set([
  "user_task",
  "answer_ready",
  "error",
  "evidence_register",
  "evidence_registered",
]);

export function classify(ev: Ev): EventKind {
  if (TOOL.has(ev.type)) return "tool";
  if (PLAN.has(ev.type)) return "plan";
  if (MESSAGE.has(ev.type)) return "message";
  return "system";
}

export { MessageEvent } from "./MessageEvent";
export { PlanEvent } from "./PlanEvent";
export { SkeletonLines, StreamEvent } from "./StreamEvent";
export { ToolEvent } from "./ToolEvent";
```

Create `apps/desktop/renderer/components/investigation/Timeline.tsx`：

```tsx
import { useEffect, useRef } from "react";
import { useRun, useStream } from "../../state";
import {
  classify,
  MessageEvent,
  PlanEvent,
  SkeletonLines,
  StreamEvent,
  ToolEvent,
} from "./events";
import "./Timeline.css";

const SYSTEM_LABEL: Record<string, string> = {
  start: "会话开始",
  run_started: "运行开始",
  run_paused: "已暂停",
  run_resumed: "已恢复",
  episodic_recall: "召回经验",
  episodic_recorded: "已写入经验库",
  auth_bounds_check: "授权边界校验",
  policy_event: "策略事件",
  token_done: "流式完成",
};

export function Timeline({
  onViewEvidence,
}: {
  onViewEvidence: (evidenceId?: string) => void;
}) {
  const { events, status } = useRun();
  const { streaming, streamText } = useStream();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length, streamText]);

  // 已提交但首包未到：显示骨架
  const awaitingFirstToken =
    status === "running" && !streaming && !streamText && events.length <= 1;

  return (
    <div className="timeline2">
      {events.map((ev, i) => {
        const kind = classify(ev);
        const key = `${i}-${ev.type}`;
        if (kind === "tool")
          return <ToolEvent key={key} ev={ev} onViewEvidence={onViewEvidence} />;
        if (kind === "plan")
          return <PlanEvent key={key} ev={ev} onViewEvidence={onViewEvidence} />;
        if (kind === "message")
          return (
            <MessageEvent key={key} ev={ev} onViewEvidence={onViewEvidence} />
          );
        return (
          <p key={key} className="timeline2-system">
            {SYSTEM_LABEL[ev.type] || ev.type}
          </p>
        );
      })}

      {awaitingFirstToken ? <SkeletonLines /> : <StreamEvent />}
      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 5: 写事件卡样式**

Create `apps/desktop/renderer/components/investigation/events/events.css`：

```css
.ev2 { animation: ev2-enter var(--motion-base) var(--ease-out); }

@keyframes ev2-enter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

.ev2-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}

.ev2-kind {
  font-size: var(--text-2xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.ev2-name {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text);
}

.ev2-dur {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  font-variant-numeric: tabular-nums;
  color: var(--text-faint);
}

/* 外部来源标注 —— INV-39 */
.ev2-hostile {
  font-size: var(--text-2xs);
  color: var(--warn);
  border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent);
  border-radius: 999px;
  padding: 0 var(--sp-2);
  cursor: help;
}

.ev2-approval {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--text-faint);
}

.ev2-summary {
  margin: 0;
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--text-muted);
}

/* 结构化失败：类型 + 消息 + 可重试，不是一行红字 */
.ev2-fail { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--sp-2); }
.ev2-fail-kind { font-size: var(--text-xs); font-weight: 600; color: var(--danger); }
.ev2-fail-msg { font-size: var(--text-sm); color: var(--text-muted); }
.ev2-fail-retry {
  font-size: var(--text-2xs);
  color: var(--info);
  border: 1px solid color-mix(in srgb, var(--info) 40%, transparent);
  border-radius: 999px;
  padding: 0 var(--sp-2);
}

.ev2-pre {
  margin: 0;
  padding: var(--sp-3);
  background: var(--layer-1);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  line-height: var(--leading-normal);
  color: var(--text-muted);
  overflow-x: auto;
}

.ev2-steps { list-style: none; margin: var(--sp-2) 0 0; padding: 0; display: flex; flex-direction: column; gap: var(--sp-2); }
.ev2-step { display: flex; align-items: baseline; gap: var(--sp-3); font-size: var(--text-sm); color: var(--text); }
.ev2-step-n {
  flex: none;
  width: 18px; height: 18px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--plan-muted);
  color: var(--plan);
  font-size: var(--text-2xs);
  font-weight: 600;
}

.ev2-user { display: flex; gap: var(--sp-3); padding: var(--sp-2) 0; }
.ev2-user-label {
  flex: none;
  font-size: var(--text-2xs);
  font-weight: 600;
  color: var(--text-faint);
  padding-top: 3px;
}
.ev2-user-text {
  margin: 0;
  font-size: var(--text-md);
  line-height: var(--leading-relaxed);
  color: var(--text);
}

.ev2--report { line-height: var(--leading-relaxed); }
.ev2-hash { margin: 0; font-family: var(--font-mono); font-size: var(--text-2xs); color: var(--text-faint); }

.ev2-cursor { color: var(--info); animation: ev2-blink 1s steps(2) infinite; }
@keyframes ev2-blink { 50% { opacity: 0; } }

.ev2-skeleton { display: flex; flex-direction: column; gap: var(--sp-2); padding: var(--sp-2) 0; }
.ev2-skel-line {
  height: 10px;
  border-radius: 999px;
  background: var(--layer-2);
  animation: ev2-pulse 2s var(--ease-out) infinite;
}
.ev2-skel-line:nth-child(1) { width: 62%; }
.ev2-skel-line:nth-child(2) { width: 88%; animation-delay: 160ms; }
.ev2-skel-line:nth-child(3) { width: 44%; animation-delay: 320ms; }

@keyframes ev2-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

@media (prefers-reduced-motion: reduce) {
  .ev2 { animation: none; }
  .ev2-cursor, .ev2-skel-line { animation: none; }
}
```

Create `apps/desktop/renderer/components/investigation/Timeline.css`：

```css
.timeline2 {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-5);
}

.timeline2-system {
  margin: 0;
  font-size: var(--text-2xs);
  color: var(--text-faint);
  padding-left: var(--sp-2);
}
```

- [ ] **Step 6: 接进 WorkbenchView 并删除旧 EventCard**

在 `apps/desktop/renderer/views/WorkbenchView.tsx` 的 `.wb-main` 中填入：

```tsx
<div className="wb-timeline">
  <Timeline onViewEvidence={props.onViewEvidence} />
</div>
```

加 `import { Timeline } from "../components/investigation/Timeline";`。

在 `WorkbenchLayout.css` 追加：

```css
.wb-timeline {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
```

然后：

```bash
cd apps/desktop
git rm renderer/components/EventCard.tsx
grep -rn "EventCard" renderer/ || echo "无残留引用"
```
Expected: 输出「无残留引用」

- [ ] **Step 7: 跑测试、typecheck 与目视验证**

```bash
cd apps/desktop && npm test && npm run typecheck && npm run dev:renderer
```

- [ ] **Step 8: 提交**

```bash
git add -A apps/desktop/renderer/components apps/desktop/renderer/views/WorkbenchView.tsx
git commit -m "feat(desktop-ui): 时间线按事件类型拆四类卡片，保留 INV-39 外部来源标注"
```

---

### Task 15: Composer + 运行反馈 + 计划面板

**Files:**
- Create: `apps/desktop/renderer/components/investigation/Composer.tsx` `Composer.css`
- Create: `apps/desktop/renderer/components/investigation/InvestigationHeader.tsx` `InvestigationHeader.css`
- Create: `apps/desktop/renderer/components/investigation/PlanPanel.tsx` `PlanPanel.css`
- Modify: `apps/desktop/renderer/views/WorkbenchView.tsx`
- Modify: `apps/desktop/renderer/App.tsx`
- Delete: `apps/desktop/renderer/components/PlanPanel.tsx`（旧版）
- Delete: `apps/desktop/renderer/components/EmptyState.tsx`（示例任务已迁入 `SessionRail`）
- Delete: `apps/desktop/renderer/components/SessionList.tsx`（已由 `SessionRail` 取代）

**Interfaces:**
- Consumes: `useRun()` / `usePlan()` / primitives
- Produces:
  - `Composer`: 无 props，内部 `useRun()`
  - `InvestigationHeader`: `props { title: string }`，内部 `useRun()` 取运行态与进度条
  - `PlanPanel`: 无 props，内部 `usePlan()`

- [ ] **Step 1: 实现 InvestigationHeader（含 2px 不确定态进度条）**

Create `apps/desktop/renderer/components/investigation/InvestigationHeader.tsx`：

```tsx
import { useRun } from "../../state";
import { StatusDot } from "../../ui";
import "./InvestigationHeader.css";

const STATUS_TEXT: Record<string, string> = {
  idle: "空闲",
  running: "运行中",
  paused: "已暂停",
  done: "已完成",
  failed: "失败",
};

export function InvestigationHeader({ title }: { title: string }) {
  const { status, running, resume, paused, pausedRunId } = useRun();

  return (
    <header className="invhead">
      <div className="invhead-row">
        <h1 className="invhead-title">{title}</h1>
        <span className="invhead-status">
          <StatusDot
            level={
              status === "running"
                ? "info"
                : status === "failed"
                  ? "danger"
                  : status === "paused"
                    ? "warn"
                    : status === "done"
                      ? "ok"
                      : "idle"
            }
            pulse={running}
            label={STATUS_TEXT[status] || status}
          />
        </span>
      </div>

      {paused ? (
        <div className="invhead-paused">
          <span>
            已暂停{pausedRunId ? ` · ${pausedRunId.slice(0, 8)}` : ""}
          </span>
          <button type="button" className="invhead-resume" onClick={() => void resume()}>
            继续
          </button>
        </div>
      ) : null}

      <div className={`invhead-bar${running ? " is-active" : ""}`} aria-hidden />
    </header>
  );
}
```

Create `apps/desktop/renderer/components/investigation/InvestigationHeader.css`：

```css
.invhead { flex: none; position: relative; }

.invhead-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-5) var(--sp-3);
}

.invhead-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  line-height: var(--leading-tight);
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.invhead-status { flex: none; }

.invhead-paused {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  margin: 0 var(--sp-5) var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  background: var(--warn-muted);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--warn);
}

.invhead-resume {
  background: var(--warn);
  color: var(--text-inverse);
  border: none;
  border-radius: var(--radius-sm);
  padding: 2px var(--sp-3);
  font-family: var(--font-ui);
  font-size: var(--text-2xs);
  font-weight: 600;
  cursor: pointer;
}

/* 2px 不确定态进度条 —— 比状态胶囊有存在感 */
.invhead-bar { height: 2px; background: transparent; overflow: hidden; }

.invhead-bar.is-active::after {
  content: "";
  display: block;
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, transparent, var(--info), transparent);
  animation: invhead-slide 1.4s var(--ease-out) infinite;
}

@keyframes invhead-slide {
  from { transform: translateX(-100%); }
  to { transform: translateX(350%); }
}

@media (prefers-reduced-motion: reduce) {
  .invhead-bar.is-active::after { animation: none; width: 100%; opacity: 0.5; }
}
```

- [ ] **Step 2: 实现 Composer**

Create `apps/desktop/renderer/components/investigation/Composer.tsx`：

```tsx
import { useState } from "react";
import { useRun } from "../../state";
import type { Tier } from "../../lib/types";
import { Button, Select } from "../../ui";
import "./Composer.css";

const TIER_OPTIONS: Array<{ value: Tier; label: string }> = [
  { value: "readonly", label: "只读" },
  { value: "full", label: "完整" },
];

export function Composer() {
  const {
    task,
    setTask,
    tier,
    setTier,
    run,
    abort,
    steer,
    steerText,
    setSteerText,
    running,
    runId,
  } = useRun();
  const [showSteer, setShowSteer] = useState(false);

  const hasApi = typeof window !== "undefined" && Boolean(window.cyberguard);

  return (
    <div className="composer2">
      <textarea
        className="composer2-input"
        value={task}
        onChange={(e) => setTask(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            void run();
          }
        }}
        placeholder="描述任务… 例如：分诊 high/critical 告警，给出优先级与建议动作"
        disabled={running}
        rows={3}
      />

      <div className="composer2-bar">
        <Select
          value={tier}
          onChange={setTier}
          options={TIER_OPTIONS}
          ariaLabel="能力档位"
          size="sm"
          disabled={running}
        />
        <Button
          variant="primary"
          size="sm"
          onClick={() => void run()}
          disabled={!hasApi || running || !task.trim()}
        >
          {running ? "运行中…" : "运行"}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void abort()}
          disabled={!running || !runId}
        >
          中止
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowSteer((v) => !v)}
          disabled={!running || !runId}
        >
          中途补充
        </Button>
        <span className="composer2-hint">⌘↵ 运行</span>
      </div>

      {showSteer ? (
        <div className="composer2-steer">
          <input
            className="composer2-steerinput"
            value={steerText}
            onChange={(e) => setSteerText(e.target.value)}
            placeholder="运行中途补充说明…"
            disabled={!running || !runId}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void steer()}
            disabled={!running || !runId || !steerText.trim()}
          >
            发送
          </Button>
        </div>
      ) : null}
    </div>
  );
}
```

Create `apps/desktop/renderer/components/investigation/Composer.css`：

```css
.composer2 {
  flex: none;
  border-top: 1px solid var(--border-0);
  padding: var(--sp-4) var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.composer2-input {
  width: 100%;
  resize: vertical;
  background: var(--layer-2);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-md);
  padding: var(--sp-3) var(--sp-4);
  font-family: var(--font-ui);
  font-size: var(--text-base);
  line-height: var(--leading-relaxed);
  color: var(--text);
  transition: border-color var(--motion-fast) var(--ease-out);
}

.composer2-input::placeholder { color: var(--text-faint); }

.composer2-input:focus {
  outline: none;
  border-color: var(--accent);
}

.composer2-input:disabled { opacity: 0.6; cursor: not-allowed; }

.composer2-bar { display: flex; align-items: center; gap: var(--sp-2); }

.composer2-hint {
  margin-left: auto;
  font-size: var(--text-2xs);
  color: var(--text-faint);
}

.composer2-steer { display: flex; align-items: center; gap: var(--sp-2); }

.composer2-steerinput {
  flex: 1;
  height: 26px;
  background: var(--layer-2);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  padding: 0 var(--sp-3);
  font-family: var(--font-ui);
  font-size: var(--text-xs);
  color: var(--text);
}

.composer2-steerinput:focus { outline: none; border-color: var(--accent); }

@media (prefers-reduced-motion: reduce) {
  .composer2-input { transition: none; }
}
```

- [ ] **Step 3: 实现新 PlanPanel**

Create `apps/desktop/renderer/components/investigation/PlanPanel.tsx`：

```tsx
import { usePlan } from "../../state";
import { Button } from "../../ui";
import "./PlanPanel.css";

export function PlanPanel() {
  const { pendingPlan, planEdit, setPlanEdit, approve, reject } = usePlan();
  if (!pendingPlan) return null;

  const steps = pendingPlan.plan?.steps || [];
  const localOnly = pendingPlan.approval_type === "self";

  return (
    <div className="planpanel" role="dialog" aria-label="计划审阅">
      <div className="planpanel-head">
        <span className="planpanel-label">{pendingPlan.ui_label || "计划待批"}</span>
        {/* 本地确认 ≠ 职责分离审批，必须显式标注（INV-38） */}
        {localOnly ? (
          <span className="planpanel-self">approval_type: self · 本地自批准</span>
        ) : null}
        {pendingPlan.timeout_seconds ? (
          <span className="planpanel-timeout">
            超时 {pendingPlan.timeout_seconds}s = 拒绝
          </span>
        ) : null}
      </div>

      <textarea
        className="planpanel-edit"
        value={planEdit}
        onChange={(e) => setPlanEdit(e.target.value)}
        rows={3}
        aria-label="计划摘要（可修改）"
      />

      {steps.length > 0 ? (
        <ol className="planpanel-steps">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      ) : null}

      <div className="planpanel-actions">
        <Button
          variant="primary"
          size="sm"
          onClick={() => void approve()}
          disabled={pendingPlan.local_approve_allowed === false}
        >
          批准
        </Button>
        <Button variant="danger" size="sm" onClick={() => void reject()}>
          拒绝
        </Button>
      </div>
    </div>
  );
}
```

Create `apps/desktop/renderer/components/investigation/PlanPanel.css`：

```css
.planpanel {
  flex: none;
  margin: 0 var(--sp-5) var(--sp-3);
  padding: var(--sp-4);
  background: var(--layer-2);
  border: 1px solid color-mix(in srgb, var(--plan) 40%, transparent);
  border-left: 2px solid var(--plan);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.planpanel-head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); }

.planpanel-label { font-size: var(--text-xs); font-weight: 600; color: var(--plan); }

.planpanel-self,
.planpanel-timeout {
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--warn);
}

.planpanel-edit {
  width: 100%;
  resize: vertical;
  background: var(--layer-1);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  padding: var(--sp-2) var(--sp-3);
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--text);
}

.planpanel-edit:focus { outline: none; border-color: var(--plan); }

.planpanel-steps {
  margin: 0;
  padding-left: var(--sp-5);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--text-muted);
}

.planpanel-actions { display: flex; gap: var(--sp-2); }
```

- [ ] **Step 4: 组装 WorkbenchView 并清理旧组件**

`apps/desktop/renderer/views/WorkbenchView.tsx` 最终形态：

```tsx
import "../components/workbench/WorkbenchLayout.css";
import { ContextRail } from "../components/context/ContextRail";
import { Composer } from "../components/investigation/Composer";
import { InvestigationHeader } from "../components/investigation/InvestigationHeader";
import { PlanPanel } from "../components/investigation/PlanPanel";
import { Timeline } from "../components/investigation/Timeline";
import { SessionRail } from "../components/session/SessionRail";
import type { SettingsSection } from "../lib/types";
import { useRun, useSessions } from "../state";

export type WorkbenchViewProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (section?: SettingsSection) => void;
};

export function WorkbenchView(props: WorkbenchViewProps) {
  const { sessions, sessionId } = useSessions();
  const { lastSubmitted } = useRun();

  const current = sessions.find((s) => s.session_id === sessionId);
  const title = current?.title || lastSubmitted || "新调查";

  return (
    <div className="wb">
      <SessionRail />
      <div className="wb-main">
        <InvestigationHeader title={title} />
        <PlanPanel />
        <div className="wb-timeline">
          <Timeline onViewEvidence={props.onViewEvidence} />
        </div>
        <Composer />
      </div>
      <ContextRail
        onViewEvidence={props.onViewEvidence}
        onOpenSettings={props.onOpenSettings}
      />
    </div>
  );
}
```

在 `App.tsx` 中删除旧 `PlanPanel` 的 import 与其 JSX 块（计划面板已归属 Workbench 内部）。

```bash
cd apps/desktop
git rm renderer/components/PlanPanel.tsx renderer/components/EmptyState.tsx renderer/components/SessionList.tsx
grep -rn "components/PlanPanel\|components/EmptyState\|components/SessionList" renderer/ || echo "无残留引用"
```
Expected: 输出「无残留引用」

- [ ] **Step 5: 跑测试、typecheck 与目视验证**

```bash
cd apps/desktop && npm test && npm run typecheck && npm run dev:renderer
```

目视确认：档位是自绘下拉不是原生控件；运行时顶部有 2px 流动进度条；深浅主题正常。

- [ ] **Step 6: 提交**

```bash
git add -A apps/desktop/renderer
git commit -m "feat(desktop-ui): Composer/调查头/计划面板重做，运行反馈与进度条到位"
```

---

### Task 16: 收尾 —— CSS 清理、reduced-motion 兜底、出口判据核对

**Files:**
- Modify: `apps/desktop/renderer/styles.css`
- Modify: `apps/desktop/renderer/styles/views.css`
- Modify: `apps/desktop/renderer/styles/motion.css`
- Modify: `apps/desktop/renderer/hooks/useDesktopRuntime.ts`（删除）
- Test: `apps/desktop/renderer/__tests__/styles/legacy.test.ts`

- [ ] **Step 1: 删除已无引用的 useDesktopRuntime**

```bash
cd apps/desktop
grep -rn "useDesktopRuntime" renderer/ || echo "无残留引用"
git rm renderer/hooks/useDesktopRuntime.ts
```
Expected: 先输出「无残留引用」，再删除成功

- [ ] **Step 2: 写遗留 CSS 守卫测试（先失败）**

Create `apps/desktop/renderer/__tests__/styles/legacy.test.ts`：

```ts
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
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd apps/desktop && npm test -- legacy`
Expected: FAIL，多个旧选择器仍存在

- [ ] **Step 4: 清理遗留 CSS**

从 `renderer/styles.css` 与 `renderer/styles/views.css` 中删除上述 Workbench 相关规则块。

**保留**：Settings 与 Evidence 仍在用的规则（`.settings-*`、`.evidence-*`、`.banner`、`.pill`、`.kv`、`.mono-xs`、`.row`、通用表单样式等）。

判断方法：对每个待删选择器执行

```bash
cd apps/desktop && grep -rn "className=.*<选择器名>" renderer/views renderer/components
```

无命中才删。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd apps/desktop && npm test -- legacy`
Expected: PASS

- [ ] **Step 6: 补全局 reduced-motion 兜底**

在 `renderer/styles/motion.css` 末尾追加：

```css
/* 全局兜底：任何遗漏的动画在 reduce 下一律关闭 */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 7: 逐条核对出口判据**

对照 spec §11，逐条确认：

```bash
cd apps/desktop

# 判据 1：WorkbenchView props = 0（只剩两个导航回调）；无 hook 超 150 行
grep -c "" renderer/state/*.tsx renderer/state/*.ts

# 判据 4：Workbench 规则清零
npm test -- legacy

# 判据 5：无原生 select
grep -rn "<select" renderer/views/WorkbenchView.tsx renderer/components/investigation/ || echo "无原生 select"

# 判据 6：测试与 typecheck
npm test && npm run typecheck

# 判据 8：Python 桌面测试
cd ../.. && PYTHONPATH="packages:$(pwd)" .venv/bin/python -m pytest -q tests/test_desktop_*.py
```

**判据 2 / 3 / 7 / 9 为人工目视核对**，在 `npm run dev:renderer` 下逐条确认：

- 判据 2：顶部常驻 ≤ 48px，无异常时无第二条横带
- 判据 3：状态栏六项常显不可折叠；在浏览器 devtools 中把 `sandboxImpl` 改为 `none` 后确认转 danger 且顶部浮出
- 判据 7：系统偏好设置开启「减弱动态效果」后，进入动效与脉冲全部停止
- 判据 9：深浅双主题下 Workbench 均无破版；Settings / Evidence 不破版

- [ ] **Step 8: 提交**

```bash
git add -A apps/desktop
git commit -m "chore(desktop-ui): 清理遗留 Workbench 样式与 god hook，补 reduced-motion 兜底"
```

---

## 自查记录

**Spec 覆盖核对**（spec 章节 → 落地 Task）：

| Spec 章节 | Task |
|---|---|
| §2.1 本轮范围 | Global Constraints + 各 Task 范围声明 |
| §3.1 三栏布局 | Task 12 |
| §3.2 关键决策（顶部压缩 / 层级差 / 左栏空态 / 拆三按钮） | Task 12、13 |
| §3.3 状态栏六项常显 | Task 13 |
| §4.1–4.3 字阶 / 间距阶 / 层级阶 | Task 2 |
| §4.4 色彩职责拆分 | Task 2（token）+ Task 12（nav 选中用 accent） |
| §4.5 文件组织 | Task 3–5（`ui/`）、Task 16（清理） |
| §5 primitives 十个 | Task 3、4、5 |
| §6.1 导出/卸载迁出 | Task 11 |
| §6.2 六个域拆分 | Task 6–9、11（`useDataLifecycle`）、10（组合） |
| §6.3 组件边界 | Task 12–15 |
| §7.1 运行生命周期反馈 | Task 14（骨架、计时器）+ Task 15（进度条、乐观渲染） |
| §7.2 动效三类 | Task 14、15 + Task 16 兜底 |
| §7.3 错误与降级呈现 | Task 9（派生）+ Task 12（浮出条）+ Task 14（结构化失败卡） |
| §7.4 键盘 | 沿用现有 `useHotkeys`；Esc 已在 `App.tsx` 实现 |
| §7.5 就地反馈（不做 toast） | Task 11（导出结果行内）+ Task 15 |
| §8 测试策略 | Task 1、2、3、4、6、7、9、16 |
| §9 新依赖五个 | Task 1（三个）+ Task 4（两个） |
| §10 不变量对照 | Task 9（INV-16/38 派生）、12（浮出条）、13（INV-36 常显）、14（INV-39 标注）、15（INV-38 self 标注） |
| §11 出口判据 | Task 16 Step 7 |

**已知偏差**：spec §7.4 提到「↑↓ 在会话列表移动」，本计划未单列步骤 —— `SessionRail` 用原生 `<button>` 列表，Tab 键可达；方向键导航若确需，作为后续小改动处理，不阻塞出口判据。

**类型一致性**：`RunStatus` 枚举在 Task 6 定义，Task 13（`StatusBar`）、14（`Timeline`）、15（`InvestigationHeader`）消费；`Degradation` 在 Task 9 定义，Task 12（`DegradationStrip`）消费；primitives 的 props 签名在 Task 3–5 的 Interfaces 块给出，Task 12–15 按此调用。

