import { PermissionButton } from '../components/PermissionButton'
import { useState, useEffect, useRef, useContext, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Wrench, X, Loader2, Link, Upload, FolderArchive } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { SearchContext } from '../context/search'
import { errorMessage } from '../lib/errorMessage'
import Modal from '../components/Modal'

interface Skill {
  id?: string
  name: string
  description?: string
  category?: string
  version?: string
  permission_level?: string
  is_active?: boolean
  metadata_json?: Record<string, unknown>
  tags?: string[]
  tagsText?: string
  md_content?: string
  bundle_file_count?: number
}

interface BundleFile {
  path: string
  size_bytes: number
  mime?: string
  is_binary: boolean
}

interface PromoteForm {
  name: string
  description: string
  command_template: string
  input_schema_json: string
  required_permission: string
  action_category: string
  risk_tier: string
  permission_level: string
  timeout_seconds: number
  script_network: string
  script_network_allowlist: string
}

const EMPTY_PROMOTE_FORM: PromoteForm = {
  name: '', description: '', command_template: '', input_schema_json: '',
  required_permission: '', action_category: 'observe', risk_tier: 'low',
  permission_level: 'medium', timeout_seconds: 60, script_network: 'none',
  script_network_allowlist: '',
}

interface ImportFailure {
  name?: string
  error: string
}

interface ImportResult {
  success?: boolean
  error?: string
  skill?: Skill
  installed?: Skill[]
  failed?: ImportFailure[]
}

interface ImportSummary {
  installed: string[]
  failed: ImportFailure[]
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
  const [importSummary, setImportSummary] = useState<ImportSummary | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [promoteSkill, setPromoteSkill] = useState<Skill | null>(null)
  const [bundleFiles, setBundleFiles] = useState<BundleFile[]>([])
  const [promoteScript, setPromoteScript] = useState('')
  const [promoteSource, setPromoteSource] = useState('')
  const [promoteForm, setPromoteForm] = useState<PromoteForm>(EMPTY_PROMOTE_FORM)
  const [promoteError, setPromoteError] = useState('')
  const [promoteBusy, setPromoteBusy] = useState(false)
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

