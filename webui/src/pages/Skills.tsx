import { useState, useEffect, useRef, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Wrench, X, Loader2, Link, Upload } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { SearchContext } from '../context/SearchContext'
import Modal from '../components/Modal'

interface Skill {
  id?: string
  name: string
  description?: string
  category?: string
  version?: string
  permission_level?: string
  is_active?: boolean
  metadata_json?: Record<string, any>
  tags?: string[]
  tagsText?: string
  md_content?: string
}

const CATEGORY_COLORS: Record<string, string> = {
  tool: 'var(--cyan)',
  skill: 'var(--amber)',
  workflow: 'var(--purple)',
  threat_intel: 'var(--red)',
  log_analysis: 'var(--accent)',
  vuln: 'var(--orange)',
}

export default function Skills() {
  const { t } = useTranslation()
  const [items, setItems] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [tagFilter, setTagFilter] = useState('')
  const [form, setForm] = useState<Skill>({ name: '', category: 'tool', description: '', version: '1.0.0', permission_level: 'medium', tagsText: '' })
  const [mdContent, setMdContent] = useState('')
  const [showInstallUrl, setShowInstallUrl] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [installUrl, setInstallUrl] = useState('')
  const [installLoading, setInstallLoading] = useState(false)
  const [installError, setInstallError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { searchTarget, setSearchTarget } = useContext(SearchContext)

  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'skills') return
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
      const data = await api.getSkills(tagFilter ? `?tag=${encodeURIComponent(tagFilter)}` : '') as Skill[] | { skills?: Skill[] }
      setItems(Array.isArray(data) ? data : data?.skills || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      const payload = {
        ...form,
        md_content: mdContent,
        tags: (form.tagsText || '').split(',').map(s => s.trim()).filter(Boolean),
        tagsText: undefined,
      }
      if (editing) await api.updateSkill(editing, payload)
      else await api.createSkill(payload)
      setShowForm(false); setEditing(null)
      setForm({ name: '', category: 'tool', description: '', version: '1.0.0', permission_level: 'medium', tagsText: '' })
      setMdContent('')
      load()
    } catch (e: any) { alert(e.message) }
  }

  const openEdit = (s: Skill) => {
    setEditing(String(s.id))
    setForm({ name: s.name, category: s.category || 'tool', description: s.description || '', version: s.version || '1.0.0', permission_level: s.permission_level || 'medium', tagsText: (s.tags || []).join(', ') })
    setMdContent(s.md_content || '')
    setShowForm(true)
  }

  const del = async (id: string) => { if (confirm('CONFIRM DELETION?')) { await api.deleteSkill(id); load() } }

  const handleInstallUrl = async () => {
    if (!installUrl.trim()) return
    setInstallLoading(true); setInstallError('')
    try {
      const result: any = await api.installSkillFromUrl({ url: installUrl.trim() })
      if (result.success) {
        setShowInstallUrl(false); setInstallUrl(''); load()
      } else {
        setInstallError(result.error || 'Installation failed')
      }
    } catch (e: any) { setInstallError(e.message) }
    finally { setInstallLoading(false) }
  }

  const handleFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setInstallLoading(true); setInstallError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const result: any = await api.importSkillFile(fd)
      if (result.success) {
        setShowImport(false); load()
      } else {
        setInstallError(result.error || 'Import failed')
      }
    } catch (e: any) { setInstallError(e.message) }
    finally { setInstallLoading(false) }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div>
      <PageHeader
        eyebrow="AGENT CAPABILITIES"
        title={t('skills.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <button onClick={() => setShowInstallUrl(true)} className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Link size={12} /> FROM URL
            </button>
            <button onClick={() => setShowImport(true)} className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Upload size={12} /> IMPORT
            </button>
            <button
              onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', category: 'tool', description: '', version: '1.0.0', permission_level: 'medium', tagsText: '' }); setMdContent('') }}
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <Plus size={13} /> NEW SKILL
            </button>
          </div>
        }
      />

      {/* Progressive disclosure for server-managed internal agents */}
      <div
        style={{
          marginBottom: 18,
          padding: '12px 14px',
          border: '1px solid var(--border-bright)',
          background: 'var(--bg-surface)',
          fontSize: 12,
          color: 'var(--text-muted)',
          lineHeight: 1.65,
          letterSpacing: '0.02em',
        }}
      >
        <div style={{ color: 'var(--accent)', fontWeight: 700, letterSpacing: '0.1em', marginBottom: 6, fontSize: 11 }}>
          PROGRESSIVE DISCLOSURE · LOAD_SKILL
        </div>
        <div>
          Internal agents put only <strong style={{ color: 'var(--text-primary)' }}>name + description</strong> in the
          system prompt (catalog). Full Markdown body is fetched on demand via the{' '}
          <code style={{ color: 'var(--cyan)' }}>load_skill</code> tool — never dumped into context up front.
          Write a clear <strong style={{ color: 'var(--text-primary)' }}>DESCRIPTION</strong>: that is what the model
          sees when deciding which SOP to load. Skill text is a procedure, not an authorization override.
        </div>
      </div>

      {/* Install from URL Modal */}
      {showInstallUrl && (
        <Modal width={500} title="INSTALL FROM URL" onClose={() => { setShowInstallUrl(false); setInstallError('') }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label className="form-label">SKILL FILE URL</label>
              <input
                className="form-input"
                value={installUrl}
                onChange={e => setInstallUrl(e.target.value)}
                placeholder="https://www.skills.sh/... or https://raw.githubusercontent.com/.../SKILL.md"
                onKeyDown={e => e.key === 'Enter' && handleInstallUrl()}
              />
            </div>
            {installError && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,0,0,0.1)', border: '1px solid var(--red)', fontSize: 13, color: 'var(--red)' }}>
                {installError}
              </div>
            )}
            <div style={{ padding: '8px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              Paste a raw .md URL, or a skills.sh page URL (e.g. https://www.skills.sh/vercel-labs/skills/find-skills). We auto-resolve to the raw SKILL.md. Supports YAML frontmatter. If the skill name already exists, it will be updated.
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => { setShowInstallUrl(false); setInstallError('') }}
                style={{ padding: '0 14px', height: 36, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em', cursor: 'pointer' }}>
                CANCEL
              </button>
              <button onClick={handleInstallUrl} disabled={installLoading}
                style={{ padding: '0 14px', height: 36, border: '1px solid var(--accent-border)', background: installLoading ? 'var(--bg-elevated)' : 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.1em', cursor: installLoading ? 'not-allowed' : 'pointer' }}>
                {installLoading ? 'INSTALLING...' : 'INSTALL'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Import File Modal */}
      {showImport && (
        <Modal width={500} title="IMPORT SKILL FILE" onClose={() => { setShowImport(false); setInstallError('') }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ padding: '20px', background: 'var(--bg-base)', border: '1px dashed var(--border-bright)', textAlign: 'center', cursor: 'pointer' }}
              onClick={() => fileInputRef.current?.click()}>
              <Upload size={24} style={{ color: 'var(--text-dim)', marginBottom: 8 }} />
              <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>Click to select a .md file</div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>or drag and drop</div>
              <input ref={fileInputRef} type="file" accept=".md,.markdown,.json" onChange={handleFileImport} style={{ display: 'none' }} />
            </div>
            {installError && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,0,0,0.1)', border: '1px solid var(--red)', fontSize: 13, color: 'var(--red)' }}>
                {installError}
              </div>
            )}
            <div style={{ padding: '8px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              Supported formats: .md (markdown with optional YAML frontmatter), .json. If the skill name already exists, it will be updated.
            </div>
          </div>
        </Modal>
      )}

      {/* Form */}
      {showForm && (
        <div style={{ marginBottom: 24, padding: 24, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>{editing ? 'EDIT SKILL' : 'NEW SKILL'}</h3>
            <button onClick={() => { setShowForm(false); setEditing(null) }} style={{ color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none', padding: 4 }}>
              <X size={14} />
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>NAME</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. cve-lookup"
                className="form-input" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>CATEGORY</label>
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
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>VERSION</label>
              <input value={form.version || '1.0.0'} onChange={e => setForm(f => ({ ...f, version: e.target.value }))}
                placeholder="1.0.0"
                className="form-input" />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>PERMISSION</label>
              <select value={form.permission_level || 'medium'} onChange={e => setForm(f => ({ ...f, permission_level: e.target.value }))}
                className="form-input">
                <option value="low">LOW</option>
                <option value="medium">MEDIUM</option>
                <option value="high">HIGH</option>
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>
                DESCRIPTION <span style={{ color: 'var(--amber)' }}>(catalog · always in prompt)</span>
              </label>
              <input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="One-line: when the agent should load this SOP (visible in catalog)"
                className="form-input" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>
                MARKDOWN CONTENT <span style={{ color: 'var(--text-dim)' }}>(body · via load_skill only)</span>
              </label>
              <textarea value={mdContent} onChange={e => setMdContent(e.target.value)}
                rows={10}
                placeholder={"# Skill Name\n\nFull procedure steps… (not injected into system prompt)"}
                className="form-textarea" style={{ minHeight: 120 }} />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>TAGS (comma-separated)</label>
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
              {editing ? 'SAVE CHANGES' : 'CREATE SKILL'}
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
            <Wrench size={18} style={{ color: 'var(--text-dim)' }} />
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO SKILLS DEPLOYED</div>
          <button onClick={() => setShowForm(true)} style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + DEPLOY FIRST SKILL
          </button>
        </div>
      )}

      {/* Grid */}
      {!loading && items.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {items.map(s => {
            const tc = CATEGORY_COLORS[s.category || ''] || 'var(--text-muted)'
            return (
              <div
                key={s.id}
                data-item-id={s.id}
                className="item-card"
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
                    <span className="item-card-pip" style={{ background: tc }} />
                    <div className="item-card-title" style={{ fontSize: 14 }}>{s.name}</div>
                  </div>
                  <div className="item-card-badge" style={{ borderColor: tc, color: tc, background: 'var(--bg-base)' }}>
                    {(s.category || 'tool').toUpperCase()}
                  </div>
                </div>

                <div className="item-card-desc" style={{ marginBottom: 2 }}>{s.description || '— no description (catalog empty)'}</div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span
                    title="Full body loaded via load_skill tool, not system prompt"
                    style={{
                      fontSize: 10,
                      letterSpacing: '0.08em',
                      color: 'var(--cyan)',
                      border: '1px solid var(--border)',
                      padding: '2px 6px',
                    }}
                  >
                    CATALOG → LOAD_SKILL
                  </span>
                  {s.tags && s.tags.length > 0 && (
                    <span style={{ fontSize: 11, color: '#60a5fa' }}>{s.tags.join(', ')}</span>
                  )}
                  {s.version && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>v{s.version}</span>
                  )}
                  {s.md_content && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                      body ~{Math.max(1, Math.round((s.md_content.length || 0) / 100) / 10)}k chars
                    </span>
                  )}
                </div>

                <div className="item-card-actions" style={{ paddingTop: 10, marginTop: 4 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>ID: {String(s.id || '').slice(0, 8) || '—'}</span>
                  <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
                    <button onClick={() => openEdit(s)} className="item-card-icon-btn" title="Edit">
                      <Edit2 size={12} />
                    </button>
                    <button onClick={() => del(String(s.id))} className="item-card-icon-btn danger" title="Delete">
                      <Trash2 size={12} />
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
