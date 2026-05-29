import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Wrench, X, Loader2, Link, Upload } from 'lucide-react'

interface Skill {
  id?: string
  name: string
  description?: string
  category?: string
  version?: string
  permission_level?: string
  is_active?: boolean
  metadata_json?: Record<string, any>
}

const CATEGORY_COLORS: Record<string, string> = {
  tool: 'var(--cyan)',
  skill: 'var(--amber)',
  workflow: 'var(--purple)',
  threat_intel: 'var(--red)',
  log_analysis: 'var(--blue)',
  vuln: 'var(--orange)',
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px 0' }}
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{ width: 500, maxHeight: 'calc(100vh - 80px)', background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', padding: 24, overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>{title}</h3>
          <button onClick={onClose} style={{ color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none', padding: 4 }}>
            <X size={14} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export default function Skills() {
  const [items, setItems] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Skill>({ name: '', category: 'tool', description: '', version: '1.0.0', permission_level: 'medium' })
  const [mdContent, setMdContent] = useState('')
  const [showInstallUrl, setShowInstallUrl] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [installUrl, setInstallUrl] = useState('')
  const [installLoading, setInstallLoading] = useState(false)
  const [installError, setInstallError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    try {
      const data = await api.getSkills() as Skill[] | { skills?: Skill[] }
      setItems(Array.isArray(data) ? data : data?.skills || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      const payload = { ...form, md_content: mdContent }
      if (editing) await api.updateSkill(editing, payload)
      else await api.createSkill(payload)
      setShowForm(false); setEditing(null)
      setForm({ name: '', category: 'tool', description: '', version: '1.0.0', permission_level: 'medium' })
      setMdContent('')
      load()
    } catch (e: any) { alert(e.message) }
  }

  const openEdit = (s: Skill) => {
    setEditing(String(s.id))
    setForm({ name: s.name, category: s.category || 'tool', description: s.description || '', version: s.version || '1.0.0', permission_level: s.permission_level || 'medium' })
    setMdContent((s as any).md_content || '')
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
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>AGENT CAPABILITIES</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SKILL POOL</h1>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => setShowInstallUrl(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 36, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
            <Link size={12} /> FROM URL
          </button>
          <button onClick={() => setShowImport(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 36, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
            <Upload size={12} /> IMPORT
          </button>
          <button onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', category: 'tool', description: '', version: '1.0.0', permission_level: 'medium' }); setMdContent('') }}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px', height: 36, background: 'var(--accent)', border: '1px solid var(--accent-border)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)', boxShadow: '0 0 16px rgba(0,255,65,0.15)' }}>
            <Plus size={13} /> NEW SKILL
          </button>
        </div>
      </div>

      {/* Install from URL Modal */}
      {showInstallUrl && (
        <Modal title="INSTALL FROM URL" onClose={() => { setShowInstallUrl(false); setInstallError('') }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>SKILL FILE URL</label>
              <input value={installUrl} onChange={e => setInstallUrl(e.target.value)}
                placeholder="https://raw.githubusercontent.com/.../skill.md"
                onKeyDown={e => e.key === 'Enter' && handleInstallUrl()}
                style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }} />
            </div>
            {installError && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,0,0,0.1)', border: '1px solid var(--red)', fontSize: 13, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>
                {installError}
              </div>
            )}
            <div style={{ padding: '8px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              Paste a raw URL to a markdown skill file. Supports YAML frontmatter for metadata (name, description, version, category). If the skill name already exists, it will be updated.
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => { setShowInstallUrl(false); setInstallError('') }}
                style={{ padding: '0 14px', height: 36, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                CANCEL
              </button>
              <button onClick={handleInstallUrl} disabled={installLoading}
                style={{ padding: '0 14px', height: 36, border: '1px solid var(--accent-border)', background: installLoading ? 'var(--bg-elevated)' : 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.1em', cursor: installLoading ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-mono)' }}>
                {installLoading ? 'INSTALLING...' : 'INSTALL'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Import File Modal */}
      {showImport && (
        <Modal title="IMPORT SKILL FILE" onClose={() => { setShowImport(false); setInstallError('') }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ padding: '20px', background: 'var(--bg-base)', border: '1px dashed var(--border-bright)', textAlign: 'center', cursor: 'pointer' }}
              onClick={() => fileInputRef.current?.click()}>
              <Upload size={24} style={{ color: 'var(--text-dim)', marginBottom: 8 }} />
              <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>Click to select a .md file</div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>or drag and drop</div>
              <input ref={fileInputRef} type="file" accept=".md,.markdown,.json" onChange={handleFileImport} style={{ display: 'none' }} />
            </div>
            {installError && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,0,0,0.1)', border: '1px solid var(--red)', fontSize: 13, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>
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
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>NAME</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. cve-lookup"
                style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>CATEGORY</label>
              <select value={form.category || 'tool'} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }}>
                <option value="tool">TOOL</option>
                <option value="skill">SKILL</option>
                <option value="workflow">WORKFLOW</option>
                <option value="threat_intel">THREAT INTEL</option>
                <option value="log_analysis">LOG ANALYSIS</option>
                <option value="vuln">VULNERABILITY</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>VERSION</label>
              <input value={form.version || '1.0.0'} onChange={e => setForm(f => ({ ...f, version: e.target.value }))}
                placeholder="1.0.0"
                style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>PERMISSION</label>
              <select value={form.permission_level || 'medium'} onChange={e => setForm(f => ({ ...f, permission_level: e.target.value }))}
                style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }}>
                <option value="low">LOW</option>
                <option value="medium">MEDIUM</option>
                <option value="high">HIGH</option>
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>DESCRIPTION</label>
              <input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Skill capability description..."
                style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }} />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>MARKDOWN CONTENT</label>
              <textarea value={mdContent} onChange={e => setMdContent(e.target.value)}
                rows={10}
                placeholder={"# Skill Name\n\nDescribe what this skill does..."}
                style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)', resize: 'vertical' }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 20 }}>
            <button onClick={() => { setShowForm(false); setEditing(null) }}
              style={{ padding: '0 16px', height: 36, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
              CANCEL
            </button>
            <button onClick={submit}
              style={{ padding: '0 16px', height: 36, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
              {editing ? 'SAVE CHANGES' : 'CREATE SKILL'}
            </button>
          </div>
        </div>
      )}

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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {items.map(s => {
            const tc = CATEGORY_COLORS[s.category || ''] || 'var(--text-muted)'
            return (
              <div key={s.id} style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', borderLeft: `3px solid ${tc}` }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, border: '1px solid var(--border-bright)', background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: tc }}>
                      <Wrench size={13} />
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>{s.name}</div>
                  </div>
                  <div style={{ display: 'inline-block', padding: '2px 6px', border: `1px solid ${tc}`, color: tc, fontSize: 10, letterSpacing: '0.15em', background: 'var(--bg-base)' }}>
                    {(s.category || 'tool').toUpperCase()}
                  </div>
                </div>
                <p style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 8 }}>{s.description || '—'}</p>
                {s.version && (
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>v{s.version}</div>
                )}
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>ID: {String(s.id || '').slice(0, 8) || '—'}</span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => openEdit(s)} style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      <Edit2 size={12} />
                    </button>
                    <button onClick={() => del(String(s.id))} style={{ padding: 4, color: 'var(--red)', cursor: 'pointer', background: 'none', border: 'none' }}>
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