  const load = useCallback(async () => {
    try {
      const data = await api.getSkills(tagFilter ? `?tag=${encodeURIComponent(tagFilter)}` : '') as Skill[] | { skills?: Skill[] }
      setItems(Array.isArray(data) ? data : data?.skills || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }, [tagFilter])
  useEffect(() => { void Promise.resolve().then(() => load()) }, [load])

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
    } catch (e: unknown) { alert(errorMessage(e)) }
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
      const result = await api.installSkillFromUrl({ url: installUrl.trim() }) as { success?: boolean; error?: string }
      if (result.success) {
        setShowInstallUrl(false); setInstallUrl(''); load()
      } else {
        setInstallError(result.error || 'Installation failed')
      }
    } catch (e: unknown) { setInstallError(errorMessage(e)) }
    finally { setInstallLoading(false) }
  }

  const importFile = async (file: File) => {
    setInstallLoading(true); setInstallError(''); setImportSummary(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const result = await api.importSkillFile(fd) as ImportResult
      if (result.success) {
        const installed = result.installed || (result.skill ? [result.skill] : [])
        load()
        // A bundle can partially succeed, so keep the modal open to show what landed.
        if ((result.failed?.length || 0) > 0) {
          setImportSummary({ installed: installed.map(s => s.name), failed: result.failed || [] })
        } else {
          setShowImport(false)
        }
      } else {
        setInstallError(result.error || 'Import failed')
      }
    } catch (e: unknown) { setInstallError(errorMessage(e)) }
    finally { setInstallLoading(false) }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) await importFile(file)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) await importFile(file)
  }

  const openBundle = async (s: Skill) => {
    setPromoteSkill(s); setPromoteScript(''); setPromoteSource('')
    setPromoteError(''); setPromoteForm(EMPTY_PROMOTE_FORM); setBundleFiles([])
    try {
      const r = await api.getSkillFiles(Number(s.id)) as { files?: BundleFile[] }
      setBundleFiles(r.files || [])
    } catch (e: unknown) { setPromoteError(errorMessage(e)) }
  }

  const selectScript = async (s: Skill, path: string) => {
    setPromoteScript(path); setPromoteError(''); setPromoteSource('')
    try {
      setPromoteSource(await api.getSkillFileContent(Number(s.id), path))
    } catch (e: unknown) { setPromoteError(errorMessage(e)) }
    const interpreter = path.endsWith('.sh') ? 'sh' : 'python3'
    setPromoteForm(f => ({
      ...f,
      name: `${s.name}-${path.split('/').pop()?.replace(/\.(py|sh)$/, '')}`,
      command_template: `${interpreter} ${path}`,
    }))
  }

  const submitPromotion = async () => {
    if (!promoteSkill || !promoteScript) return
    setPromoteError(''); setPromoteBusy(true)
    try {
      await api.promoteSkillScript(Number(promoteSkill.id), promoteScript, {
        ...promoteForm,
        required_permission: promoteForm.required_permission || null,
        input_schema_json: promoteForm.input_schema_json || null,
        script_network_allowlist: promoteForm.script_network === 'allowlist'
          ? promoteForm.script_network_allowlist.split('\n').map(h => h.trim()).filter(Boolean)
          : null,
      })
      setPromoteSkill(null)
    } catch (e: unknown) { setPromoteError(errorMessage(e)) }
    finally { setPromoteBusy(false) }
  }

  return (
    <div>
      <PageHeader
        eyebrow="AGENT CAPABILITIES"
        title={t('skills.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <PermissionButton permission="skill:write" onClick={() => setShowInstallUrl(true)} className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Link size={12} /> FROM URL
            </PermissionButton>
            <PermissionButton permission="skill:write" onClick={() => setShowImport(true)} className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Upload size={12} /> IMPORT
            </PermissionButton>
            <PermissionButton permission="skill:write"
              onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', category: 'tool', description: '', version: '1.0.0', permission_level: 'medium', tagsText: '' }); setMdContent('') }}
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <Plus size={13} /> NEW SKILL
            </PermissionButton>
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
              <PermissionButton permission="skill:write" onClick={handleInstallUrl} disabled={installLoading}
                style={{ padding: '0 14px', height: 36, border: '1px solid var(--accent-border)', background: installLoading ? 'var(--bg-elevated)' : 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.1em', cursor: installLoading ? 'not-allowed' : 'pointer' }}>
                {installLoading ? 'INSTALLING...' : 'INSTALL'}
              </PermissionButton>
            </div>
          </div>
        </Modal>
      )}

      {/* Import File Modal */}
      {showImport && (
        <Modal width={500} title="IMPORT SKILL FILE" onClose={() => { setShowImport(false); setInstallError(''); setImportSummary(null) }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div
              style={{
                padding: '20px',
                background: dragOver ? 'var(--bg-elevated)' : 'var(--bg-base)',
                border: `1px dashed ${dragOver ? 'var(--accent)' : 'var(--border-bright)'}`,
                textAlign: 'center',
                cursor: installLoading ? 'wait' : 'pointer',
                opacity: installLoading ? 0.6 : 1,
              }}
              onClick={() => !installLoading && fileInputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              {installLoading
                ? <Loader2 size={24} style={{ color: 'var(--accent)', marginBottom: 8, animation: 'spin 1s linear infinite' }} />
                : <Upload size={24} style={{ color: 'var(--text-dim)', marginBottom: 8 }} />}
              <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>
                {installLoading ? t('skills.importing') : t('skills.importPick')}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>{t('skills.importDrop')}</div>
              <input ref={fileInputRef} type="file" accept=".md,.markdown,.json,.zip" onChange={handleFileImport} style={{ display: 'none' }} />
            </div>
            {installError && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,0,0,0.1)', border: '1px solid var(--red)', fontSize: 13, color: 'var(--red)' }}>
                {installError}
              </div>
            )}
            {importSummary && (
              <div style={{ padding: '8px 10px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', fontSize: 12, lineHeight: 1.6 }}>
                <div style={{ color: 'var(--accent)' }}>
                  {t('skills.importInstalled', { count: importSummary.installed.length })}
                  {importSummary.installed.length > 0 && `: ${importSummary.installed.join(', ')}`}
                </div>
                {importSummary.failed.map((f, i) => (
                  <div key={i} style={{ color: 'var(--red)' }}>{f.name || '?'}: {f.error}</div>
                ))}
              </div>
            )}
            <div style={{ padding: '8px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              {t('skills.importHint')}
            </div>
          </div>
        </Modal>
      )}

      {/* Promote bundle script to tool */}
      {promoteSkill && (
        <Modal width={720} title={t('skills.promoteTitle').toUpperCase()}
          onClose={() => { setPromoteSkill(null); setPromoteError('') }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              {t('skills.promoteReview')}
            </div>
            {bundleFiles.filter(f => /\.(py|sh)$/.test(f.path)).length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {t('skills.promoteNoScripts')}
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {bundleFiles.filter(f => /\.(py|sh)$/.test(f.path)).map(f => (
                  <button key={f.path} onClick={() => selectScript(promoteSkill, f.path)}
                    className={promoteScript === f.path ? 'btn btn-primary' : 'btn btn-secondary'}
                    style={{ fontSize: 11, height: 24, padding: '0 8px' }}>
                    {f.path}
                  </button>
                ))}
              </div>
            )}
            {promoteScript && (
              <>
                <pre style={{
                  maxHeight: 240, overflow: 'auto', background: 'var(--bg-base)',
                  border: '1px solid var(--border)', padding: 10, fontSize: 12, margin: 0,
                }}>{promoteSource}</pre>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label className="form-label">NAME</label>
                    <input className="form-input" value={promoteForm.name}
                      onChange={e => setPromoteForm(f => ({ ...f, name: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">COMMAND TEMPLATE</label>
                    <input className="form-input" value={promoteForm.command_template}
                      onChange={e => setPromoteForm(f => ({ ...f, command_template: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">ACTION CATEGORY</label>
                    <input className="form-input" value={promoteForm.action_category}
                      onChange={e => setPromoteForm(f => ({ ...f, action_category: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">RISK TIER</label>
                    <input className="form-input" value={promoteForm.risk_tier}
                      onChange={e => setPromoteForm(f => ({ ...f, risk_tier: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">{t('skills.promoteNetwork').toUpperCase()}</label>
                    <select className="form-input" value={promoteForm.script_network}
                      onChange={e => setPromoteForm(f => ({ ...f, script_network: e.target.value }))}>
                      <option value="none">{t('skills.promoteNetworkNone')}</option>
                      <option value="allowlist">{t('skills.promoteNetworkAllowlist')}</option>
                    </select>
                  </div>
                  <div />
                  {promoteForm.script_network === 'allowlist' && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label className="form-label">{t('skills.promoteAllowlist').toUpperCase()}</label>
                      <textarea className="form-input" rows={3}
                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                        value={promoteForm.script_network_allowlist}
                        placeholder={'vendor.example\n.api.vendor.example'}
                        onChange={e => setPromoteForm(f => ({
                          ...f, script_network_allowlist: e.target.value }))} />
                      <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4, lineHeight: 1.6 }}>
                        {t('skills.promoteAllowlistHint')}
                      </div>
                    </div>
                  )}
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label className="form-label">INPUT SCHEMA (JSON)</label>
                    <input className="form-input" value={promoteForm.input_schema_json}
                      placeholder='{"properties": {"target": {"type": "string"}}}'
                      onChange={e => setPromoteForm(f => ({ ...f, input_schema_json: e.target.value }))} />
                  </div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--amber)', lineHeight: 1.6 }}>
                  {t('skills.promoteDigestNote')}
                </div>
              </>
            )}
            {promoteError && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,0,0,0.1)',
                border: '1px solid var(--red)', fontSize: 13, color: 'var(--red)' }}>
                {promoteError}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <PermissionButton permission="skill:script_approve" onClick={submitPromotion} disabled={!promoteScript || promoteBusy}
                className="btn btn-primary">
                {promoteBusy ? '...' : t('skills.promote').toUpperCase()}
              </PermissionButton>
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
            <PermissionButton permission="skill:write" onClick={submit}
              style={{ padding: '0 16px', height: 36, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer' }}>
              {editing ? 'SAVE CHANGES' : 'CREATE SKILL'}
            </PermissionButton>
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
          <PermissionButton permission="skill:write" onClick={() => setShowForm(true)} style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + DEPLOY FIRST SKILL
          </PermissionButton>
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
                  {!!s.bundle_file_count && (
                    <button
                      onClick={() => openBundle(s)}
                      title={t('skills.bundleFilesTitle')}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4, fontSize: 11,
                        color: 'var(--cyan)', background: 'transparent',
                        border: '1px solid var(--border-bright)', padding: '1px 6px',
                        cursor: 'pointer',
                      }}>
                      <FolderArchive size={11} /> {t('skills.bundleFiles', { count: s.bundle_file_count })}
                    </button>
                  )}
                </div>

                <div className="item-card-actions" style={{ paddingTop: 10, marginTop: 4 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>ID: {String(s.id || '').slice(0, 8) || '—'}</span>
                  <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
                    <PermissionButton permission="skill:write" onClick={() => openEdit(s)} className="item-card-icon-btn" title="Edit">
                      <Edit2 size={12} />
                    </PermissionButton>
                    <PermissionButton permission="skill:write" onClick={() => del(String(s.id))} className="item-card-icon-btn danger" title="Delete">
                      <Trash2 size={12} />
                    </PermissionButton>
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
