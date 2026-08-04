# Governance Operations Dashboard (WebUI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give operators a single **Agent Governance** dashboard that surfaces the runtime governance signals the backend already exposes — POC success metrics, kill-switch state with an EMERGENCY STOP control, active rollback registrations, audit-chain integrity, and pending-approval count — so governance is observable and actionable, not just enforced.

**Architecture:** A new read-mostly page `webui/src/pages/AgentGovernance.tsx` (distinct from the existing GRC `Governance.tsx`) that polls existing endpoints via new methods on the `api` client. It reuses the project's page conventions: `PageHeader`, `useTranslation`, `lucide-react` icons, and `index.css` design tokens (`var(--accent/red/green/amber)`). Registered in `App.tsx`'s page registry with bilingual `nav.*` labels.

**Tech Stack:** React + TypeScript, react-i18next, lucide-react, the existing `api` client (`webui/src/api/client.ts`), Vite/tsc build, Playwright smoke (webapp-testing). No backend change — consumes already-implemented endpoints.

---

## Dependencies & decisions

- **Consumes already-implemented endpoints:** `GET /governance/metrics`, `GET /agents/halt/status`, `POST`/`DELETE /agents/halt`, `GET /governance/rollback`, `POST /governance/rollback/{id}`, `GET /audit/verify`, `GET /approvals?status_filter=pending`. (These come from the controls / safety-envelope / poc-metrics plans the user has implemented.)
- **Distinct from GRC:** the existing `Governance.tsx` is the ISO/NIST compliance tracker. This is **operations**, so it gets its own nav entry (`agentGovernance` / 智能体治理) to avoid confusion.
- **Read-mostly + two privileged actions:** EMERGENCY STOP / Resume (halt) and Trigger-rollback. Both are admin-gated server-side; the UI shows them but the backend enforces RBAC.
- **Polling:** 10s interval for live panels (halt status, metrics), with a manual refresh — matches the app's existing lightweight polling style. No websockets needed.

## File Structure

| File | Responsibility |
|------|----------------|
| `webui/src/api/client.ts` (modify) | governance ops methods |
| `webui/src/pages/AgentGovernance.tsx` (create) | the dashboard page |
| `webui/src/App.tsx` (modify) | import + register the page route |
| `webui/src/i18n/*` (modify) | `nav.agentGovernance` + page strings (en + zh) |
| `tests/webui/agent-governance.smoke.md` (create) | Playwright smoke checklist |

---

### Task 1: API client methods

**Files:**
- Modify: `webui/src/api/client.ts`

- [ ] **Step 1: Add governance-ops methods** to the `api` object (place near the existing approvals/audit methods):

```typescript
  // --- Agent governance operations ---
  getGovernanceMetrics: (windowDays = 30) =>
    request(`/governance/metrics?window_days=${windowDays}`),
  getHaltStatus: () => request('/agents/halt/status'),
  haltAll: (reason: string) =>
    request('/agents/halt', { method: 'POST', body: JSON.stringify({ reason }) }),
  resumeAll: () => request('/agents/halt', { method: 'DELETE' }),
  getRollbacks: () => request('/governance/rollback'),
  triggerRollback: (actionId: string) =>
    request(`/governance/rollback/${actionId}`, { method: 'POST' }),
  verifyAudit: () => request('/audit/verify'),
```

- [ ] **Step 2: Type-check + commit**

```bash
cd webui && npx tsc --noEmit 2>&1 | head -5; cd ..
git add webui/src/api/client.ts
git commit -m "feat(ui): governance ops api client methods"
```
Expected: tsc clean (no new errors).

### Task 2: The dashboard page

**Files:**
- Create: `webui/src/pages/AgentGovernance.tsx`

- [ ] **Step 1: Implement the page** (matches `Approvals.tsx` conventions — hooks, `t()`, tokens, `PageHeader`)

