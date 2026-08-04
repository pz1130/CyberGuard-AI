# Desktop App Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a complete, silky macOS desktop UI (dark-default dual theme): Workbench + Settings + Evidence, with full LLM/MCP GUI configuration on the existing Electron renderer (approach A).

**Architecture:** Split the monolithic `App.tsx` into Shell + views + components; CSS design tokens for dark/light; thin sidecar RPC for provider/mcp config/prefs; no ui-shared extraction, no Web 21-tab clone.

**Tech Stack:** Electron 33, React 19, Vite 6, TypeScript, plain CSS (tokens), Python sidecar JSONL RPC, pytest for new RPC.

**Spec:** `docs/superpowers/specs/2026-08-04-desktop-app-frontend-design.md`

## Global Constraints

- Platform: macOS first; Electron + React renderer only.
- No listen ports; all data via `window.cyberguard` → JSONL sidecar.
- API keys / MCP secrets: Keychain only; never log plaintext; UI shows has_key only.
- Default theme: **dark**; light and system supported.
- INV-38: development banner + 自批准 labeling required.
- INV-06: Plan timeout = reject; connected hides local approve (existing behavior).
- Do not introduce Tailwind, new UI frameworks, or `packages/ui-shared` in this plan.
- Do not add Web-style Agents/Governance/Users tabs.
- Every wave must keep existing desktop pytest green: `pytest -q tests/test_desktop_*.py`.
- After Electron overwrite: `cd apps/desktop && npm run codesign:dev` (dev only).

## File map

| Path | Responsibility |
|------|----------------|
| `apps/desktop/renderer/styles/tokens.css` | Dark/light CSS variables |
| `apps/desktop/renderer/styles/base.css` | Reset, typography, layout primitives |
| `apps/desktop/renderer/styles/motion.css` | Transitions |
| `apps/desktop/renderer/styles/views.css` | Workbench/Evidence/Settings layouts |
| `apps/desktop/renderer/lib/types.ts` | Shared TS types (Ev, Tier, Caps, …) |
| `apps/desktop/renderer/lib/ipc.ts` | Typed `window.cyberguard` wrappers |
| `apps/desktop/renderer/hooks/useTheme.ts` | Theme state + localStorage/prefs |
| `apps/desktop/renderer/hooks/useSidecar.ts` | ping, live events subscription |
| `apps/desktop/renderer/components/*` | StatusBar, Button, Panel, Markdown, EventCard, PlanPanel, SessionList, EmptyState |
| `apps/desktop/renderer/views/WorkbenchView.tsx` | Three-column workbench |
| `apps/desktop/renderer/views/EvidenceView.tsx` | Evidence library page |
| `apps/desktop/renderer/views/SettingsView.tsx` | Settings groups |
| `apps/desktop/renderer/App.tsx` | Shell only (≤~300 lines) |
| `apps/desktop/electron/preload.cjs` | Expose new IPC methods |
| `apps/desktop/electron/main.cjs` | dialog + rpc passthrough for provider/mcp/prefs |
| `apps/desktop/sidecar/main.py` | RPC handlers for provider/mcp.config/ui.prefs |
| `apps/desktop/sidecar/provider.py` | set/get/test helpers if needed |
| `apps/desktop/sidecar/mcp_config.py` | load/save config file |
| `tests/test_desktop_provider_mcp_config.py` | RPC contract tests |
| `tests/test_desktop_ui_theme.py` | Optional pure theme resolve tests (if extracted) |

---

## Wave P0 — Shell + visual migration

### Task 1: Design tokens + base/motion CSS

**Files:**
- Create: `apps/desktop/renderer/styles/tokens.css`
- Create: `apps/desktop/renderer/styles/base.css`
- Create: `apps/desktop/renderer/styles/motion.css`
- Modify: `apps/desktop/renderer/main.tsx` (import styles)
- Modify or retire: `apps/desktop/renderer/styles.css` (re-export or delete after migration)

**Interfaces:**
- Produces: CSS variables listed in spec §2.3; `html[data-theme="dark"|"light"]`

