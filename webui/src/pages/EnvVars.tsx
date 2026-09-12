import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Trash2, Eye, EyeOff, RefreshCw, Lock } from 'lucide-react'
import PageHeader from '../components/PageHeader'

interface EnvVar {
  id?: number
  key: string
  value_type: 'text' | 'secret'
  description?: string
  is_active?: boolean
}

export default function EnvVars() {
  const { t } = useTranslation()
  const [vars, setVars] = useState<EnvVar[]>([])
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')
  const [newType, setNewType] = useState<'text' | 'secret'>('text')
  const [newDesc, setNewDesc] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [decryptedValues, setDecryptedValues] = useState<Record<number, string>>({})
  const [visibleValues, setVisibleValues] = useState<Record<string, boolean>>({})
  const [decrypting, setDecrypting] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getEnvVars() as { vars: EnvVar[] }
      setVars(data?.vars || [])
    } catch { setVars([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const add = async () => {
    if (!newKey.trim()) return
    try {
      await api.createEnvVar({ key: newKey.trim().toUpperCase(), value: newVal, value_type: newType, description: newDesc || undefined })
      setNewKey(''); setNewVal(''); setNewType('text'); setNewDesc(''); setShowNew(false)
      load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: number) => {
    if (!confirm('CONFIRM DELETION?')) return
    try {
      await api.deleteEnvVar(id)
      setVars(v => v.filter(x => x.id !== id))
      setDecryptedValues(prev => { const n = { ...prev }; delete n[id]; return n })
    } catch (e: any) { alert(e.message) }
  }

  const toggleActive = async (v: EnvVar) => {
    if (!v.id) return
    try {
      await api.updateEnvVar(v.id, { is_active: !v.is_active })
      load()
    } catch (e: any) { alert(e.message) }
  }

  const decryptValue = async (id: number, key: string) => {
    if (decryptedValues[id]) {
      setVisibleValues(prev => ({ ...prev, [key]: !prev[key] }))
      return
    }
    setDecrypting(id)
    try {
      const res = await api.decryptEnvVar(id) as { value: string }
      setDecryptedValues(prev => ({ ...prev, [id]: res.value }))
      setVisibleValues(prev => ({ ...prev, [key]: true }))
    } catch (e: any) { alert(e.message) }
    finally { setDecrypting(null) }
  }

  const displayValue = (v: EnvVar) => {
    if (v.value_type !== 'secret') return '—'
    if (!decryptedValues[v.id!]) return '••••••••'
    if (!visibleValues[v.key]) return '••••••••'
    return decryptedValues[v.id!]
  }

  return (
    <div>
      <PageHeader
        eyebrow="SYSTEM CONFIGURATION"
        title={t('envvars.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={load} className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6, height: 36 }}>
              <RefreshCw size={11} /> REFRESH
            </button>
            <button onClick={() => setShowNew(!showNew)} className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8, height: 36 }}>
              <Lock size={11} /> NEW VAR
            </button>
          </div>
        }
      />

      {/* Security notice */}
      <div style={{
        padding: '10px 14px', marginBottom: 20,
        background: 'var(--red-dim)', border: '1px solid rgba(255,59,48,0.2)',
        display: 'flex', alignItems: 'flex-start', gap: 10,
      }}>
        <Lock size={13} style={{ color: 'var(--amber)', marginTop: 1, flexShrink: 0 }} />
        <div style={{ fontSize: 12, color: 'var(--amber)', letterSpacing: '0.05em', lineHeight: 1.6 }}>
          VALUES ARE AES-256 ENCRYPTED IN TRANSIT AND AT REST. DECRYPTION REQUIRES ADMIN PERMISSIONS.
        </div>
      </div>

      {/* Add New Form */}
      {showNew && (
        <div className="item-card" style={{ marginBottom: 20, padding: 20, display: 'block', background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16 }}>NEW ENVIRONMENT VARIABLE</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>KEY</label>
              <input value={newKey} onChange={e => setNewKey(e.target.value.toUpperCase())}
                placeholder="VARIABLE_NAME"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                                  }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>VALUE</label>
              <input value={newVal} onChange={e => setNewVal(e.target.value)}
                placeholder="VALUE (ENCRYPTED)"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                                  }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>TYPE</label>
              <select value={newType} onChange={e => setNewType(e.target.value as 'text' | 'secret')}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14,                 }}>
                <option value="text">TEXT</option>
                <option value="secret">SECRET</option>
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>DESCRIPTION (OPTIONAL)</label>
              <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
                placeholder="PURPOSE / USAGE..."
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                                  }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowNew(false)}
              style={{
                padding: '0 14px', height: 34,
                border: '1px solid var(--border-bright)', background: 'transparent',
                color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer',
                              }}>
              CANCEL
            </button>
            <button onClick={add}
              style={{
                padding: '0 14px', height: 34,
                background: 'var(--accent)', border: '1px solid var(--accent-border)',
                color: '#000', fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', cursor: 'pointer',
                              }}>
              ADD
            </button>
          </div>
        </div>
      )}

      {/* List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading ? (
          <div style={{ padding: '40px 0', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>LOADING...</div>
        ) : vars.length === 0 ? (
          <div style={{ padding: '40px 0', textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 8 }}>NO ENVIRONMENT VARIABLES</div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>CLICK "NEW VAR" TO CREATE ONE</div>
          </div>
        ) : vars.map(v => (
          <div key={v.id} className="item-card" style={{
            display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 12,
            padding: '12px 16px',
            background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
          }}>
            {/* Key */}
            <div style={{ width: 200, flexShrink: 0 }}>
              <span className="font-mono" style={{ fontSize: 13, color: 'var(--accent)', letterSpacing: '0.04em' }}>{v.key}</span>
              <span style={{
                marginLeft: 8, padding: '1px 5px',
                border: `1px solid ${v.value_type === 'secret' ? 'var(--amber)' : 'var(--border)'}`,
                color: v.value_type === 'secret' ? 'var(--amber)' : 'var(--text-muted)',
                fontSize: 10, letterSpacing: '0.1em', background: 'var(--bg-base)',
              }}>
                {v.value_type === 'secret' && <Lock size={8} style={{ display: 'inline', marginRight: 2 }} />}
                {v.value_type === 'secret' ? 'SECRET' : 'TEXT'}
              </span>
            </div>

            {/* Value */}
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
              {v.value_type === 'secret' ? (
                <>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>
                    {displayValue(v)}
                  </span>
                  {v.is_active && (
                    <button
                      onClick={() => decryptValue(v.id!, v.key)}
                      disabled={decrypting === v.id}
                      style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      {decrypting === v.id ? (
                        <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />
                      ) : visibleValues[v.key] ? (
                        <EyeOff size={12} />
                      ) : (
                        <Eye size={12} />
                      )}
                    </button>
                  )}
                </>
              ) : (
                <span style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em', fontStyle: 'italic' }}>TEXT TYPE — NOT PREVIEWABLE</span>
              )}
            </div>

            {/* Description */}
            <div style={{ flex: 1, fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {v.description || '—'}
            </div>

            {/* Active */}
            <button
              onClick={() => toggleActive(v)}
              style={{
                padding: '2px 8px',
                border: `1px solid ${v.is_active ? 'var(--green)' : 'var(--border)'}`,
                background: v.is_active ? 'rgba(0,255,65,0.05)' : 'transparent',
                color: v.is_active ? 'var(--green)' : 'var(--text-dim)',
                fontSize: 11, letterSpacing: '0.1em', cursor: 'pointer',
                              }}>
              {v.is_active ? 'ACTIVE' : 'INACTIVE'}
            </button>

            {/* Delete */}
            <button onClick={() => del(v.id!)} style={{ padding: 4, color: 'var(--red)', cursor: 'pointer', background: 'none', border: 'none' }}>
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