```tsx
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert, RefreshCw, Loader2, Power, RotateCcw, CheckCircle2, XCircle } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../api/client'

interface Metric { name: string; value: number; target: number; pass: boolean }
interface MetricsReport { window_days: number; metrics: Metric[]; all_pass: boolean }
interface Rollback { action_id: string; tool: string | null; expires_at: string }

const PCT = new Set(['governance_violation_rate', 'human_override_rate', 'audit_completeness', 'rollback_success_rate'])
function fmtMetric(m: Metric): string {
  if (m.name === 'kill_switch_response_seconds') return `${m.value.toFixed(2)}s`
  if (PCT.has(m.name)) return `${(m.value * 100).toFixed(2)}%`
  return String(m.value)
}
function fmt(iso: string) {
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function AgentGovernance() {
  const { t } = useTranslation()
  const [metrics, setMetrics] = useState<MetricsReport | null>(null)
  const [halted, setHalted] = useState<boolean | null>(null)
  const [rollbacks, setRollbacks] = useState<Rollback[]>([])
  const [auditIntact, setAuditIntact] = useState<boolean | null>(null)
  const [pending, setPending] = useState<number>(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [m, h, rb, av, ap] = await Promise.allSettled([
        api.getGovernanceMetrics(30), api.getHaltStatus(), api.getRollbacks(),
        api.verifyAudit(), api.getApprovals('pending'),
      ])
      if (m.status === 'fulfilled') setMetrics(m.value)
      if (h.status === 'fulfilled') setHalted(!!h.value?.global)
      if (rb.status === 'fulfilled') setRollbacks(rb.value || [])
      if (av.status === 'fulfilled') setAuditIntact(!!av.value?.intact)
      if (ap.status === 'fulfilled') setPending((ap.value || []).length)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [load])

  const toggleHalt = async () => {
    setBusy(true)
    try {
      if (halted) await api.resumeAll()
      else await api.haltAll(window.prompt(t('agentGovernance.haltReason')) || 'manual')
      await load()
    } finally { setBusy(false) }
  }

  const doRollback = async (id: string) => {
    if (!window.confirm(t('agentGovernance.confirmRollback'))) return
    setBusy(true)
    try { await api.triggerRollback(id); await load() } finally { setBusy(false) }
  }

  const card: React.CSSProperties = {
    background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 8, padding: 16,
  }

  return (
    <div>
      <PageHeader title={t('nav.agentGovernance')} subtitle={t('agentGovernance.subtitle')}
        actions={<button className="btn" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />} {t('common.refresh')}
        </button>} />

      {/* Kill switch banner */}
      <div style={{ ...card, marginBottom: 16, borderColor: halted ? 'var(--red)' : 'var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <ShieldAlert size={20} color={halted ? 'var(--red)' : 'var(--green)'} />
            <strong>{halted ? t('agentGovernance.haltedState') : t('agentGovernance.runningState')}</strong>
          </div>
          <button className="btn" onClick={toggleHalt} disabled={busy}
            style={{ background: halted ? 'var(--green)' : 'var(--red)', color: '#fff' }}>
            <Power size={16} /> {halted ? t('agentGovernance.resume') : t('agentGovernance.emergencyStop')}
          </button>
        </div>
      </div>

      {/* Metrics grid */}
      <div style={{ ...card, marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t('agentGovernance.pocMetrics')}
          {metrics && <span style={{ marginLeft: 8, color: metrics.all_pass ? 'var(--green)' : 'var(--red)' }}>
            {metrics.all_pass ? t('agentGovernance.allPass') : t('agentGovernance.someFail')}</span>}
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(200px,1fr))', gap: 12 }}>
          {metrics?.metrics.map((m) => (
            <div key={m.name} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{t(`agentGovernance.metric.${m.name}`)}</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{fmtMetric(m)}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: m.pass ? 'var(--green)' : 'var(--red)' }}>
                {m.pass ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                <span style={{ fontSize: 12 }}>{t('agentGovernance.target')}: {fmtMetric({ ...m, value: m.target })}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Audit integrity + pending approvals */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>{t('agentGovernance.auditIntegrity')}</h3>
          {auditIntact === null ? '—' : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: auditIntact ? 'var(--green)' : 'var(--red)' }}>
              {auditIntact ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              {auditIntact ? t('agentGovernance.chainIntact') : t('agentGovernance.chainBroken')}
            </div>
          )}
        </div>
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>{t('agentGovernance.pendingApprovals')}</h3>
          <div style={{ fontSize: 28, fontWeight: 700, color: pending ? 'var(--amber, #ffb000)' : 'var(--text-dim)' }}>{pending}</div>
        </div>
      </div>

      {/* Active rollbacks */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>{t('agentGovernance.activeRollbacks')}</h3>
        {rollbacks.length === 0 ? <div style={{ color: 'var(--text-dim)' }}>{t('agentGovernance.noRollbacks')}</div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr style={{ textAlign: 'left', color: 'var(--text-dim)' }}>
              <th>action_id</th><th>{t('agentGovernance.tool')}</th><th>{t('agentGovernance.expires')}</th><th></th>
            </tr></thead>
            <tbody>
              {rollbacks.map((r) => (
                <tr key={r.action_id} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.action_id}</td>
                  <td>{r.tool || '—'}</td>
                  <td>{fmt(r.expires_at)}</td>
                  <td><button className="btn" onClick={() => doRollback(r.action_id)} disabled={busy}>
                    <RotateCcw size={14} /> {t('agentGovernance.revert')}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
```

