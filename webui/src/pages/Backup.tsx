import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Database, Download, Trash2, Plus, RefreshCw, Loader2 } from 'lucide-react'
import PageHeader from '../components/PageHeader'

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
  const { t } = useTranslation()
  const [items, setItems] = useState<Backup[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [restoring, setRestoring] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [excludeChat, setExcludeChat] = useState(false)

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
        exclude_chat: excludeChat,
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

  const del = async (id: string) => {
    if (!confirm('DELETE THIS BACKUP? THE ENCRYPTED DUMP WILL BE PERMANENTLY REMOVED.')) return
    setDeleting(id)
    try {
      await api.deleteBackup(id)
      await load()
    } catch (e: any) { alert(e.message) } finally { setDeleting(null) }
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
      <PageHeader
        eyebrow="DATA RESILIENCE"
        title={t('backup.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={exportConfig}
              className="btn btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Download size={11} /> EXPORT CONFIG
            </button>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-muted)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={excludeChat}
                onChange={e => setExcludeChat(e.target.checked)}
                style={{ accentColor: 'var(--accent)' }}
              />
              Exclude chat records
            </label>
            <button
              onClick={create}
              disabled={creating}
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: creating ? 0.6 : 1 }}
            >
              {creating ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Plus size={11} />}
              {creating ? 'CREATING...' : 'CREATE BACKUP'}
            </button>
          </div>
        }
      />

      {/* Info Banner */}
      <div style={{
        padding: '12px 16px', marginBottom: 24,
        background: 'var(--accent-dim)', border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-md)',
        fontSize: 12, color: 'var(--accent)', letterSpacing: '0.05em', lineHeight: 1.8,
      }}>
        FULL DB BACKUP (PG_DUMP + AES-256) OR "EXPORT CONFIG" (JSON: providers, users, agents, skills, tools, prompts, knowledge bases, MCP, environment, security, and master config — no chat/audit/executions) · CHECK "Exclude chat records" FOR DB BACKUP WITHOUT HISTORY · S3 OPTIONAL
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
          background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', gap: 12,
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {items.map(b => (
            <div key={b.id} data-item-id={b.id} className="item-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 36, height: 36, border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)', flexShrink: 0 }}>
                  <Database size={14} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span className="item-card-title" style={{ fontSize: 14 }}>{b.name}</span>
                    <span className="item-card-badge" style={{ color: 'var(--accent)' }}>
                      {(b.type || 'FULL').replace(/\.AES$/i, '').toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 11, color: 'var(--text-dim)' }}>
                    {b.size && <span>{b.size}</span>}
                    {b.created_at && <span>{b.created_at}</span>}
                    {b.status && <span>{b.status.toUpperCase()}</span>}
                  </div>
                </div>
              </div>
              <div className="item-card-actions">
                <button onClick={() => restore(b.id!)} disabled={restoring === b.id} className="item-card-btn">
                  <RefreshCw size={11} style={restoring === b.id ? { animation: 'spin 1s linear infinite' } : {}} />
                  {restoring === b.id ? 'RESTORING...' : 'RESTORE'}
                </button>
                <div style={{ marginLeft: 'auto' }}>
                  <button onClick={() => del(b.id!)} disabled={deleting === b.id} className="item-card-icon-btn danger" title="DELETE">
                    {deleting === b.id ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={13} />}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