- [ ] **Step 1: Add `tokens.css` with dark (default) and light maps**

```css
:root, html[data-theme="dark"] {
  --bg: #0a0c10;
  --bg-elevated: #12151c;
  --surface: rgba(22, 26, 36, 0.82);
  --surface-hover: rgba(32, 38, 52, 0.9);
  --border: rgba(120, 140, 180, 0.18);
  --border-subtle: rgba(120, 140, 180, 0.1);
  --text: #e8edf7;
  --text-muted: #8b95a8;
  --accent: #3ee0c5;
  --accent-muted: rgba(62, 224, 197, 0.15);
  --ok: #34d399;
  --warn: #fbbf24;
  --danger: #f87171;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --shadow-panel: 0 8px 32px rgba(0, 0, 0, 0.45);
  --motion-fast: 160ms;
  --motion-base: 240ms;
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --font-ui: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, monospace;
}
html[data-theme="light"] {
  --bg: #f4f5f8;
  --bg-elevated: #ffffff;
  --surface: rgba(255, 255, 255, 0.9);
  --surface-hover: #f0f2f6;
  --border: rgba(15, 23, 42, 0.12);
  --text: #0f172a;
  --text-muted: #64748b;
  --accent: #0d9488;
  /* ok/warn/danger slightly deeper for contrast */
  --shadow-panel: 0 8px 24px rgba(15, 23, 42, 0.08);
}
```

- [ ] **Step 2: Add `base.css` + `motion.css`**

`base.css`: `body { margin:0; font-family:var(--font-ui); background:var(--bg); color:var(--text); }`  
`motion.css`: `.view-enter { transition: opacity var(--motion-base) var(--ease-out), transform var(--motion-base) var(--ease-out); }`

- [ ] **Step 3: Wire imports in `main.tsx`**

```tsx
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/motion.css";
import "./styles/views.css"; // empty file ok until Task 3
```

- [ ] **Step 4: Manual check**

Run: `cd apps/desktop && npm run dev:signed`  
Expected: app still loads (may look half-styled until later tasks).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/renderer/styles apps/desktop/renderer/main.tsx
git commit -m "feat(desktop-ui): add design tokens and base motion CSS (P0)"
```

---

### Task 2: `lib/types.ts` + `lib/ipc.ts` + `useTheme`

**Files:**
- Create: `apps/desktop/renderer/lib/types.ts`
- Create: `apps/desktop/renderer/lib/ipc.ts`
- Create: `apps/desktop/renderer/hooks/useTheme.ts`

**Interfaces:**
- Produces: `getApi()`, typed methods matching current preload; `useTheme()` → `{ theme, setTheme, resolved }` where theme is `"dark"|"light"|"system"`

- [ ] **Step 1: Extract types from current `App.tsx` into `types.ts`**

Move `Tier`, `Caps`, `Ev`, `SessionRow`, `PendingPlan` without behavior change.

- [ ] **Step 2: Implement `ipc.ts`**

```ts
export function getApi() {
  return window.cyberguard;
}
export async function ping() {
  return getApi()?.ping();
}
// wrap existing methods only in P0; provider/mcp later
```

- [ ] **Step 3: Implement `useTheme`**

```ts
// resolve system via matchMedia('(prefers-color-scheme: dark)')
// apply document.documentElement.dataset.theme = resolved
// persist to localStorage key 'cg.theme' in P0; migrate to ui.prefs RPC in P1
```

- [ ] **Step 4: Unit-free smoke — import in App temporarily**

Ensure no TS errors: `cd apps/desktop && npm run typecheck`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(desktop-ui): typed ipc helpers and theme hook (P0)"
```

---

### Task 3: Shell App + StatusBar + view switch

**Files:**
- Create: `apps/desktop/renderer/components/StatusBar.tsx`
- Create: `apps/desktop/renderer/components/StatusPill.tsx`
- Create: `apps/desktop/renderer/components/Button.tsx`
- Create: `apps/desktop/renderer/styles/views.css`
- Rewrite: `apps/desktop/renderer/App.tsx` (shell only)

