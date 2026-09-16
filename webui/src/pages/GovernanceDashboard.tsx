import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert, RefreshCw, Power, RotateCcw, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../api/client'
import { unwrapList } from '../lib/unwrapList'

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
      if (m.status === 'fulfilled') setMetrics(m.value as MetricsReport)
      if (h.status === 'fulfilled') setHalted(!!(h.value as { global?: boolean } | null)?.global)
      if (rb.status === 'fulfilled') setRollbacks((rb.value as Rollback[] | null) || [])
      if (av.status === 'fulfilled') setAuditIntact(!!(av.value as { intact?: boolean } | null)?.intact)
      if (ap.status === 'fulfilled') setPending(unwrapList(ap.value, 'requests').length)
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
        eyebrow={t('nav.features').toUpperCase()}
        title={t('nav.govDashboard').toUpperCase()}
        description={t('govDash.subtitle')}
        actions={
          <button className="btn btn-secondary" onClick={load} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {loading ? <RefreshCw size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {t('common.refresh').toUpperCase()}
          </button>
        }
      />

      {/* Kill switch banner */}
      <div className="card" style={{
        marginBottom: 16,
        padding: '16px 20px',
        border: `1px solid ${halted ? 'var(--red)' : 'var(--border-bright)'}`,
        background: halted ? 'rgba(239, 68, 68, 0.05)' : 'var(--bg-surface)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 38,
            height: 38,
            border: `1px solid ${halted ? 'rgba(239, 68, 68, 0.5)' : 'var(--accent-border)'}`,
            background: halted ? 'var(--red-dim)' : 'var(--accent-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: halted ? 'var(--red)' : 'var(--accent)',
            flexShrink: 0,
          }}>
            {halted ? <ShieldAlert size={20} /> : <ShieldCheck size={20} />}
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
                {t('govDash.killSwitch', 'EXECUTION CONTROL STATUS').toUpperCase()}
              </span>
              <span className={`badge ${halted ? 'badge-error' : 'badge-success'}`} style={{ fontFamily: 'var(--font-mono)' }}>
                {halted ? t('govDash.haltedState').toUpperCase() : t('govDash.runningState').toUpperCase()}
              </span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              {halted ? t('govDash.haltedDesc', 'Global safety kill switch is active. All agent operations are suspended.') : t('govDash.runningDesc', 'Global safety kill switch is disengaged. Agents operate under policy.')}
            </div>
          </div>
        </div>
        <button
          className={`btn ${halted ? 'btn-primary' : 'btn-danger'}`}
          onClick={toggleHalt}
          disabled={busy}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '0 16px',
            height: 36,
            ...(halted ? {} : { background: 'var(--red)', borderColor: 'var(--red)', color: '#ffffff' }),
          }}
        >
          <Power size={14} />
          {halted ? t('govDash.resume').toUpperCase() : t('govDash.emergencyStop').toUpperCase()}
        </button>
      </div>

      {/* Metrics grid */}
      <div className="card" style={{ padding: 0, marginBottom: 16, overflow: 'hidden' }}>
        <div style={{
          padding: '14px 18px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--bg-surface)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
              {t('govDash.pocMetrics').toUpperCase()}
            </span>
            {metrics && (
              <span className={`badge ${metrics.all_pass ? 'badge-success' : 'badge-error'}`}>
                {metrics.all_pass ? t('govDash.allPass').toUpperCase() : t('govDash.someFail').toUpperCase()}
              </span>
            )}
          </div>
          {metrics && (
            <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }}>
              {metrics.window_days}D ROLLING WINDOW
            </span>
          )}
        </div>
        <div style={{
          padding: 16,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
          gap: 12,
        }}>
          {metrics?.metrics.map((m) => (
            <div
              key={m.name}
              style={{
                padding: '14px 16px',
                background: 'var(--bg-elevated)',
                border: `1px solid ${m.pass ? 'var(--border)' : 'rgba(239, 68, 68, 0.4)'}`,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              <div style={{
                fontSize: 11,
                color: 'var(--text-dim)',
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {t(`govDash.metric.${m.name}`)}
              </div>
              <div style={{
                fontSize: 24,
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                letterSpacing: '0.02em',
                color: m.pass ? 'var(--text-primary)' : 'var(--red)',
              }}>
                {fmtMetric(m)}
              </div>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingTop: 8,
                borderTop: '1px solid var(--border)',
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  color: m.pass ? 'var(--green)' : 'var(--red)',
                  fontSize: 12,
                }}>
                  {m.pass ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                    {t('govDash.target')}: {fmtMetric({ ...m, value: m.target })}
                  </span>
                </div>
                <span
                  className={`badge ${m.pass ? 'badge-success' : 'badge-error'}`}
                  style={{ fontSize: 10, padding: '1px 6px', fontFamily: 'var(--font-mono)' }}
                >
                  {m.pass ? 'PASS' : 'FAIL'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Audit integrity + pending approvals */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{
            padding: '14px 18px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
              {t('govDash.auditIntegrity').toUpperCase()}
            </span>
            <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>SHA-256 HASH CHAIN</span>
          </div>
          <div style={{ padding: '20px 18px' }}>
            {auditIntact === null ? (
              <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>—</span>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 36,
                  height: 36,
                  border: `1px solid ${auditIntact ? 'var(--accent-border)' : 'rgba(239, 68, 68, 0.4)'}`,
                  background: auditIntact ? 'var(--accent-dim)' : 'var(--red-dim)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: auditIntact ? 'var(--accent)' : 'var(--red)',
                }}>
                  {auditIntact ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
                </div>
                <div>
                  <div style={{
                    fontSize: 14,
                    fontWeight: 700,
                    letterSpacing: '0.04em',
                    color: auditIntact ? 'var(--accent)' : 'var(--red)',
                  }}>
                    {auditIntact ? t('govDash.chainIntact').toUpperCase() : t('govDash.chainBroken').toUpperCase()}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>
                    {auditIntact ? 'Cryptographic audit signatures validated.' : 'Hash mismatch detected in audit log.'}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{
            padding: '14px 18px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
              {t('govDash.pendingApprovals').toUpperCase()}
            </span>
            <span className={`badge ${pending > 0 ? 'badge-warning' : 'badge-neutral'}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>
              {pending > 0 ? 'ACTION REQUIRED' : 'QUEUE CLEAR'}
            </span>
          </div>
          <div style={{ padding: '20px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 32, fontWeight: 700, fontFamily: 'var(--font-mono)', color: pending ? 'var(--amber)' : 'var(--text-dim)', lineHeight: 1 }}>
                {pending}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 6 }}>
                {t('govDash.pendingDesc', 'Agent actions awaiting operator authorization')}
              </div>
            </div>
            {pending > 0 && (
              <a href="/approvals" className="btn btn-secondary btn-sm" style={{ textDecoration: 'none' }}>
                {t('govDash.viewApprovals', 'REVIEW QUEUE')}
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Active rollbacks */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{
          padding: '14px 18px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
              {t('govDash.activeRollbacks').toUpperCase()}
            </span>
            <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
              {rollbacks.length}
            </span>
          </div>
        </div>
        {rollbacks.length === 0 ? (
          <div style={{ padding: '36px 16px', textAlign: 'center', color: 'var(--text-dim)', fontSize: 13 }}>
            {t('govDash.noRollbacks')}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>ACTION ID</th>
                  <th>{t('govDash.tool').toUpperCase()}</th>
                  <th>{t('govDash.expires').toUpperCase()}</th>
                  <th style={{ width: 100, textAlign: 'center' }}></th>
                </tr>
              </thead>
              <tbody>
                {rollbacks.map((r) => (
                  <tr key={r.action_id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)' }}>
                      {r.action_id}
                    </td>
                    <td>
                      <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
                        {r.tool || '—'}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                      {fmt(r.expires_at)}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className="btn btn-sm btn-secondary"
                        onClick={() => doRollback(r.action_id)}
                        disabled={busy}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--amber)', borderColor: 'rgba(245, 158, 11, 0.3)' }}
                      >
                        <RotateCcw size={12} /> {t('govDash.revert')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