> If `PageHeader` doesn't accept `subtitle`/`actions` props, match its actual signature (check another page that uses it). The CSS classes (`btn`, `spin`) and tokens are the ones already used across the app — adjust names to the exact ones in `index.css` if they differ.

- [ ] **Step 2: Type-check**

```bash
cd webui && npx tsc --noEmit 2>&1 | head -10; cd ..
```
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add webui/src/pages/AgentGovernance.tsx
git commit -m "feat(ui): Agent Governance operations dashboard page"
```

### Task 3: Route registration + i18n

**Files:**
- Modify: `webui/src/App.tsx`, `webui/src/i18n/*`

- [ ] **Step 1: Register the page** in `App.tsx` — add the import and a registry entry next to `governance`:

```tsx
import AgentGovernance from './pages/AgentGovernance'
// ...in the page registry object:
  agentGovernance: { labelKey: 'nav.agentGovernance', component: <AgentGovernance /> },
```

> Place the entry where it should appear in the sidebar order (near `approvals`/`governance`). If nav order is derived from the registry key order, position accordingly.

- [ ] **Step 2: Add i18n keys** to the English and Chinese resource files under `webui/src/i18n/` (match the existing structure used by `nav.*`):

English:
```json
"nav": { "agentGovernance": "Agent Governance" },
"agentGovernance": {
  "subtitle": "Runtime governance: metrics, kill switch, rollbacks, audit integrity",
  "pocMetrics": "POC Success Metrics", "allPass": "ALL PASS", "someFail": "ATTENTION",
  "target": "target", "runningState": "Agents running", "haltedState": "KILL SWITCH ENGAGED",
  "emergencyStop": "EMERGENCY STOP", "resume": "Resume", "haltReason": "Reason for halt:",
  "auditIntegrity": "Audit Chain Integrity", "chainIntact": "Chain intact", "chainBroken": "CHAIN BROKEN",
  "pendingApprovals": "Pending Approvals", "activeRollbacks": "Active Rollbacks", "noRollbacks": "No active rollbacks",
  "tool": "Tool", "expires": "Expires", "revert": "Revert", "confirmRollback": "Trigger this rollback now?",
  "metric": {
    "governance_violation_rate": "Governance violations", "human_override_rate": "Human override rate",
    "kill_switch_response_seconds": "Kill-switch response", "audit_completeness": "Audit completeness",
    "rollback_success_rate": "Rollback success"
  }
}
```

Chinese (mirror keys):
```json
"nav": { "agentGovernance": "智能体治理" },
"agentGovernance": {
  "subtitle": "运行时治理：指标、紧急停止、回滚、审计完整性",
  "pocMetrics": "POC 验收指标", "allPass": "全部达标", "someFail": "需关注",
  "target": "目标", "runningState": "智能体运行中", "haltedState": "紧急停止已启用",
  "emergencyStop": "紧急停止", "resume": "恢复", "haltReason": "停止原因：",
  "auditIntegrity": "审计链完整性", "chainIntact": "链完整", "chainBroken": "链已损坏",
  "pendingApprovals": "待审批", "activeRollbacks": "活动回滚", "noRollbacks": "无活动回滚",
  "tool": "工具", "expires": "过期时间", "revert": "回滚", "confirmRollback": "立即触发此回滚？",
  "metric": {
    "governance_violation_rate": "治理违规率", "human_override_rate": "人工否决率",
    "kill_switch_response_seconds": "紧急停止响应", "audit_completeness": "审计完整性",
    "rollback_success_rate": "回滚成功率"
  }
}
```

- [ ] **Step 3: Build + commit**

```bash
cd webui && npx tsc --noEmit && npm run build 2>&1 | tail -5; cd ..
git add webui/src/App.tsx webui/src/i18n
git commit -m "feat(ui): register Agent Governance route + bilingual strings"
```
Expected: build succeeds.

### Task 4: Smoke verification (webapp-testing / Playwright)

**Files:**
- Create: `tests/webui/agent-governance.smoke.md`

- [ ] **Step 1: Write the smoke checklist** (drive with the webapp-testing skill / Playwright against a running dev server)

```markdown
# Agent Governance dashboard — smoke checklist

Preconditions: app running, logged in as admin.

1. Navigate to the Agent Governance nav item → page loads, no console errors.
2. Kill-switch banner shows "Agents running" (green). Click EMERGENCY STOP →
   banner turns red "KILL SWITCH ENGAGED"; `GET /agents/halt/status` returns global=true.
3. Click Resume → banner returns to green.
4. POC metrics grid renders 5 tiles, each with a value, target, and pass/fail badge;
   header shows ALL PASS / ATTENTION matching `all_pass`.
5. Audit Chain Integrity shows "Chain intact" (matches `GET /audit/verify`).
6. Pending Approvals count matches `GET /approvals?status_filter=pending`.
7. If a rollback registration exists, it lists with a Revert button; clicking it
   calls `POST /governance/rollback/{id}` and the row clears on refresh.
8. Toggle language → all labels switch (no raw i18n keys visible).
```

- [ ] **Step 2: Run the smoke** (optional automation via the webapp-testing skill / Playwright MCP) and record results.

- [ ] **Step 3: Commit**

```bash
git add tests/webui/agent-governance.smoke.md
git commit -m "test(ui): Agent Governance dashboard smoke checklist"
```

---

## Self-Review notes

- **Operator value:** one screen for the five governance signals + the two actions (halt / revert) that an on-call would need during an incident.
- **No backend changes:** consumes endpoints from the already-implemented plans; if any path differs in the running code, adjust the api client method to match (single point of change).
- **Honest UI caveats:** (1) the page uses inline styles to stay close to the existing pages' approach — if the app has a shared card/table component, prefer it. (2) `PageHeader` and CSS class/token names must be matched to the real ones in this repo (the example assumes `btn`/`spin`/`--panel`/`--border`); verify before committing. (3) RBAC: the halt/revert buttons are shown to all who can see the page; the backend enforces admin — optionally hide them for non-admins using the app's existing role context for nicer UX. (4) 10s polling is fine for this scale; switch to SSE only if you later want sub-second kill-switch reflection.
- **Remaining beyond-NDB ideas (unchanged):** signed audit (HMAC/KMS), red-team CI gate, out-of-band action detection.