**Interfaces:**
- Consumes: `useTheme`, `getApi`, types
- Produces: `activeView` state; children slot for views

- [ ] **Step 1: Build StatusBar**

Props: `pingOk`, `sandboxImpl`, `sandboxMode`, `tccSummary`, `providerMode`, `tier`, `runStatus`, `evidenceHint`  
Use StatusPill with variants `ok|warn|danger|neutral` mapped per spec §2.5.

- [ ] **Step 2: Shell chrome**

Nav buttons: Workbench | Evidence | Settings; theme toggle (cycles dark→light→system or dark/light only in P0); development banner kept.

- [ ] **Step 3: Placeholder views**

```tsx
{activeView === "workbench" && <div className="placeholder">Workbench soon</div>}
{activeView === "evidence" && <div className="placeholder">Evidence soon</div>}
{activeView === "settings" && <div className="placeholder">Settings soon</div>}
```

Temporarily keep old workbench body still reachable OR next task migrates immediately — prefer Task 4 same PR if possible.

- [ ] **Step 4: typecheck + visual**

`npm run typecheck`  
Manual: switch views, switch theme, no flash of wrong theme on reload.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(desktop-ui): app shell navigation and status bar (P0)"
```

---

### Task 4: Migrate Workbench into `WorkbenchView` (no feature regression)

**Files:**
- Create: `apps/desktop/renderer/views/WorkbenchView.tsx`
- Create: `apps/desktop/renderer/components/EventCard.tsx` (move from App)
- Create: `apps/desktop/renderer/components/PlanPanel.tsx`
- Create: `apps/desktop/renderer/components/SessionList.tsx`
- Create: `apps/desktop/renderer/components/Markdown.tsx` (upgrade SimpleMarkdown)
- Create: `apps/desktop/renderer/components/EmptyState.tsx`
- Modify: `App.tsx` to render `<WorkbenchView … />`

**Interfaces:**
- Consumes: all existing run/session/plan handlers (pass as props or hooks)
- Produces: three-column layout per spec §3.2

- [ ] **Step 1: Move EventCard + PlanPanel + session list logic out of App.tsx without changing event handling**

- [ ] **Step 2: Layout CSS for `.workbench { display:grid; grid-template-columns: 240px 1fr 280px; }`**

Glass panels: `background: var(--surface); backdrop-filter: blur(12px); border: 1px solid var(--border); border-radius: var(--radius-lg);`

- [ ] **Step 3: Wire Run/Abort/Steer/tier exactly as before**

Regression: same RPC methods, same event types.

- [ ] **Step 4: EmptyState component**

Three CTAs: open Settings LLM, open Settings MCP, sample task text fill.

- [ ] **Step 5: Manual golden path smoke + desktop tests**

```bash
cd cyberguard
export PYTHONPATH="packages:."
.venv/bin/python -m pytest -q tests/test_desktop_sidecar.py tests/test_desktop_m4_plan_mode.py tests/test_desktop_m5_trust_evidence_pause.py
cd apps/desktop && npm run typecheck
```

Expected: pytest pass; UI can run a task with existing provider.json.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(desktop-ui): migrate workbench to three-column view (P0)"
```

---

### Task 5: P0 polish gate

**Files:** docs optional note in `apps/desktop/README.md` on theme + structure

- [ ] **Step 1: Delete dead CSS from old `styles.css` if fully superseded**

- [ ] **Step 2: Checklist**

- [ ] Dark default  
- [ ] Theme toggle works  
- [ ] Workbench three columns  
- [ ] Plan approve/reject still works  
- [ ] Status bar shows sandbox/tcc/llm  
- [ ] Development banner visible  

- [ ] **Step 3: Commit**

```bash
git commit -m "docs(desktop-ui): P0 complete — shell and workbench visual migration"
```

---

## Wave P1 — Settings GUI + provider/MCP RPC

