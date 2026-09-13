import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, X, RefreshCw, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../api/client'
import { errorMessage } from '../lib/errorMessage'

type StatusFilter = 'pending' | 'approved' | 'rejected' | 'all'
type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

interface ApprovalRequest {
  id: number
  request_id: string
  user_id: number
  approver_id: number | null
  agent_id: number | null
  agent_name: string | null
  action_type: string
  action_description: string | null
  payload: Record<string, unknown> | null
  risk_level: RiskLevel
  urgency: string
  status: string
  created_at: string
  expires_at: string | null
  decided_at: string | null
  approver_comment: string | null
}

const RISK_COLOR: Record<RiskLevel, string> = {
  low: 'var(--accent)',
  medium: 'var(--green)',
  high: 'var(--amber, #ffb000)',
  critical: 'var(--red)',
}
const RISK_BG: Record<RiskLevel, string> = {
  low: 'rgba(0,255,65,0.08)',
  medium: 'var(--green-dim)',
  high: 'rgba(255,176,0,0.08)',
  critical: 'rgba(255,60,60,0.08)',
}
const STATUS_COLOR: Record<string, string> = {
  pending: 'var(--amber, #ffb000)',
  approved: 'var(--accent)',
  rejected: 'var(--red)',
  expired: 'var(--text-dim)',
  cancelled: 'var(--text-dim)',
}

