import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import ChatEvidence from './ChatEvidence'
import { Download, Search, Loader2 } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { errorMessage } from '../lib/errorMessage'

interface Log {
  id?: number
  user_id?: number
  agent_id?: string
  action: string
  input_hash?: string
  output_hash?: string
  request_id?: string
  timestamp?: string
}

export default function AuditLogs() {
  const { t } = useTranslation()
  const [showSyslog, setShowSyslog] = useState(false)
  const [syslog, setSyslog] = useState({ host: '', port: 514, protocol: 'tcp' as 'udp' | 'tcp', facility: 16 })
  const [sending, setSending] = useState(false)
  const [syslogResult, setSyslogResult] = useState('')
  const [syslogError, setSyslogError] = useState('')
  const [logs, setLogs] = useState<Log[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [limit, setLimit] = useState(50)
  const [tab, setTab] = useState<'logs' | 'evidence'>('logs')

  const load = useCallback(async () => {
    try {
      const data = await api.getAuditLogs({ limit }) as Log[] | { logs?: Log[] }
      setLogs(Array.isArray(data) ? data : data?.logs || [])
    } catch { setLogs([]) } finally { setLoading(false) }
  }, [limit])
  useEffect(() => { void Promise.resolve().then(() => load()) }, [load])

  const exportLogs = async () => {
    try {
      const data: unknown = await api.exportAuditLogs()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `audit-logs-${Date.now()}.json`; a.click()
      URL.revokeObjectURL(url)
    } catch (e: unknown) { alert(errorMessage(e)) }
  }

  const exportSyslog = async (event: React.FormEvent) => {
    event.preventDefault()
    setSending(true); setSyslogResult(''); setSyslogError('')
    try {
      const result = await api.exportAuditLogsSyslog(syslog) as { sent: number }
      setSyslogResult(t('audit.syslogSent', { count: result.sent }))
    } catch (e: unknown) { setSyslogError(errorMessage(e)) }
    finally { setSending(false) }
  }

  const filtered = logs.filter(l =>
    !filter || l.action?.toLowerCase().includes(filter.toLowerCase()) ||
    String(l.user_id)?.includes(filter)
  )

  return (
    <div>
      {/* Header */}
      <PageHeader
        eyebrow="COMPLETE OPERATION RECORDS · SIEM EXPORT"
        title={t('audit.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => setShowSyslog(!showSyslog)} aria-expanded={showSyslog}>SYSLOG</button>
          <button
            onClick={exportLogs}
            className="btn btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: 8, height: 36 }}
          >
            <Download size={13} /> EXPORT
          </button>
          </div>
        }
      />

      {showSyslog && <form onSubmit={exportSyslog} style={{ padding: 20, marginBottom: 20, border: '1px solid var(--border-bright)' }}>
        <p style={{ marginTop: 0 }}>{t('audit.syslogDescription')}</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'end' }}>
          <label style={{ display: 'grid', gap: 6 }}>{t('audit.syslogHost')}<input required maxLength={253} value={syslog.host} placeholder="syslog.example.com"
            disabled={sending} onChange={e => setSyslog({ ...syslog, host: e.target.value })} /></label>
          <label style={{ display: 'grid', gap: 6 }}>{t('audit.syslogPort')}<input required type="number" min={1} max={65535} value={syslog.port}
            disabled={sending} onChange={e => setSyslog({ ...syslog, port: Number(e.target.value) })} /></label>
          <label style={{ display: 'grid', gap: 6 }}>{t('audit.syslogProtocol')}<select value={syslog.protocol} disabled={sending}
            onChange={e => setSyslog({ ...syslog, protocol: e.target.value as 'udp' | 'tcp' })}>
            <option value="tcp">TCP</option><option value="udp">UDP</option>
          </select></label>
          <label style={{ display: 'grid', gap: 6 }}>Facility<select value={syslog.facility} disabled={sending}
            onChange={e => setSyslog({ ...syslog, facility: Number(e.target.value) })}>
            {Array.from({ length: 8 }, (_, i) => <option key={i} value={16 + i}>local{i}</option>)}
          </select></label>
          <button className="btn btn-primary" type="submit" disabled={sending}>
            {sending ? t('audit.syslogSending') : t('audit.syslogSend')}
          </button>
        </div>
        {syslogResult && <p role="status">{syslogResult}</p>}
        {syslogError && <p role="alert" style={{ color: 'var(--red)' }}>{syslogError}</p>}
      </form>}

      {/* Tabs — both halves of the auditor's job: what the system did, and
          what was said. Same permission, same person. */}
      <div style={{ display: 'flex', border: '1px solid var(--border-bright)',
                    width: 'fit-content', marginBottom: 20 }}>
        {([['logs', t('audit.tabLogs')], ['evidence', t('audit.tabEvidence')]] as const)
          .map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)} role="tab"
              aria-selected={tab === key}
              style={{
                padding: '8px 20px', fontSize: 12, letterSpacing: '0.08em',
                fontWeight: 600, cursor: 'pointer', border: 'none',
                background: tab === key ? 'var(--accent)' : 'var(--bg-surface)',
                color: tab === key ? '#000' : 'var(--text-muted)',
                borderRight: key === 'logs' ? '1px solid var(--border-bright)' : 'none',
              }}>
              {label.toUpperCase()}
            </button>
          ))}
      </div>

      {tab === 'evidence' && <ChatEvidence />}

      {tab === 'logs' && (<>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <Search size={12} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input value={filter} onChange={e => setFilter(e.target.value)}
            placeholder="SEARCH ACTION OR USER ID..."
            style={{
              width: '100%', height: 36, paddingLeft: 36, paddingRight: 12,
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 13, letterSpacing: '0.05em',
            }} />
        </div>
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          style={{
            height: 36, padding: '0 10px',
            background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
            color: 'var(--text-primary)', fontSize: 13,
          }}>
          <option value={20}>20 RECORDS</option>
          <option value={50}>50 RECORDS</option>
          <option value={100}>100 RECORDS</option>
          <option value={500}>500 RECORDS</option>
        </select>
        <button onClick={load}
          style={{
            height: 36, padding: '0 14px',
            border: '1px solid var(--border-bright)', background: 'transparent',
            color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em', cursor: 'pointer',
          }}>
          REFRESH
        </button>
      </div>

      {/* Table */}
      <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden', borderRadius: 'var(--radius-lg)' }}>
        <table className="data-table">
          <thead>
            <tr>
              {['TIMESTAMP', 'USER', 'ACTION', 'REQUEST ID'].map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} style={{ textAlign: 'center', padding: 40 }}>
                  <Loader2 size={18} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite', margin: '0 auto' }} />
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ textAlign: 'center', padding: 40, fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO LOG RECORDS</td>
              </tr>
            ) : filtered.map((log, i) => (
              <tr key={i}>
                <td className="font-mono" style={{ fontSize: 12, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                  {log.timestamp ? new Date(log.timestamp).toLocaleString('zh-CN') : '—'}
                </td>
                <td style={{ color: 'var(--text-muted)' }}>
                  {log.user_id ?? '—'}
                </td>
                <td style={{ color: 'var(--cyan)', letterSpacing: '0.05em' }}>{log.action}</td>
                <td className="font-mono" style={{ fontSize: 12, color: 'var(--text-dim)' }}>{log.request_id ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </>)}
    </div>
  )
}