### Task 6: Sidecar `ui.prefs` + `provider.get/set/test`

**Files:**
- Modify: `apps/desktop/sidecar/main.py` (RPC dispatch)
- Modify: `apps/desktop/sidecar/provider.py`
- Create: `apps/desktop/sidecar/ui_prefs.py` (optional small module)
- Test: `tests/test_desktop_provider_mcp_config.py`

**Interfaces:**
- Produces:
  - `ui.prefs.get` → `{ theme?: string, font_size?: string }`
  - `ui.prefs.set` → `{ ok: true, prefs: … }`
  - `provider.get` → public fields, **no api_key**
  - `provider.set` params: `{ mode, base_url, model, temperature?, api_key? }` — if api_key set, call secrets store and strip from file
  - `provider.test` → `{ ok: bool, error?: string, latency_ms?: number }`

- [ ] **Step 1: Write failing tests**

```python
def test_provider_get_never_returns_api_key(tmp_path, monkeypatch):
    # write provider.json with api_key, call provider.get via handle, assert "api_key" not in result
    ...

def test_provider_set_moves_key_to_secrets(tmp_path, monkeypatch):
    # set api_key via provider.set; file has no key; secrets has key
    ...
```

- [ ] **Step 2: Run tests — expect FAIL**

`pytest -q tests/test_desktop_provider_mcp_config.py -v`

- [ ] **Step 3: Implement handlers**

Reuse `load_provider_config`, `secrets.set_provider_key`, file write without key field.

- [ ] **Step 4: Tests PASS + commit**

```bash
git commit -m "feat(desktop): provider and ui.prefs RPC for settings GUI (P1)"
```

---

### Task 7: Sidecar `mcp.config.list/upsert/delete`

**Files:**
- Modify: `apps/desktop/sidecar/mcp_config.py`
- Modify: `apps/desktop/sidecar/main.py`
- Test: same test file

**Interfaces:**
- `mcp.config.list` → servers without secrets
- `mcp.config.upsert` body matches README schema + optional `secret` → `secrets.set_mcp`
- `mcp.config.delete` by id

- [ ] **Step 1: Failing tests for list omits secret env values; upsert persists json**

- [ ] **Step 2: Implement save with atomic write to `mcp_servers.json`**

- [ ] **Step 3: Tests pass + commit**

```bash
git commit -m "feat(desktop): mcp.config CRUD RPC (P1)"
```

---

### Task 8: Preload + main IPC for new methods + file dialogs

**Files:**
- Modify: `apps/desktop/electron/preload.cjs`
- Modify: `apps/desktop/electron/main.cjs`

- [ ] **Step 1: Expose** `providerGet/Set/Test`, `mcpConfigList/Upsert/Delete`, `prefsGet/Set`, `pickFile` (open dialog)

