import { useState, useEffect, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Clock, X, Loader2 } from 'lucide-react'
import { SearchContext } from '../context/SearchContext'
import PageHeader from '../components/PageHeader'

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
  const { t } = useTranslation()
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

  const { searchTarget, setSearchTarget } = useContext(SearchContext)
  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'schedule') return
    const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('search-highlight')
    }
    const t = setTimeout(() => setSearchTarget(null), 2000)
    return () => clearTimeout(t)
  }, [searchTarget, setSearchTarget])

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
      <PageHeader
        eyebrow="AUTOMATION"
        title={t('schedule.title').toUpperCase()}
        actions={
          <button
            onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', task_type: 'agent_execution', cron_expression: '', is_active: true, task_config: {} }) }}
            className="btn btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: 8 }}
          >
            <Plus size={13} /> NEW TASK
          </button>
        }
      />

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
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>TASK NAME</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Log Analysis"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                                  }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>TYPE</label>
              <select value={form.task_type} onChange={e => setForm(f => ({ ...f, task_type: e.target.value }))}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14,                 }}>
                <option value="agent_execution">AGENT EXECUTION</option>
                <option value="backup">BACKUP</option>
                <option value="report_generation">REPORT GENERATION</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>CRON EXPRESSION</label>
              <input value={form.cron_expression || ''} onChange={e => setForm(f => ({ ...f, cron_expression: e.target.value }))}
                placeholder="0 * * * * (every hour)"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                                  }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>AGENT ID</label>
              <input value={form.agent_id ?? ''} onChange={e => setForm(f => ({ ...f, agent_id: e.target.value ? Number(e.target.value) : undefined }))}
                placeholder="optional"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                                  }} />
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
                border: '1px solid var(--accent-border)', background: 'var(--accent)',
                color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer',
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
        <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 48, gap: 12 }}>
          <div style={{ width: 48, height: 48, border: '1px solid var(--border-bright)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 'var(--radius-md)' }}>
            <Clock size={18} style={{ color: 'var(--text-dim)' }} />
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO SCHEDULED TASKS</div>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {items.map(t => (
            <div key={t.task_id || t.id} data-item-id={t.task_id || t.id} className="item-card">
              {/* Name row with pip + badges */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                  <span className="item-card-pip" style={{ background: t.is_active ? 'var(--accent)' : 'var(--text-dim)' }} />
                  <span className="item-card-title">{t.name}</span>
                </div>
                <span className="item-card-badge" style={{ color: 'var(--cyan)' }}>
                  {t.task_type.toUpperCase()}
                </span>
              </div>

              {/* Status */}
              <div className="item-card-status" style={{ color: t.is_active ? 'var(--accent)' : 'var(--text-dim)' }}>
                {t.is_active ? 'ACTIVE' : 'INACTIVE'}
              </div>

              {/* Cron + next */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {t.cron_expression && (
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>
                    {t.cron_expression}
                  </div>
                )}
                {t.next_run_at && (
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>
                    NEXT: {t.next_run_at}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="item-card-actions">
                <button onClick={() => { setEditing(t.task_id!); setForm({ ...t }); setShowForm(true) }}
                  className="item-card-btn">
                  <Edit2 size={12} /> EDIT
                </button>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                  <button onClick={() => t.task_id && del(t.task_id)} className="item-card-icon-btn danger">
                    <Trash2 size={13} />
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