function fmt(iso: string) {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export default function Approvals() {
  const { t } = useTranslation()
  const [items, setItems] = useState<ApprovalRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<StatusFilter>('pending')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [deciding, setDeciding] = useState<number | null>(null)
  const [comments, setComments] = useState<Record<number, string>>({})
  const [notice, setNotice] = useState<{ id: number; ok: boolean; msg: string } | null>(null)

  const load = useCallback(async () => {
    try {
      const d = await api.getApprovals(filter) as { requests: ApprovalRequest[]; total: number }
      setItems(d?.requests || [])
    } catch { setItems([]) }
    finally { setLoading(false) }
  }, [filter])

  useEffect(() => { void Promise.resolve().then(() => load()) }, [load])

  // Auto-refresh every 15s when viewing pending
  useEffect(() => {
    if (filter !== 'pending') return
    const id = setInterval(() => load(), 15_000)
    return () => clearInterval(id)
  }, [filter, load])

  const decide = async (item: ApprovalRequest, decision: 'approved' | 'rejected') => {
    setDeciding(item.id)
    setNotice(null)
    try {
      await api.decideApproval(item.id, decision, comments[item.id] || undefined)
      setNotice({ id: item.id, ok: true, msg: decision === 'approved' ? 'APPROVED' : 'REJECTED' })
      setTimeout(() => setNotice(null), 3000)
      await load()
    } catch (e: unknown) {
      setNotice({ id: item.id, ok: false, msg: errorMessage(e) || 'FAILED' })
    } finally {
      setDeciding(null)
    }
  }

  const filters: StatusFilter[] = ['pending', 'approved', 'rejected', 'all']

  return (
    <div>
      <PageHeader
        eyebrow="HUMAN-IN-THE-LOOP"
        title={t('approvals.title').toUpperCase()}
        description={t('approvals.subtitle')}
        actions={
          <button
            onClick={load}
            className="btn btn-secondary"
            style={{ display: 'flex', alignItems: 'center', gap: 6, height: 30 }}
          >
            <RefreshCw size={11} /> REFRESH
          </button>
        }
      />

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
        {filters.map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: '4px 14px', fontSize: 11, letterSpacing: '0.12em',
            border: `1px solid ${filter === f ? 'var(--accent-border)' : 'var(--border-bright)'}`,
            background: filter === f ? 'var(--accent-dim)' : 'transparent',
            color: filter === f ? 'var(--accent)' : 'var(--text-muted)',
            cursor: 'pointer',           }}>
            {f.toUpperCase()}
          </button>
        ))}
        {filter === 'pending' && !loading && (
          <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.08em', alignSelf: 'center' }}>
            AUTO-REFRESH 15s
          </span>
        )}
      </div>

      {/* List */}
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 40, color: 'var(--text-muted)', fontSize: 13 }}>
          <Loader2 size={16} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
          LOADING...
        </div>
      ) : items.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, letterSpacing: '0.1em' }}>
          {filter === 'pending' ? 'NO PENDING APPROVALS' : 'NO RECORDS'}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {items.map(item => {
            const risk = item.risk_level as RiskLevel
            const isExpanded = expanded === item.id
            const isPending = item.status === 'pending'
            const isDeciding = deciding === item.id
            const itemNotice = notice?.id === item.id ? notice : null

            return (
              <div key={item.id} className="item-card" style={{ border: `1px solid ${isPending ? 'var(--border-bright)' : 'var(--border)'}` }}>
                {/* Main row */}
                <div
                  onClick={() => setExpanded(isExpanded ? null : item.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 16px', cursor: 'pointer',
                  }}
                >
                  <span style={{ color: 'var(--text-dim)', flexShrink: 0 }}>
                    {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  </span>
                  <span className="item-card-pip" style={{ background: RISK_COLOR[risk] || 'var(--border)' }} />

                  {/* Risk badge */}
                  <span style={{
                    fontSize: 10, letterSpacing: '0.1em', padding: '2px 6px',
                    border: `1px solid ${RISK_COLOR[risk]}`,
                    color: RISK_COLOR[risk], background: RISK_BG[risk],
                    flexShrink: 0,
                  }}>
                    {risk.toUpperCase()}
                  </span>

                  {/* Urgency badge */}
                  {item.urgency === 'urgent' && (
                    <span style={{
                      fontSize: 10, letterSpacing: '0.1em', padding: '2px 6px',
                      border: '1px solid var(--red)', color: 'var(--red)',
                      background: 'rgba(255,60,60,0.08)', flexShrink: 0,
                    }}>
                      URGENT
                    </span>
                  )}

                  {/* Action info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.06em' }}>
                        {item.action_type.toUpperCase()}
                      </span>
                      {item.agent_name && (
                        <span style={{ fontSize: 11, color: 'var(--accent)', letterSpacing: '0.06em' }}>
                          {item.agent_name}
                        </span>
                      )}
                    </div>
                    {item.action_description && (
                      <div style={{
                        fontSize: 12, color: 'var(--text-muted)', marginTop: 2,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {item.action_description}
                      </div>
                    )}
                  </div>

                  {/* Status + time */}
                  <div style={{ flexShrink: 0, textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: STATUS_COLOR[item.status] || 'var(--text-dim)', letterSpacing: '0.1em' }}>
                      {item.status.toUpperCase()}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
                      {fmt(item.created_at)}
                    </div>
                  </div>

                  {/* Inline approve/reject for pending (stop propagation) */}
                  {isPending && (
                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                      <button
                        onClick={() => decide(item, 'approved')}
                        disabled={isDeciding}
                        title="APPROVE"
                        style={{
                          width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                          background: 'rgba(0,255,65,0.1)', border: '1px solid var(--accent)',
                          color: 'var(--accent)', cursor: isDeciding ? 'not-allowed' : 'pointer',
                        }}
                      >
                        {isDeciding ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={12} />}
                      </button>
                      <button
                        onClick={() => decide(item, 'rejected')}
                        disabled={isDeciding}
                        title="REJECT"
                        style={{
                          width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                          background: 'rgba(255,60,60,0.1)', border: '1px solid var(--red)',
                          color: 'var(--red)', cursor: isDeciding ? 'not-allowed' : 'pointer',
                        }}
                      >
                        <X size={12} />
                      </button>
                    </div>
                  )}
                </div>

                {/* Expanded detail panel */}
                {isExpanded && (
                  <div style={{
                    borderTop: '1px solid var(--border)',
                    padding: '14px 16px', background: 'var(--bg-base)',
                  }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 24px', marginBottom: 14 }}>
                      {[
                        ['REQUEST ID', item.request_id],
                        ['USER ID', String(item.user_id)],
                        ['AGENT', item.agent_name || '—'],
                        ['ACTION TYPE', item.action_type],
                        ['EXPIRES', item.expires_at ? fmt(item.expires_at) : '—'],
                        ['DECIDED', item.decided_at ? fmt(item.decided_at) : '—'],
                        ...(item.approver_comment ? [['COMMENT', item.approver_comment]] : []),
                      ].map(([label, value]) => (
                        <div key={label}>
                          <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.12em', marginBottom: 2 }}>{label}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-muted)', wordBreak: 'break-all' }}>{value}</div>
                        </div>
                      ))}
                    </div>

                    {item.action_description && (
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.12em', marginBottom: 4 }}>DESCRIPTION</div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>{item.action_description}</div>
                      </div>
                    )}

                    {item.payload && Object.keys(item.payload).length > 0 && (
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.12em', marginBottom: 4 }}>PAYLOAD</div>
                        <pre style={{
                          fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-elevated)',
                          border: '1px solid var(--border)', padding: '8px 12px',
                          overflowX: 'auto', maxHeight: 200, margin: 0,                         }}>
                          {JSON.stringify(item.payload, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Comment + decide buttons (only for pending) */}
                    {isPending && (
                      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                        <textarea
                          value={comments[item.id] || ''}
                          onChange={e => setComments(c => ({ ...c, [item.id]: e.target.value }))}
                          placeholder="OPTIONAL COMMENT..."
                          rows={2}
                          style={{
                            flex: 1, resize: 'none', padding: '6px 10px',
                            background: 'var(--bg-elevated)', border: '1px solid var(--border-bright)',
                            color: 'var(--text-primary)', fontSize: 12,
                            letterSpacing: '0.04em',
                          }}
                        />
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          <button
                            onClick={() => decide(item, 'approved')}
                            disabled={isDeciding}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 6,
                              padding: '0 14px', height: 32,
                              background: 'rgba(0,255,65,0.1)', border: '1px solid var(--accent)',
                              color: 'var(--accent)', fontSize: 12, letterSpacing: '0.1em',
                              cursor: isDeciding ? 'not-allowed' : 'pointer',                             }}
                          >
                            {isDeciding ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={11} />}
                            APPROVE
                          </button>
                          <button
                            onClick={() => decide(item, 'rejected')}
                            disabled={isDeciding}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 6,
                              padding: '0 14px', height: 32,
                              background: 'rgba(255,60,60,0.1)', border: '1px solid var(--red)',
                              color: 'var(--red)', fontSize: 12, letterSpacing: '0.1em',
                              cursor: isDeciding ? 'not-allowed' : 'pointer',                             }}
                          >
                            <X size={11} /> REJECT
                          </button>
                        </div>
                      </div>
                    )}

                    {itemNotice && (
                      <div style={{
                        marginTop: 10, fontSize: 12, letterSpacing: '0.1em',
                        color: itemNotice.ok ? 'var(--accent)' : 'var(--red)',
                      }}>
                        {itemNotice.msg}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
