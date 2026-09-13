import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Trash2, Edit2 } from 'lucide-react'

interface User {
  id?: number
  username: string
  email?: string
  role: string
  is_active?: boolean
  created_at?: string
}

const ROLES = ['admin', 'operator', 'viewer']

export default function Users() {
  const { t } = useTranslation()
  const [items, setItems] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState<User>({ username: '', email: '', role: 'viewer' })
  const [password, setPassword] = useState('')
  const [activeTab, setActiveTab] = useState<'users' | 'sso'>('users')
  // SSO state
  const [ssoCfg, setSsoCfg] = useState<any>(null)
  const [ssoMappings, setSsoMappings] = useState<any[]>([])
  const [ssoSaving, setSsoSaving] = useState(false)
  const [newMapping, setNewMapping] = useState({ azure_key: '', app_role: 'viewer', priority: 10 })
  const [secretEnvVars, setSecretEnvVars] = useState<{id: number; key: string; description?: string}[]>([])

  const load = useCallback(async () => {
    try {
      const data = await api.getUsers() as User[] | { users?: User[] }
      setItems(Array.isArray(data) ? data : data?.users || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }, [])
  useEffect(() => { void Promise.resolve().then(() => load()) }, [load])

  const submit = async () => {
    if (!form.username || form.username.trim().length < 3) {
      alert('Username must be at least 3 characters'); return
    }
    if (!form.email || !form.email.includes('@')) {
      alert('Please enter a valid email address'); return
    }
    if (!editing && (!password || password.length < 8)) {
      alert('Password must be at least 8 characters'); return
    }
    try {
      const payload = { ...form }
      if (password) Object.assign(payload, { password })
      if (editing) {
        await api.updateUser(editing, payload)
      } else {
        await api.createUser(payload)
      }
      setShowForm(false); setEditing(null)
      setForm({ username: '', email: '', role: 'viewer' }); setPassword(''); load()
    } catch (e: any) {
      // Show friendly error from backend validation
      try {
        const errData = JSON.parse(e.message)
        if (Array.isArray(errData.detail)) {
          const msgs = errData.detail.map((d: any) => d.msg).join('\n')
          alert(msgs)
        } else {
          alert(e.message)
        }
      } catch {
        alert(e.message)
      }
    }
  }

  const del = async (id: number) => {
    if (!confirm('CONFIRM DELETION?')) return
    await api.deleteUser(id); load()
  }

  // SSO data loading & mutation
  const loadSso = useCallback(async () => {
    try {
      const [cfg, mappings, envvars] = await Promise.all([
        api.getSsoConfig(),
        api.getSsoRoleMappings(),
        api.getSecretEnvVars(),
      ])
      setSsoCfg(cfg); setSsoMappings(mappings || []); setSecretEnvVars(envvars || [])
    } catch { /* admin-only, let tabs gate access */ }
  }, [])

  const saveSsoConfig = async (patch: Record<string, unknown>) => {
    setSsoSaving(true)
    try {
      const updated = await api.updateSsoConfig(patch)
      setSsoCfg(updated)
    } catch (e: any) {
      alert(e?.message || 'Failed to save SSO config')
    } finally { setSsoSaving(false) }
  }

  const addMapping = async () => {
    if (!newMapping.azure_key.trim()) return
    await api.createSsoRoleMapping(newMapping)
    setNewMapping({ azure_key: '', app_role: 'viewer', priority: 10 })
    await loadSso()
  }

  const removeMapping = async (id: number) => {
    if (!confirm('REMOVE THIS MAPPING?')) return
    await api.deleteSsoRoleMapping(id)
    await loadSso()
  }

  useEffect(() => {
    if (activeTab === 'sso') void Promise.resolve().then(() => loadSso())
  }, [activeTab, loadSso])

  const openForm = (u?: User) => {
    if (u) {
      setEditing(u.id!); setForm({ ...u })
    } else {
      setEditing(null)
      setForm({ username: '', email: '', role: 'viewer' })
    }
    setPassword(''); setShowForm(true)
  }

  const ROLE_COLORS: Record<string, string> = {
    admin: 'var(--red)',
    operator: 'var(--cyan)',
    viewer: 'var(--text-muted)',
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>ACCESS CONTROL</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{t('users.title').toUpperCase()}</h1>
        </div>
        <div style={{ display: 'flex', border: '1px solid var(--border-bright)' }}>
          {(['users', 'sso'] as const).map(t => (
            <button
              key={t}
              onClick={() => setActiveTab(t)}
              style={{
                padding: '8px 20px', fontSize: 12,
                letterSpacing: '0.08em', fontWeight: 600, cursor: 'pointer',
                background: activeTab === t ? 'var(--accent)' : 'var(--bg-surface)',
                color: activeTab === t ? '#000' : 'var(--text-muted)',
                border: 'none', borderRight: t === 'users' ? '1px solid var(--border-bright)' : 'none',
              }}
            >{t === 'users' ? 'USERS' : 'SSO'}</button>
          ))}
        </div>
      </div>

      {/* ── SSO tab ── */}
      {activeTab === 'sso' && (
        <div style={{ marginBottom: 24, display: 'flex', flexDirection: 'column', gap: 24 }}>
          <div style={{ padding: 24, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
            <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: '0.1em', marginBottom: 20, paddingBottom: 16, borderBottom: '1px solid var(--border)', color: 'var(--text-primary)' }}>AZURE AD CONFIGURATION</div>
            {!ssoCfg ? <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>LOADING…</div> : (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <SsoField label="ENABLED" checked={!!ssoCfg.enabled} onChange={v => saveSsoConfig({ enabled: v })} saving={ssoSaving} />
                <div>
                  <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>CLIENT SECRET (ENV)</label>
                  <select
                    value={ssoCfg.secret_env_var_id ?? ''}
                    onChange={e => saveSsoConfig({ secret_env_var_id: e.target.value ? parseInt(e.target.value) : null })}
                    style={{ width: '100%', height: 36, padding: '0 10px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13 }}
                  >
                    <option value="">— NOT SET —</option>
                    {secretEnvVars.map(v => <option key={v.id} value={v.id}>{v.key}</option>)}
                  </select>
                  {ssoCfg.secret_env_var_id ? (
                    <div style={{ fontSize: 11, color: 'var(--green)', marginTop: 4, letterSpacing: '0.05em' }}>✓ Configured via EnvVar</div>
                  ) : (
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>Add a secret EnvVar first</div>
                  )}
                </div>
              <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <SsoInput label="TENANT ID" value={ssoCfg.tenant_id || ''} onChange={v => saveSsoConfig({ tenant_id: v || null })} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                <SsoInput label="CLIENT ID" value={ssoCfg.client_id || ''} onChange={v => saveSsoConfig({ client_id: v || null })} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                <div style={{ gridColumn: '1 / -1' }}><SsoInput label="REDIRECT URI" value={ssoCfg.redirect_uri || ''} onChange={v => saveSsoConfig({ redirect_uri: v || null })} placeholder="https://your-domain/api/v1/auth/sso/callback" /></div>
              </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>DEFAULT ROLE</label>
                  <select value={ssoCfg.default_role} onChange={e => saveSsoConfig({ default_role: e.target.value })} style={{ width: '100%', height: 36, padding: '0 10px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13 }}>
                    {['admin', 'operator', 'analyst', 'viewer', 'auditor'].map(r => <option key={r} value={r}>{r.toUpperCase()}</option>)}
                  </select>
                </div>
                <SsoField label="JIT PROVISIONING" checked={!!ssoCfg.allow_jit} onChange={v => saveSsoConfig({ allow_jit: v })} saving={ssoSaving} />
              </div>
            )}
          </div>
          <div style={{ padding: 24, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
            <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: '0.1em', marginBottom: 20, paddingBottom: 16, borderBottom: '1px solid var(--border)', color: 'var(--text-primary)' }}>AZURE GROUP → APP ROLE MAPPINGS</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: 12, alignItems: 'end', marginBottom: 20 }}>
              <SsoInput label="AZURE KEY" value={newMapping.azure_key} onChange={v => setNewMapping(p => ({ ...p, azure_key: v }))} placeholder="00000000-0000-0000-0000-000000000000" />
              <div>
                <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>APP ROLE</label>
                <select value={newMapping.app_role} onChange={e => setNewMapping(p => ({ ...p, app_role: e.target.value }))} style={{ height: 36, padding: '0 8px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13 }}>
                  {['admin', 'operator', 'analyst', 'viewer', 'auditor'].map(r => <option key={r} value={r}>{r.toUpperCase()}</option>)}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>PRIORITY</label>
                <input type="number" value={newMapping.priority} onChange={e => setNewMapping(p => ({ ...p, priority: parseInt(e.target.value) || 0 }))} style={{ height: 36, width: 80, padding: '0 8px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13 }} />
              </div>
              <button onClick={addMapping} disabled={!newMapping.azure_key.trim()} style={{ height: 36, padding: '0 16px', background: newMapping.azure_key.trim() ? 'var(--accent)' : 'var(--bg-elevated)', border: '1px solid var(--accent-border)', color: newMapping.azure_key.trim() ? '#000' : 'var(--text-muted)', fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', cursor: 'pointer' }}>+ ADD</button>
            </div>
            {ssoMappings.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.06em' }}>NO MAPPINGS — AZURE USERS RECEIVE THE DEFAULT ROLE</div>
            ) : (
              <table className="data-table">
                <thead><tr>
                  {['AZURE KEY', 'APP ROLE', 'PRIORITY', ''].map(h => <th key={h}>{h}</th>)}
                </tr></thead>
                <tbody>{ssoMappings.map(m => (
                  <tr key={m.id}>
                    <td className="font-mono" style={{ fontSize: 12 }}>{m.azure_key}</td>
                    <td style={{ fontSize: 12, color: 'var(--accent)' }}>{m.app_role.toUpperCase()}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{m.priority}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button onClick={() => removeMapping(m.id)} style={{ background: 'none', border: '1px solid var(--red)', color: 'var(--red)', padding: '4px 10px', fontSize: 11, cursor: 'pointer', letterSpacing: '0.06em', borderRadius: 'var(--radius-sm)' }}>REMOVE</button>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── Users tab ── */}
      {activeTab === 'users' && (
        <div>
          {showForm && (
            <div style={{ marginBottom: 24, padding: 24, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 20, paddingBottom: 16, borderBottom: '1px solid var(--border)' }}>
                {editing ? 'UPDATE USER' : 'CREATE USER'}
              </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>USERNAME</label>
              <input value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                className="form-input" />
              <div style={{ fontSize: 11, color: form.username && form.username.trim().length >= 3 ? 'var(--green)' : 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
                {form.username ? (form.username.trim().length >= 3 ? '✓ At least 3 characters' : `✗ ${form.username.trim().length}/3 characters`) : 'Min 3 characters'}
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>EMAIL</label>
              <input type="email" value={form.email || ''} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="form-input" />
              <div style={{ fontSize: 11, color: form.email && form.email.includes('@') ? 'var(--green)' : 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
                {form.email ? (form.email.includes('@') ? '✓ Valid email' : '✗ Must contain @') : 'Must be a valid email'}
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>ROLE</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                className="form-input">
                {ROLES.map(r => <option key={r} value={r}>{r.toUpperCase()}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>{editing ? 'NEW PASSWORD' : 'PASSWORD'}</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder={editing ? 'LEAVE BLANK TO KEEP CURRENT' : ''}
                className="form-input" />
              {editing ? (
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>Leave blank to keep current password</div>
              ) : (
                <div style={{ fontSize: 11, color: password.length >= 8 ? 'var(--green)' : 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
                  {password ? (password.length >= 8 ? `✓ ${password.length} characters` : `✗ ${password.length}/8 characters`) : 'Min 8 characters'}
                </div>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 20 }}>
            <button onClick={() => { setShowForm(false); setEditing(null) }}
              style={{
                padding: '0 16px', height: 36,
                border: '1px solid var(--border-bright)', background: 'transparent',
                color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer',
                              }}>
              CANCEL
            </button>
            <button onClick={submit}
              style={{
                padding: '0 16px', height: 36,
                background: 'var(--accent)', border: '1px solid var(--accent-border)',
                color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em',
                cursor: 'pointer',               }}>
              {editing ? 'SAVE CHANGES' : 'CREATE USER'}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden', borderRadius: 'var(--radius-lg)' }}>
        <table className="data-table">
          <thead>
            <tr>
              {['USERNAME', 'EMAIL', 'ROLE', 'STATUS', 'ACTIONS'].map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 40, fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>LOADING...</td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 40, fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO USERS FOUND</td>
              </tr>
            ) : items.map(u => (
              <tr key={u.id}>
                <td style={{ fontWeight: 600 }}>{u.username}</td>
                <td style={{ color: 'var(--text-muted)' }}>{u.email || '—'}</td>
                <td style={{ padding: '14px 16px' }}>
                  <span style={{
                    display: 'inline-block', padding: '2px 8px',
                    border: `1px solid ${ROLE_COLORS[u.role] || 'var(--border)'}`,
                    color: ROLE_COLORS[u.role] || 'var(--text-muted)',
                    fontSize: 11, letterSpacing: '0.06em', background: 'var(--bg-base)',
                  }}>
                    {u.role.toUpperCase()}
                  </span>
                </td>
                <td style={{ padding: '14px 16px' }}>
                  <span style={{
                    display: 'inline-block', padding: '2px 8px',
                    border: `1px solid ${u.is_active !== false ? 'var(--green)' : 'var(--border)'}`,
                    color: u.is_active !== false ? 'var(--green)' : 'var(--text-dim)',
                    fontSize: 11, letterSpacing: '0.06em',
                    background: u.is_active !== false ? 'rgba(0,255,65,0.05)' : 'transparent',
                  }}>
                    {u.is_active !== false ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                </td>
                <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                  <button onClick={() => openForm(u)}
                    style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none', marginRight: 8 }}>
                    <Edit2 size={12} />
                  </button>
                  <button onClick={() => del(u.id!)}
                    style={{ padding: 4, color: 'var(--red)', cursor: 'pointer', background: 'none', border: 'none' }}>
                    <Trash2 size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
        </div>
      )}
    </div>
  )
}

// ── SSO helper components ───────────────────────────────────────────────────

function SsoField({ label, value, checked, saved, onChange, saving }: {
  label: string; value?: string; checked?: boolean; saved?: boolean;
  onChange?: (v: boolean) => void; saving?: boolean;
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>{label}</label>
      {checked !== undefined && onChange ? (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} disabled={saving} />
          <span style={{ fontSize: 12, color: 'var(--text-primary)', letterSpacing: '0.06em' }}>
            {checked ? 'ON' : 'OFF'}
          </span>
        </label>
      ) : (
        <div style={{ padding: '8px 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', fontSize: 12, color: saved ? 'var(--green)' : 'var(--text-primary)', letterSpacing: '0.05em' }}>
          {value || '—'}
        </div>
      )}
    </div>
  )
}

function SsoInput({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="form-label">{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="form-input" />
    </div>
  )
}