- [ ] **Step 2: main.cjs handlers call sidecar rpc** (same pattern as existing `sidecar:plan:approve`)

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(desktop): expose provider/mcp/prefs IPC in Electron (P1)"
```

---

### Task 9: SettingsView — LLM + MCP + Appearance + Data + About

**Files:**
- Create: `apps/desktop/renderer/views/SettingsView.tsx`
- Create: `apps/desktop/renderer/components/settings/*` if needed (LlmForm, McpEditor)
- Modify: `App.tsx` mount SettingsView
- Modify: `useTheme` to prefer `ui.prefs` when available

- [ ] **Step 1: LLM form UI** (mode, base_url, model, key password field, Save, Test)

Never display stored key; show badge "key configured" from `has_api_key`.

- [ ] **Step 2: MCP list + editor form**

args as multiline (one arg per line). Browse button for command path via `pickFile`.

- [ ] **Step 3: Wire Data export/uninstall** (move from current data panel into Settings → Data & Security)

- [ ] **Step 4: Appearance theme select binds to prefs**

- [ ] **Step 5: Manual: configure LLM+MCP without editing JSON; run triage**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(desktop-ui): settings GUI for LLM, MCP, data, appearance (P1)"
```

---

### Task 10: EmptyState deep-links + P1 gate

- [ ] **Step 1: EmptyState buttons set `activeView` to settings and optional hash `settings.llm` / `settings.mcp`**

- [ ] **Step 2: P1 checklist**

- [ ] No JSON edit required for golden path  
- [ ] Key never shown after save  
- [ ] MCP discover works from UI  
- [ ] pytest provider/mcp config green  

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(desktop-ui): P1 complete — full settings configuration GUI"
```

---

## Wave P2 — Evidence page

### Task 11: EvidenceView full page

**Files:**
- Create: `apps/desktop/renderer/views/EvidenceView.tsx`
- Modify: preload/main if `evidence.register` needs path from dialog (reuse pickFile)
- Modify: EventCard — link "View in Evidence" when type indicates register

**Interfaces:**
- Consumes: `evidence.list`, `evidence.register`, `evidence.verify` (existing)

- [ ] **Step 1: List UI with sha256 truncated + full on expand**

- [ ] **Step 2: Register via file picker → rpc register**

- [ ] **Step 3: Verify button → ok/mismatch display**

- [ ] **Step 4: Manual + existing `tests/test_desktop_m5_trust_evidence_pause.py` still pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(desktop-ui): independent evidence library view (P2)"
```

---

## Wave P3 — Polish

### Task 12: Keyboard shortcuts

**Files:**
- Create: `apps/desktop/renderer/hooks/useHotkeys.ts`
- Modify: `App.tsx`

| Key | Action |
|-----|--------|
| ⌘N | new session |
| ⌘, | settings |
| ⌘1 | workbench |
| ⌘2 | evidence |
| ⌘Enter | run when task focused |
| Esc | clear focus / close modal |

- [ ] **Step 1: Implement useHotkeys with preventDefault when target is not textarea (except ⌘Enter in task box)**

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(desktop-ui): keyboard shortcuts (P3)"
```

---

### Task 13: Font size prefs + focus rings + motion pass

**Files:**
- Modify: tokens / Settings Appearance
- `ui.prefs.font_size`: `sm|md|lg` → `html` font-size 13/14/16

- [ ] **Step 1: Implement font_size**  
- [ ] **Step 2: `:focus-visible` outlines using accent**  
- [ ] **Step 3: View switch animation class**  
- [ ] **Step 4: Light theme contrast pass (manual)**  
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(desktop-ui): font scale, a11y focus, motion polish (P3)"
```

---

### Task 14: Final acceptance + docs

**Files:**
- Modify: `apps/desktop/README.md` (UI structure, settings, themes)
- Modify: `docs/desktop/00-README.md` current status one paragraph
- Optional: `docs/desktop/12-M1.5-GOLDEN-PATH-RESULT.md` note UI path

- [ ] **Step 1: Run full desktop suite**

```bash
export PYTHONPATH="packages:."
.venv/bin/python -m pytest -q tests/test_desktop_*.py
cd apps/desktop && npm run typecheck && npm run codesign:verify
```

- [ ] **Step 2: Manual §1.3 success criteria from spec all checked**

- [ ] **Step 3: Commit**

```bash
git commit -m "docs(desktop-ui): complete frontend delivery notes and status"
```

---

## Spec coverage check

| Spec section | Tasks |
|--------------|-------|
| §2 tokens/theme/motion | 1, 2, 13 |
| §3 IA shell/workbench/evidence/settings | 3, 4, 9, 11 |
| §4 RPC provider/mcp/prefs | 6, 7, 8 |
| §5 directory structure | 1–4, 9, 11 |
| §6 interactions | 4, 9, 11, 12 |
| §7 waves P0–P3 | Tasks 1–5 / 6–10 / 11 / 12–14 |
| §8 tests | 6, 7, 14 |
| Non-goals | Enforced in Global Constraints |

## Placeholder scan

No TBD/TODO steps; concrete files and commands included.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-08-04-desktop-app-frontend.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, batch with checkpoints  

**Which approach?**
