import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Database, Download, Trash2, Plus, RefreshCw, Loader2 } from 'lucide-react'

interface Backup {
  id: string
  name: string
  size?: string
  created_at?: string
  type: string
  status?: string
}

interface BackupApiRecord {
  id: string
  created_at?: string
  size_bytes?: number
  format?: string
  status?: string
}

function formatBytes(size?: number) {
  if (!size || size <= 0) return undefined
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = size
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

function mapBackup(record: BackupApiRecord): Backup {
  return {
    id: record.id,
    name: `backup-${record.id.slice(0, 8)}`,
    size: formatBytes(record.size_bytes),
    created_at: record.created_at,
    type: record.format || 'full',
    status: record.status,
  }
}

export default function Backup() {
  const [items, setItems] = useState<Backup[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [restoring, setRestoring] = useState<string | null>(null)

  const load = async () => {
    try {
      const data = await api.listBackups() as BackupApiRecord[] | { backups?: BackupApiRecord[] }
      const records = Array.isArray(data) ? data : data?.backups || []
      setItems(records.map(mapBackup))
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const create = async () => {
    setCreating(true)
    try {
      await api.createBackup({
        name: `backup-${Date.now()}`,
        backup_type: 'full',
      })
      await load()
    } catch (e: any) { alert(e.message) } finally { setCreating(false) }
  }

  const restore = async (id: string) => {
    if (!confirm('CONFIRM RESTORE? CURRENT DATA WILL BE OVERWRITTEN.')) return
    setRestoring(id)
    try {
      await api.restoreBackup(id)
      alert('RESTORE SUCCESS')
    } catch (e: any) { alert(e.message) } finally { setRestoring(null) }
  }

  const exportConfig = async () => {
    try {
      const data = await api.exportConfig() as any
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'cyberguard-config.json'; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) { alert(e.message) }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>DATA RESILIENCE</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>BACKUP & RESTORE</h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={exportConfig}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '0 14px', height: 36,
              border: '1px solid var(--border-bright)', background: 'transparent',
              color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
            }}>
            <Download size={11} /> EXPORT CONFIG
          </button>
          <button onClick={create} disabled={creating}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '0 16px', height: 36,
              background: creating ? 'var(--bg-elevated)' : 'var(--accent)',
              border: '1px solid var(--accent-border)',
              color: creating ? 'var(--text-dim)' : '#000',
              fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: creating ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-mono)',
            }}>
            {creating ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Plus size={11} />}
            {creating ? 'CREATING...' : 'CREATE BACKUP'}
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div style={{
        padding: '12px 16px', marginBottom: 24,
        background: 'var(--cyan-dim)', border: '1px solid rgba(0,245,255,0.1)',
        fontSize: 12, color: 'var(--cyan)', letterSpacing: '0.05em', lineHeight: 1.8,
      }}>
        PG_DUMP + AES-256 ENCRYPTION · S3/OSS UPLOAD OPTIONAL · CONFIGURE S3_ENDPOINT AND S3_ACCESS_KEY TO ENABLE REMOTE BACKUP
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 0', gap: 12 }}>
          <Loader2 size={18} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
          <span style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>LOADING...</span>
        </div>
      )}

      {/* Empty State */}
      {!loading && items.length === 0 && (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0',
          background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', gap: 12,
        }}>
          <Database size={28} style={{ color: 'var(--text-dim)' }} />
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO BACKUPS AVAILABLE</div>
          <button onClick={create} style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + CREATE FIRST BACKUP
          </button>
        </div>
      )}

      {/* Backup List */}
      {!loading && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map(b => (
            <div key={b.id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{
                  width: 38, height: 38, border: '1px solid var(--border-bright)',
                  background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: 'var(--cyan)',
                }}>
                  <Database size={14} />
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>{b.name}</span>
                    <span style={{
                      padding: '2px 6px', border: '1px solid var(--border)',
                      color: 'var(--cyan)', fontSize: 10, letterSpacing: '0.06em', background: 'var(--bg-base)',
                    }}>
                      {(b.type || 'FULL').replace(/\.AES$/i, '').toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    {b.size && <span style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{b.size}</span>}
                    {b.created_at && <span style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{b.created_at}</span>}
                    {b.status && <span style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{b.status.toUpperCase()}</span>}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => restore(b.id!)} disabled={restoring === b.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '0 12px', height: 32,
                    border: '1px solid var(--border-bright)', background: 'transparent',
                    color: restoring === b.id ? 'var(--text-dim)' : 'var(--text-muted)',
                    fontSize: 12, letterSpacing: '0.1em', cursor: restoring === b.id ? 'not-allowed' : 'pointer',
                    fontFamily: 'var(--font-mono)',
                  }}>
                  <RefreshCw size={10} style={restoring === b.id ? { animation: 'spin 1s linear infinite' } : {}} />
                  {restoring === b.id ? 'RESTORING...' : 'RESTORE'}
                </button>
                <button style={{ padding: 6, color: 'var(--red)', cursor: 'pointer', background: 'none', border: '1px solid rgba(255,59,48,0.2)' }}>
                  <Trash2 size={11} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
