import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert, RefreshCw, Power, RotateCcw, CheckCircle2, XCircle } from 'lucide-react'
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
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function GovernanceDashboard() {
  const { t } = useTranslation()
  const [metrics, setMetrics] = useState<MetricsReport | null>(null)
  const [halted, setHalted] = useState<boolean | null>(null)
  const [rollbacks, setRollbacks] = useState<Rollback[]>([])
  const [auditIntact, setAuditIntact] = useState<boolean | null>(null)
  const [pending, setPending] = useState<number>(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
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
      else await api.haltAll(window.prompt(t('govDash.haltReason')) || 'manual')
      await load()
    } finally { setBusy(false) }
  }

  const doRollback = async (id: string) => {
    if (!window.confirm(t('govDash.confirmRollback'))) return
    setBusy(true)
    try { await api.triggerRollback(id); await load() } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader
        eyebrow={t('nav.features')}
        title={t('nav.govDashboard')}
        description={t('govDash.subtitle')}
        actions={
          <button className="btn btn-secondary" onClick={load} disabled={loading}>
            {loading ? <RefreshCw size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {t('common.refresh')}
          </button>
        }
      />

      {/* Kill switch banner */}
      <div className="card" style={{ marginBottom: 16, borderColor: halted ? 'var(--red)' : 'var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <ShieldAlert size={20} color={halted ? 'var(--red)' : 'var(--green)'} />
            <strong>{halted ? t('govDash.haltedState') : t('govDash.runningState')}</strong>
          </div>
          <button className={`btn ${halted ? 'btn-primary' : ''}`} onClick={toggleHalt} disabled={busy}
            style={halted ? undefined : { background: 'var(--red)', color: '#fff' }}>
            <Power size={14} />
            {halted ? t('govDash.resume') : t('govDash.emergencyStop')}
          </button>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t('govDash.pocMetrics')}
          {metrics && (
            <span className={`badge ${metrics.all_pass ? 'badge-success' : 'badge-error'}`} style={{ marginLeft: 8 }}>
              {metrics.all_pass ? t('govDash.allPass') : t('govDash.someFail')}
            </span>
          )}
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(180px,1fr))', gap: 12 }}>
          {metrics?.metrics.map((m) => (
            <div key={m.name} className="card-elevated" style={{ padding: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{t(`govDash.metric.${m.name}`)}</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{fmtMetric(m)}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: m.pass ? 'var(--green)' : 'var(--red)' }}>
                {m.pass ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                <span style={{ fontSize: 12 }}>{t('govDash.target')}: {fmtMetric({ ...m, value: m.target })}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Audit integrity + pending approvals */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t('govDash.auditIntegrity')}</h3>
          {auditIntact === null ? <span style={{ color: 'var(--text-dim)' }}>—</span> : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: auditIntact ? 'var(--green)' : 'var(--red)' }}>
              {auditIntact ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
              {auditIntact ? t('govDash.chainIntact') : t('govDash.chainBroken')}
            </div>
          )}
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t('govDash.pendingApprovals')}</h3>
          <div style={{ fontSize: 28, fontWeight: 700, color: pending ? 'var(--amber)' : 'var(--text-dim)' }}>{pending}</div>
        </div>
      </div>

      {/* Active rollbacks */}
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{t('govDash.activeRollbacks')}</h3>
        {rollbacks.length === 0 ? (
          <div style={{ color: 'var(--text-dim)' }}>{t('govDash.noRollbacks')}</div>
        ) : (
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr>
              <th>action_id</th><th>{t('govDash.tool')}</th><th>{t('govDash.expires')}</th><th></th>
            </tr></thead>
            <tbody>
              {rollbacks.map((r) => (
                <tr key={r.action_id}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.action_id}</td>
                  <td>{r.tool || '—'}</td>
                  <td>{fmt(r.expires_at)}</td>
                  <td>
                    <button className="btn btn-sm btn-ghost" onClick={() => doRollback(r.action_id)} disabled={busy}>
                      <RotateCcw size={14} /> {t('govDash.revert')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
