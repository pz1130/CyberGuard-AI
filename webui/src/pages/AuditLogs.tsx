import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { FileText, Download, Search, Loader2 } from 'lucide-react'

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
  const [logs, setLogs] = useState<Log[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [limit, setLimit] = useState(50)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getAuditLogs({ limit }) as Log[] | { logs?: Log[] }
      setLogs(Array.isArray(data) ? data : data?.logs || [])
    } catch { setLogs([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [limit])

  const exportLogs = async () => {
    try {
      const data = await api.exportAuditLogs() as any
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `audit-logs-${Date.now()}.json`; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) { alert(e.message) }
  }

  const filtered = logs.filter(l =>
    !filter || l.action?.toLowerCase().includes(filter.toLowerCase()) ||
    String(l.user_id)?.includes(filter)
  )

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36, height: 36, border: '1px solid var(--border-bright)',
            background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--cyan)',
          }}>
            <FileText size={15} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>AUDIT LOG</div>
            <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>COMPLETE OPERATION RECORDS · SIEM EXPORT</div>
          </div>
        </div>
        <button onClick={exportLogs}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '0 16px', height: 36,
            background: 'var(--accent)', border: '1px solid var(--accent-border)',
            color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.15em', cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
          }}>
          <Download size={11} /> EXPORT
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <Search size={12} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input value={filter} onChange={e => setFilter(e.target.value)}
            placeholder="SEARCH ACTION OR USER ID..."
            style={{
              width: '100%', height: 36, paddingLeft: 36, paddingRight: 12,
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 11, letterSpacing: '0.05em',
              fontFamily: 'var(--font-mono)',
            }} />
        </div>
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          style={{
            height: 36, padding: '0 10px',
            background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
            color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)',
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
            color: 'var(--text-muted)', fontSize: 11, letterSpacing: '0.1em', cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
          }}>
          REFRESH
        </button>
      </div>

      {/* Table */}
      <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-bright)' }}>
              {['TIMESTAMP', 'USER', 'ACTION', 'REQUEST ID'].map((h, i) => (
                <th key={i} style={{ padding: '12px 16px', textAlign: i === 0 ? 'left' : 'left', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
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
                <td colSpan={4} style={{ textAlign: 'center', padding: 40, fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO LOG RECORDS</td>
              </tr>
            ) : filtered.map((log, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '14px 16px', fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                  {log.timestamp ? new Date(log.timestamp).toLocaleString('zh-CN') : '—'}
                </td>
                <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-muted)' }}>
                  {log.user_id ?? '—'}
                </td>
                <td style={{ padding: '14px 16px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--cyan)', letterSpacing: '0.05em' }}>{log.action}</td>
                <td style={{ padding: '14px 16px', fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>{log.request_id ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
