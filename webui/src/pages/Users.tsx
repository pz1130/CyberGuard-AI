import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2 } from 'lucide-react'

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
  const [items, setItems] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState<User>({ username: '', email: '', role: 'viewer' })
  const [password, setPassword] = useState('')

  const load = async () => {
    try {
      const data = await api.getUsers() as User[] | { users?: User[] }
      setItems(Array.isArray(data) ? data : data?.users || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

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
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>ACCESS CONTROL</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>USER MANAGEMENT</h1>
        </div>
        <button onClick={() => openForm()}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '0 16px', height: 36,
            background: 'var(--accent)', border: '1px solid var(--accent-border)',
            color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.15em', cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
            boxShadow: '0 0 16px rgba(0,255,65,0.15)',
          }}>
          <Plus size={13} /> NEW USER
        </button>
      </div>

      {/* Form */}
      {showForm && (
        <div style={{ marginBottom: 24, padding: 24, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 20, paddingBottom: 16, borderBottom: '1px solid var(--border)' }}>
            {editing ? 'EDIT USER' : 'CREATE NEW USER'}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>USERNAME</label>
              <input value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
              <div style={{ fontSize: 9, color: form.username && form.username.trim().length >= 3 ? 'var(--green)' : 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
                {form.username ? (form.username.trim().length >= 3 ? '✓ At least 3 characters' : `✗ ${form.username.trim().length}/3 characters`) : 'Min 3 characters'}
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>EMAIL</label>
              <input type="email" value={form.email || ''} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
              <div style={{ fontSize: 9, color: form.email && form.email.includes('@') ? 'var(--green)' : 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
                {form.email ? (form.email.includes('@') ? '✓ Valid email' : '✗ Must contain @') : 'Must be a valid email'}
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>ROLE</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)',
                }}>
                {ROLES.map(r => <option key={r} value={r}>{r.toUpperCase()}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>{editing ? 'NEW PASSWORD' : 'PASSWORD'}</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder={editing ? 'LEAVE BLANK TO KEEP CURRENT' : ''}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
              {editing ? (
                <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>Leave blank to keep current password</div>
              ) : (
                <div style={{ fontSize: 9, color: password.length >= 8 ? 'var(--green)' : 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
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
                color: 'var(--text-muted)', fontSize: 11, letterSpacing: '0.15em', cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
              }}>
              CANCEL
            </button>
            <button onClick={submit}
              style={{
                padding: '0 16px', height: 36,
                background: 'var(--accent)', border: '1px solid var(--accent-border)',
                color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.15em',
                cursor: 'pointer', fontFamily: 'var(--font-mono)',
              }}>
              {editing ? 'SAVE CHANGES' : 'CREATE USER'}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-bright)' }}>
              {['USERNAME', 'EMAIL', 'ROLE', 'STATUS', 'ACTIONS'].map((h, i) => (
                <th key={i} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 40, fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>LOADING...</td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 40, fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO USERS FOUND</td>
              </tr>
            ) : items.map(u => (
              <tr key={u.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '14px 16px', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.05em' }}>{u.username}</td>
                <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-muted)' }}>{u.email || '—'}</td>
                <td style={{ padding: '14px 16px' }}>
                  <span style={{
                    display: 'inline-block', padding: '2px 8px',
                    border: `1px solid ${ROLE_COLORS[u.role] || 'var(--border)'}`,
                    color: ROLE_COLORS[u.role] || 'var(--text-muted)',
                    fontSize: 9, letterSpacing: '0.15em', background: 'var(--bg-base)',
                  }}>
                    {u.role.toUpperCase()}
                  </span>
                </td>
                <td style={{ padding: '14px 16px' }}>
                  <span style={{
                    display: 'inline-block', padding: '2px 8px',
                    border: `1px solid ${u.is_active !== false ? 'var(--green)' : 'var(--border)'}`,
                    color: u.is_active !== false ? 'var(--green)' : 'var(--text-dim)',
                    fontSize: 9, letterSpacing: '0.15em',
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
  )
}
