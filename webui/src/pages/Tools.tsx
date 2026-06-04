import { useState, useEffect, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Terminal, X, Loader2 } from 'lucide-react'
import { SearchContext } from '../context/SearchContext'

interface Tool {
  id?: number
  name: string
  description?: string
  category?: string
  version?: string
  permission_level?: string
  is_active?: boolean
  command_template?: string
  input_schema_json?: string
  timeout_seconds?: number
  required_permission?: string
  md_content?: string
  metadata_json?: Record<string, any>
  tags?: string[]
  tagsText?: string
}

const CATEGORY_COLORS: Record<string, string> = {
  tool: 'var(--cyan)',
  skill: 'var(--amber)',
  workflow: 'var(--purple)',
  threat_intel: 'var(--red)',
  log_analysis: 'var(--accent)',
  vuln: 'var(--orange)',
}

// inputStyle removed — using .form-input / .form-textarea CSS classes

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  color: 'var(--text-muted)',
  marginBottom: 6,
  fontFamily: 'var(--font-sans)',
}

export default function Tools() {
  const { t } = useTranslation()
  const [items, setItems] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [tagFilter, setTagFilter] = useState('')
  const [form, setForm] = useState<Tool>({
    name: '',
    category: 'tool',
    description: '',
    version: '1.0.0',
    permission_level: 'medium',
    command_template: '',
    input_schema_json: '',
    timeout_seconds: 60,
    required_permission: '',
    md_content: '',
    tagsText: '',
  })

  const { searchTarget, setSearchTarget } = useContext(SearchContext)

  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'tools') return
    const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('search-highlight')
    const timer = setTimeout(() => {
      el.classList.remove('search-highlight')
      setSearchTarget(null)
    }, 2000)
    return () => clearTimeout(timer)
  }, [searchTarget, setSearchTarget])

  const load = async () => {
    try {
      const data = await api.getTools(tagFilter ? `?tag=${encodeURIComponent(tagFilter)}` : '') as Tool[] | { tools?: Tool[] }
      setItems(Array.isArray(data) ? data : data?.tools || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const resetForm = () => setForm({
    name: '',
    category: 'tool',
    description: '',
    version: '1.0.0',
    permission_level: 'medium',
    command_template: '',
    input_schema_json: '',
    timeout_seconds: 60,
    required_permission: '',
    md_content: '',
    tagsText: '',
  })

  const submit = async () => {
    if (!form.name) return
    try {
      const payload = {
        ...form,
        timeout_seconds: form.timeout_seconds ?? 60,
        // send null/undefined for empty strings so backend treats them as absent
        command_template: form.command_template || undefined,
        input_schema_json: form.input_schema_json || undefined,
        required_permission: form.required_permission || undefined,
        md_content: form.md_content || undefined,
        tags: (form.tagsText || '').split(',').map(s => s.trim()).filter(Boolean),
        tagsText: undefined,
      }
      if (editing != null) await api.updateTool(editing, payload)
      else await api.createTool(payload)
      setShowForm(false); setEditing(null)
      resetForm()
      load()
    } catch (e: any) { alert(e.message) }
  }

  const openEdit = (t: Tool) => {
    setEditing(t.id!)
    setForm({
      name: t.name,
      category: t.category || 'tool',
      description: t.description || '',
      version: t.version || '1.0.0',
      permission_level: t.permission_level || 'medium',
      command_template: t.command_template || '',
      input_schema_json: t.input_schema_json || '',
      timeout_seconds: t.timeout_seconds ?? 60,
      required_permission: t.required_permission || '',
      md_content: (t as any).md_content || '',
      tagsText: (t.tags || []).join(', '),
    })
    setShowForm(true)
  }

  const del = async (id: number) => {
    if (confirm('CONFIRM DELETION?')) {
      try { await api.deleteTool(id); load() }
      catch (e: any) { alert(e.message) }
    }
  }

  const testTool = async (t: Tool) => {
    const raw = prompt(`Args JSON for ${t.name}:`, '{}')
    if (raw == null) return
    try {
      const res: any = await api.executeTool(t.id!, JSON.parse(raw))
      alert(`status: ${res.status}\nexit: ${res.exit_code ?? ''}\n\n${res.stdout || res.error || ''}`)
    } catch (e: any) { alert(e.message) }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>AGENT CAPABILITIES</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{t('tools.title').toUpperCase()}</h1>
        </div>
        <button
          onClick={() => { setShowForm(true); setEditing(null); resetForm() }}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px', height: 36, background: 'var(--accent)', border: '1px solid var(--accent-border)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer', boxShadow: '0 0 16px rgba(0,255,65,0.15)' }}>
          <Plus size={13} /> NEW TOOL
        </button>
      </div>

      {/* Form */}
      {showForm && (
        <div style={{ marginBottom: 24, padding: 24, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>{editing != null ? 'EDIT TOOL' : 'NEW TOOL'}</h3>
            <button onClick={() => { setShowForm(false); setEditing(null) }} style={{ color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none', padding: 4 }}>
              <X size={14} />
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={labelStyle}>NAME</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. nmap-scan"
                className="form-input" />
            </div>
            <div>
              <label style={labelStyle}>CATEGORY</label>
              <select value={form.category || 'tool'} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                className="form-input">
                <option value="tool">TOOL</option>
                <option value="skill">SKILL</option>
                <option value="workflow">WORKFLOW</option>
                <option value="threat_intel">THREAT INTEL</option>
                <option value="log_analysis">LOG ANALYSIS</option>
                <option value="vuln">VULNERABILITY</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>VERSION</label>
              <input value={form.version || '1.0.0'} onChange={e => setForm(f => ({ ...f, version: e.target.value }))}
                placeholder="1.0.0"
                className="form-input" />
            </div>
            <div>
              <label style={labelStyle}>PERMISSION</label>
              <select value={form.permission_level || 'medium'} onChange={e => setForm(f => ({ ...f, permission_level: e.target.value }))}
                className="form-input">
                <option value="low">LOW</option>
                <option value="medium">MEDIUM</option>
                <option value="high">HIGH</option>
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>DESCRIPTION</label>
              <input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Tool capability description..."
                className="form-input" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>COMMAND TEMPLATE</label>
              <input value={form.command_template || ''} onChange={e => setForm(f => ({ ...f, command_template: e.target.value }))}
                placeholder="nmap -sV -p {ports} {target}"
                className="form-input" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>INPUT SCHEMA (JSON)</label>
              <textarea value={form.input_schema_json || ''} onChange={e => setForm(f => ({ ...f, input_schema_json: e.target.value }))}
                rows={4}
                placeholder={'{"type":"object","properties":{"target":{"type":"string"}},"required":["target"]}'}
                className="form-textarea" />
            </div>
            <div>
              <label style={labelStyle}>TIMEOUT (s)</label>
              <input type="number" value={form.timeout_seconds ?? 60} onChange={e => setForm(f => ({ ...f, timeout_seconds: Number(e.target.value) }))}
                min={1} max={3600}
                className="form-input" />
            </div>
            <div>
              <label style={labelStyle}>REQUIRED PERMISSION (optional)</label>
              <input value={form.required_permission || ''} onChange={e => setForm(f => ({ ...f, required_permission: e.target.value }))}
                placeholder="admin:all"
                className="form-input" />
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
                Use a real permission value (e.g. admin:all). Custom strings will deny all callers.
              </div>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>NOTES (optional)</label>
              <textarea value={form.md_content || ''} onChange={e => setForm(f => ({ ...f, md_content: e.target.value }))}
                rows={4}
                placeholder={"# Tool notes\n\nDescribe usage, caveats, examples..."}
                className="form-textarea" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>TAGS (comma-separated)</label>
              <input value={form.tagsText || ''}
                onChange={e => setForm(f => ({ ...f, tagsText: e.target.value }))}
                placeholder="recon, threat-intel"
                className="form-input" />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 20 }}>
            <button onClick={() => { setShowForm(false); setEditing(null) }}
              style={{ padding: '0 16px', height: 36, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer' }}>
              CANCEL
            </button>
            <button onClick={submit}
              style={{ padding: '0 16px', height: 36, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer' }}>
              {editing != null ? 'SAVE CHANGES' : 'CREATE TOOL'}
            </button>
          </div>
        </div>
      )}

      {/* Tag Filter */}
      <div style={{ marginBottom: 16 }}>
        <input value={tagFilter} onChange={e => setTagFilter(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') load() }}
          placeholder="filter by tag…"
          className="form-input" />
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 0', gap: 12 }}>
          <Loader2 size={18} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
          <span style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>LOADING...</span>
        </div>
      )}

      {/* Empty */}
      {!loading && items.length === 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 12 }}>
          <div style={{ width: 48, height: 48, border: '1px solid var(--border-bright)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Terminal size={18} style={{ color: 'var(--text-dim)' }} />
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO TOOLS DEPLOYED</div>
          <button onClick={() => { setShowForm(true); setEditing(null); resetForm() }} style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + DEPLOY FIRST TOOL
          </button>
        </div>
      )}

      {/* Grid */}
      {!loading && items.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {items.map(t => {
            const tc = CATEGORY_COLORS[t.category || ''] || 'var(--text-muted)'
            return (
              <div key={t.id} data-item-id={t.id} className="item-card">
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, border: '1px solid var(--border)', background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: tc, borderRadius: 'var(--radius-md)' }}>
                      <Terminal size={13} />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className="item-card-pip" style={{ background: tc }} />
                      <span className="item-card-title">{t.name}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                    <span className="item-card-badge" style={{ color: tc }}>
                      {(t.category || 'tool').toUpperCase()}
                    </span>
                    {t.command_template && (
                      <span className="item-card-badge" style={{ color: 'var(--cyan)' }}>EXECUTABLE</span>
                    )}
                  </div>
                </div>
                <p className="item-card-desc">{t.description || '—'}</p>
                {t.command_template && (
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    $ {t.command_template}
                  </div>
                )}
                {t.tags && t.tags.length > 0 && (
                  <span style={{ fontSize: 11, color: '#60a5fa' }}>{t.tags.join(', ')}</span>
                )}
                {t.version && (
                  <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>v{t.version}</div>
                )}
                <div className="item-card-actions">
                  <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>ID: {t.id ?? '—'}</span>
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                    {t.command_template && (
                      <button onClick={() => testTool(t)} className="item-card-btn" style={{ color: 'var(--cyan)', borderColor: 'var(--cyan)' }}>
                        TEST
                      </button>
                    )}
                    <button onClick={() => openEdit(t)} className="item-card-icon-btn">
                      <Edit2 size={13} />
                    </button>
                    <button onClick={() => del(t.id!)} className="item-card-icon-btn danger">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
