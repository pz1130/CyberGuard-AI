import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Clock, X, Loader2 } from 'lucide-react'

interface Task {
  id?: number
  task_id?: string
  name: string
  task_type: string
  description?: string
  cron_expression?: string
  agent_id?: number
  task_config?: any
  is_active: boolean
  next_run_at?: string
}

export default function Schedule() {
  const [items, setItems] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Task>({
    name: '',
    task_type: 'agent_execution',
    cron_expression: '',
    is_active: true,
    task_config: {},
  })

  const load = async () => {
    try {
      const data = await api.getScheduledTasks() as Task[] | { tasks?: Task[]; schedules?: Task[] }
      const raw = Array.isArray(data) ? data : (data?.tasks || data?.schedules || [])
      setItems(raw)
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name || !form.cron_expression) return
    const body = {
      name: form.name,
      description: form.description || null,
      cron_expression: form.cron_expression,
      task_type: form.task_type,
      agent_id: form.agent_id ?? null,
      task_config: form.task_config || {},
      is_active: form.is_active,
    }
    try {
      if (editing) await api.updateScheduledTask(editing, body)
      else await api.createScheduledTask(body)
      setShowForm(false); setEditing(null)
      setForm({
        name: '',
        task_type: 'agent_execution',
        cron_expression: '',
        is_active: true,
        task_config: {},
      }); load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: string) => { if (confirm('CONFIRM DELETION?')) { await api.deleteScheduledTask(id); load() } }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>AUTOMATION</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SCHEDULED TASKS</h1>
        </div>
        <button
          onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', task_type: 'agent_execution', cron_expression: '', is_active: true, task_config: {} }) }}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '0 16px', height: 36,
            background: 'var(--accent)', border: '1px solid var(--accent-border)',
            color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em',
            cursor: 'pointer', fontFamily: 'var(--font-mono)',
            boxShadow: '0 0 16px rgba(0,255,65,0.15)',
          }}>
          <Plus size={13} /> NEW TASK
        </button>
      </div>

      {/* Form */}
      {showForm && (
        <div style={{
          marginBottom: 24, padding: 24,
          background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>{editing ? 'EDIT TASK' : 'NEW TASK'}</h3>
            <button onClick={() => { setShowForm(false); setEditing(null) }}
              style={{ color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none', padding: 4 }}>
              <X size={14} />
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>TASK NAME</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Log Analysis"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>TYPE</label>
              <select value={form.task_type} onChange={e => setForm(f => ({ ...f, task_type: e.target.value }))}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)',
                }}>
                <option value="agent_execution">AGENT EXECUTION</option>
                <option value="backup">BACKUP</option>
                <option value="report_generation">REPORT GENERATION</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>CRON EXPRESSION</label>
              <input value={form.cron_expression || ''} onChange={e => setForm(f => ({ ...f, cron_expression: e.target.value }))}
                placeholder="0 * * * * (every hour)"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>AGENT ID</label>
              <input value={form.agent_id ?? ''} onChange={e => setForm(f => ({ ...f, agent_id: e.target.value ? Number(e.target.value) : undefined }))}
                placeholder="optional"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 20 }}>
            <button onClick={() => { setShowForm(false); setEditing(null) }}
              style={{
                padding: '0 16px', height: 36,
                border: '1px solid var(--border-bright)', background: 'transparent',
                color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
              }}>
              CANCEL
            </button>
            <button onClick={submit}
              style={{
                padding: '0 16px', height: 36,
                border: '1px solid var(--accent-border)', background: 'var(--accent)',
                color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
              }}>
              {editing ? 'SAVE CHANGES' : 'CREATE TASK'}
            </button>
          </div>
        </div>
      )}

      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 0', gap: 12 }}>
          <Loader2 size={18} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
          <span style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>LOADING...</span>
        </div>
      )}

      {!loading && items.length === 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 12 }}>
          <div style={{ width: 48, height: 48, border: '1px solid var(--border-bright)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Clock size={18} style={{ color: 'var(--text-dim)' }} />
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO SCHEDULED TASKS</div>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map(t => (
            <div key={t.task_id || t.id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ width: 36, height: 36, border: '1px solid var(--border-bright)', background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
                  <Clock size={14} />
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>{t.name}</span>
                    <span style={{ display: 'inline-block', padding: '2px 6px', border: '1px solid var(--border)', color: 'var(--cyan)', fontSize: 10, letterSpacing: '0.15em', background: 'var(--bg-base)' }}>{t.task_type.toUpperCase()}</span>
                    {t.is_active ? (
                      <span style={{ display: 'inline-block', padding: '2px 6px', border: '1px solid var(--green)', color: 'var(--green)', fontSize: 10, letterSpacing: '0.15em', background: 'rgba(0,255,65,0.05)' }}>ACTIVE</span>
                    ) : (
                      <span style={{ display: 'inline-block', padding: '2px 6px', border: '1px solid var(--border)', color: 'var(--text-dim)', fontSize: 10, letterSpacing: '0.15em', background: 'var(--bg-base)' }}>INACTIVE</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    {t.cron_expression && <span style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>{t.cron_expression}</span>}
                    {t.next_run_at && <span style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>NEXT: {t.next_run_at}</span>}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => { setEditing(t.task_id!); setForm({ ...t }); setShowForm(true) }}
                  style={{ padding: 6, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: '1px solid var(--border-bright)' }}>
                  <Edit2 size={12} />
                </button>
                <button onClick={() => t.task_id && del(t.task_id)}
                  style={{ padding: 6, color: 'var(--red)', cursor: 'pointer', background: 'none', border: '1px solid rgba(255,59,48,0.2)' }}>
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
