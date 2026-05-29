import { useEffect, useMemo, useState } from 'react'
import {
  Plus, Trash2, Sparkles, FileText, X, Save, Check,
  ChevronRight, ChevronDown, ArrowLeft, Wand2, BookOpen, ClipboardList,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api/client'

type ReqStatus = 'not_assessed' | 'compliant' | 'partially_compliant' | 'non_compliant' | 'not_applicable'
type AsmtStatus = 'planning' | 'in_progress' | 'completed' | 'archived'

interface Framework {
  id: number
  urn: string
  name: string
  version: string | null
  description: string | null
  requirement_count: number
  is_active: boolean
}

interface Requirement {
  id: number
  framework_id: number
  parent_id: number | null
  urn: string
  ref_id: string
  name: string
  description: string | null
  depth: number
  order_index: number
  is_assessable: boolean
  typical_evidence: string[] | null
}

interface Evidence {
  id: number
  name: string
  description: string | null
  kind: 'file' | 'url' | 'text'
  url: string | null
  body: string | null
  uploaded_at: string
}

interface ReqAssessment {
  id: number
  assessment_id: number
  requirement_id: number
  status: ReqStatus
  score: number | null
  observation: string | null
  ai_recommendation: string | null
  ai_assessed_at: string | null
  updated_at: string
  requirement: Requirement | null
  evidences: Evidence[]
}

interface AssessmentSummary {
  id: number
  name: string
  description: string | null
  framework_id: number
  framework_name: string | null
  scope: string | null
  status: AsmtStatus
  start_date: string | null
  due_date: string | null
  created_at: string
  updated_at: string
  progress: {
    total: number
    assessed: number
    compliant: number
    partially_compliant: number
    non_compliant: number
    not_applicable: number
    not_assessed: number
    percent: number
  } | null
}

const STATUS_COLORS: Record<ReqStatus, string> = {
  not_assessed: 'var(--text-dim)',
  compliant: 'var(--accent)',
  partially_compliant: 'var(--amber, #ffb000)',
  non_compliant: 'var(--red)',
  not_applicable: 'var(--text-muted)',
}

const STATUS_LABELS: Record<ReqStatus, string> = {
  not_assessed: 'NOT ASSESSED',
  compliant: 'COMPLIANT',
  partially_compliant: 'PARTIAL',
  non_compliant: 'NON-COMPLIANT',
  not_applicable: 'N/A',
}

const ASMT_STATUS_LABELS: Record<AsmtStatus, string> = {
  planning: 'PLANNING',
  in_progress: 'IN PROGRESS',
  completed: 'COMPLETED',
  archived: 'ARCHIVED',
}

type View =
  | { kind: 'list' }
  | { kind: 'detail'; assessmentId: number }
  | { kind: 'frameworks' }

export default function Governance() {
  const [view, setView] = useState<View>({ kind: 'list' })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 20, letterSpacing: '0.15em', color: 'var(--text-primary)' }}>GOVERNANCE</div>
          <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-dim)', marginTop: 4 }}>
            合规框架 · 审计 · 证据 · AI 评估
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => setView({ kind: 'list' })}
            style={tabButton(view.kind === 'list')}>
            <ClipboardList size={11} /> ASSESSMENTS
          </button>
          <button onClick={() => setView({ kind: 'frameworks' })}
            style={tabButton(view.kind === 'frameworks')}>
            <BookOpen size={11} /> FRAMEWORKS
          </button>
        </div>
      </div>

      {view.kind === 'list' && <AssessmentsList onOpen={(id) => setView({ kind: 'detail', assessmentId: id })} />}
      {view.kind === 'frameworks' && <FrameworksList />}
      {view.kind === 'detail' && <AssessmentDetail
        assessmentId={view.assessmentId}
        onBack={() => setView({ kind: 'list' })}
      />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Frameworks list
// ---------------------------------------------------------------------------

function FrameworksList() {
  const [items, setItems] = useState<Framework[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [importJson, setImportJson] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getFrameworks() as Framework[]
      setItems(data || [])
    } catch (e: any) {
      alert(e.message || 'load failed')
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const doImport = async () => {
    try {
      const body = JSON.parse(importJson)
      await api.importFramework(body)
      setImporting(false)
      setImportJson('')
      await load()
    } catch (e: any) {
      alert(e.message || 'Import failed — check JSON shape')
    }
  }

  const remove = async (f: Framework) => {
    if (!confirm(`Delete framework "${f.name}"? Assessments referencing it must be removed first.`)) return
    try { await api.deleteFramework(f.id); await load() }
    catch (e: any) { alert(e.message) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={() => setImporting(true)} style={primaryButton()}>
          <Plus size={12} /> IMPORT FRAMEWORK
        </button>
      </div>

      {loading ? <Loading /> : items.length === 0 ? (
        <Empty hint="NO FRAMEWORKS — IMPORT ONE OR RESTART SERVER TO LOAD DEFAULTS (ISO 27001:2022, NIST CSF 2.0)" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 12 }}>
          {items.map(f => (
            <div key={f.id} style={card()}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 15, color: 'var(--text-primary)', fontWeight: 600 }}>{f.name}</div>
                <button onClick={() => remove(f)} style={iconButton('var(--red)')}><Trash2 size={12} /></button>
              </div>
              {f.version && <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>VERSION {f.version}</div>}
              <div style={{ fontSize: 12, color: 'var(--accent)', letterSpacing: '0.1em' }}>{f.requirement_count} REQUIREMENTS</div>
              {f.description && <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5 }}>{f.description}</div>}
              <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>{f.urn}</div>
            </div>
          ))}
        </div>
      )}

      {importing && (
        <Modal onClose={() => setImporting(false)} title="+ IMPORT FRAMEWORK (JSON)">
          <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 8 }}>
            Required: <code>{`{ urn, name, requirements: [{ ref_id, name, parent_ref_id? }] }`}</code>.
            Use <code>"replace_existing": true</code> to overwrite by urn.
          </div>
          <textarea value={importJson} onChange={e => setImportJson(e.target.value)}
            placeholder={`{\n  "urn": "urn:mycompany:fw:custom-1",\n  "name": "My Custom Framework",\n  "version": "1.0",\n  "requirements": [\n    { "ref_id": "1", "name": "Top" },\n    { "ref_id": "1.1", "name": "Sub", "parent_ref_id": "1" }\n  ]\n}`}
            rows={20}
            style={{ ...textareaStyle(), minHeight: 360 }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 10 }}>
            <button onClick={() => setImporting(false)} style={ghostButton()}>CANCEL</button>
            <button onClick={doImport} style={primaryButton()}><Save size={12} /> IMPORT</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Assessments list + create
// ---------------------------------------------------------------------------

function AssessmentsList({ onOpen }: { onOpen: (id: number) => void }) {
  const [items, setItems] = useState<AssessmentSummary[]>([])
  const [frameworks, setFrameworks] = useState<Framework[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({ name: '', description: '', framework_id: 0, scope: '' })

  const load = async () => {
    setLoading(true)
    try {
      const [a, f] = await Promise.all([
        api.getAssessments() as Promise<AssessmentSummary[]>,
        api.getFrameworks() as Promise<Framework[]>,
      ])
      setItems(a || [])
      setFrameworks(f || [])
    } catch (e: any) {
      alert(e.message || 'load failed')
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const create = async () => {
    if (!draft.name.trim() || !draft.framework_id) {
      alert('Name and framework are required')
      return
    }
    try {
      const created = await api.createAssessment({
        name: draft.name.trim(),
        description: draft.description.trim() || undefined,
        framework_id: draft.framework_id,
        scope: draft.scope.trim() || undefined,
      }) as AssessmentSummary
      setCreating(false)
      setDraft({ name: '', description: '', framework_id: 0, scope: '' })
      onOpen(created.id)
    } catch (e: any) {
      alert(e.message || 'create failed')
    }
  }

  const remove = async (a: AssessmentSummary) => {
    if (!confirm(`Delete assessment "${a.name}"?`)) return
    try { await api.deleteAssessment(a.id); await load() }
    catch (e: any) { alert(e.message) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={() => setCreating(true)} disabled={frameworks.length === 0}
          title={frameworks.length === 0 ? 'Import a framework first' : ''}
          style={{ ...primaryButton(), opacity: frameworks.length === 0 ? 0.5 : 1 }}>
          <Plus size={12} /> NEW ASSESSMENT
        </button>
      </div>

      {loading ? <Loading /> : items.length === 0 ? (
        <Empty hint='NO ASSESSMENTS — CLICK "NEW ASSESSMENT" TO START AN AUDIT' />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(a => (
            <div key={a.id} onClick={() => onOpen(a.id)} style={{
              ...card(), cursor: 'pointer', flexDirection: 'row', alignItems: 'center',
            }}>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 16, color: 'var(--text-primary)', fontWeight: 600 }}>{a.name}</span>
                  <span style={statusBadge(a.status)}>{ASMT_STATUS_LABELS[a.status]}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                  {a.framework_name} {a.scope ? `· ${a.scope}` : ''}
                </div>
                <ProgressBar progress={a.progress} />
              </div>
              <button onClick={(e) => { e.stopPropagation(); remove(a) }} style={iconButton('var(--red)')}><Trash2 size={12} /></button>
            </div>
          ))}
        </div>
      )}

      {creating && (
        <Modal onClose={() => setCreating(false)} title="+ NEW COMPLIANCE ASSESSMENT">
          <Field label="NAME">
            <input value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
              placeholder="e.g. ISO 27001 - Production AWS - Q3 2026"
              style={inputStyle()}
            />
          </Field>
          <Field label="FRAMEWORK">
            <select value={draft.framework_id} onChange={e => setDraft(d => ({ ...d, framework_id: Number(e.target.value) }))}
              style={inputStyle()}>
              <option value={0}>— Select framework —</option>
              {frameworks.map(f => <option key={f.id} value={f.id}>{f.name} ({f.requirement_count})</option>)}
            </select>
          </Field>
          <Field label="SCOPE (optional)">
            <input value={draft.scope} onChange={e => setDraft(d => ({ ...d, scope: e.target.value }))}
              placeholder="e.g. Production AWS account, customer-facing services"
              style={inputStyle()}
            />
          </Field>
          <Field label="DESCRIPTION (optional)">
            <textarea value={draft.description} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))}
              rows={3} style={textareaStyle()}
            />
          </Field>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 10 }}>
            <button onClick={() => setCreating(false)} style={ghostButton()}>CANCEL</button>
            <button onClick={create} style={primaryButton()}><Save size={12} /> CREATE</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Assessment detail
// ---------------------------------------------------------------------------

function AssessmentDetail({ assessmentId, onBack }: { assessmentId: number; onBack: () => void }) {
  const [summary, setSummary] = useState<AssessmentSummary | null>(null)
  const [items, setItems] = useState<ReqAssessment[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | ReqStatus>('all')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [reportOpen, setReportOpen] = useState(false)
  const [reportMd, setReportMd] = useState('')
  const [reportLoading, setReportLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [s, r] = await Promise.all([
        api.getAssessment(assessmentId) as Promise<AssessmentSummary>,
        api.getAssessmentRequirements(assessmentId) as Promise<ReqAssessment[]>,
      ])
      setSummary(s)
      setItems(r || [])
    } catch (e: any) {
      alert(e.message || 'load failed')
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [assessmentId])

  const toggle = (id: number) => setExpanded(s => {
    const next = new Set(s)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const filtered = useMemo(() => {
    if (filter === 'all') return items
    return items.filter(i => i.status === filter)
  }, [items, filter])

  const updateItem = (raId: number, patch: Partial<ReqAssessment>) => {
    setItems(prev => prev.map(it => it.id === raId ? { ...it, ...patch } : it))
  }

  const generateReport = async () => {
    setReportOpen(true)
    setReportLoading(true)
    setReportMd('')
    try {
      const resp = await api.aiGenerateReport(assessmentId) as { markdown: string }
      setReportMd(resp.markdown || '')
    } catch (e: any) {
      setReportMd(`⚠ Report generation failed: ${e.message || 'unknown error'}`)
    } finally {
      setReportLoading(false)
    }
  }

  if (loading || !summary) return <Loading />

  const p = summary.progress

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <button onClick={onBack} style={{
        ...ghostButton(), alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 4,
      }}>
        <ArrowLeft size={12} /> BACK
      </button>

      {/* Header card */}
      <div style={{ ...card(), padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <span style={{ fontSize: 18, color: 'var(--text-primary)', fontWeight: 600 }}>{summary.name}</span>
          <span style={statusBadge(summary.status)}>{ASMT_STATUS_LABELS[summary.status]}</span>
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          {summary.framework_name} {summary.scope ? `· ${summary.scope}` : ''}
        </div>
        {summary.description && <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>{summary.description}</div>}
        <div style={{ marginTop: 10 }}><ProgressBar progress={p} /></div>
        {p && (
          <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 6, letterSpacing: '0.05em' }}>
            ✅ {p.compliant} · ◐ {p.partially_compliant} · ✗ {p.non_compliant} · — {p.not_applicable} · ◌ {p.not_assessed}
          </div>
        )}
        <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
          <button onClick={generateReport} style={primaryButton()}>
            <Sparkles size={12} /> AI REPORT
          </button>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginRight: 4 }}>FILTER</span>
        {(['all', 'not_assessed', 'compliant', 'partially_compliant', 'non_compliant', 'not_applicable'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={chipButton(filter === f)}>
            {f === 'all' ? 'ALL' : STATUS_LABELS[f as ReqStatus]}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-dim)' }}>
          {filtered.length}/{items.length}
        </span>
      </div>

      {/* Requirement list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {filtered.map(ra => (
          <RequirementRow key={ra.id}
            ra={ra}
            expanded={expanded.has(ra.id)}
            onToggle={() => toggle(ra.id)}
            onUpdate={(patch) => updateItem(ra.id, patch)}
          />
        ))}
        {filtered.length === 0 && <Empty hint="NO REQUIREMENTS MATCH FILTER" />}
      </div>

      {/* Report modal */}
      {reportOpen && (
        <Modal onClose={() => setReportOpen(false)} title="◆ AI AUDIT REPORT" wide>
          {reportLoading ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
              <div style={{ display: 'inline-block', width: 14, height: 14, border: '1px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              <div style={{ marginTop: 12, fontSize: 13, letterSpacing: '0.15em' }}>GENERATING...</div>
            </div>
          ) : (
            <div style={{
              maxHeight: '60vh', overflowY: 'auto',
              background: 'var(--bg-base)', border: '1px solid var(--border)',
              padding: 16, fontSize: 14, lineHeight: 1.7,
            }}>
              <ReactMarkdown>{reportMd}</ReactMarkdown>
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
            <button onClick={async () => {
              try { await navigator.clipboard.writeText(reportMd); alert('Copied') }
              catch { /* ignore */ }
            }} style={ghostButton()} disabled={!reportMd}>COPY MARKDOWN</button>
            <button onClick={() => setReportOpen(false)} style={primaryButton()}>CLOSE</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function RequirementRow({
  ra, expanded, onToggle, onUpdate,
}: {
  ra: ReqAssessment
  expanded: boolean
  onToggle: () => void
  onUpdate: (patch: Partial<ReqAssessment>) => void
}) {
  const req = ra.requirement
  if (!req) return null
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({
    status: ra.status as ReqStatus,
    score: ra.score ?? null,
    observation: ra.observation || '',
  })
  const [aiLoading, setAiLoading] = useState<'suggest' | 'assess' | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [newEvidence, setNewEvidence] = useState({ name: '', body: '', kind: 'text' as 'text' | 'url', url: '' })
  const [addingEv, setAddingEv] = useState(false)
  const [savingEv, setSavingEv] = useState(false)

  const save = async () => {
    try {
      const updated = await api.updateRequirementAssessment(ra.id, draft) as ReqAssessment
      onUpdate({ status: updated.status, score: updated.score, observation: updated.observation, updated_at: updated.updated_at })
      setEditing(false)
    } catch (e: any) { alert(e.message) }
  }

  const aiSuggest = async () => {
    setAiLoading('suggest')
    try {
      const r = await api.aiSuggestEvidence(ra.id) as { suggestions: string[] }
      setSuggestions(r.suggestions || [])
    } catch (e: any) { alert(e.message) }
    finally { setAiLoading(null) }
  }

  const aiAssess = async (apply: boolean) => {
    setAiLoading('assess')
    try {
      const r = await api.aiAssessRequirement(ra.id, { apply }) as { status: ReqStatus; score: number | null; observation: string; applied: boolean }
      if (apply) {
        setDraft({ status: r.status, score: r.score, observation: r.observation })
        onUpdate({ status: r.status, score: r.score, observation: r.observation, ai_recommendation: `status=${r.status} score=${r.score}\n${r.observation}`, ai_assessed_at: new Date().toISOString() })
      } else {
        onUpdate({ ai_recommendation: `status=${r.status} score=${r.score}\n${r.observation}`, ai_assessed_at: new Date().toISOString() })
        alert(`AI verdict: ${r.status} (score ${r.score ?? '—'})\n\n${r.observation}\n\n(Not applied — open the row and re-run with "Apply" to save.)`)
      }
    } catch (e: any) { alert(e.message) }
    finally { setAiLoading(null) }
  }

  const addEvidence = async () => {
    if (!newEvidence.name.trim()) { alert('Name is required'); return }
    if (newEvidence.kind === 'text' && !newEvidence.body.trim()) { alert('Body is required for text evidence'); return }
    if (newEvidence.kind === 'url' && !newEvidence.url.trim()) { alert('URL is required'); return }
    setSavingEv(true)
    try {
      const ev = await api.addEvidence(ra.id, {
        name: newEvidence.name.trim(),
        kind: newEvidence.kind,
        body: newEvidence.kind === 'text' ? newEvidence.body : undefined,
        url: newEvidence.kind === 'url' ? newEvidence.url : undefined,
      }) as Evidence
      onUpdate({ evidences: [ev, ...ra.evidences] })
      setNewEvidence({ name: '', body: '', kind: 'text', url: '' })
      setAddingEv(false)
    } catch (e: any) { alert(e.message) }
    finally { setSavingEv(false) }
  }

  const deleteEv = async (ev: Evidence) => {
    if (!confirm(`Delete evidence "${ev.name}"?`)) return
    try {
      await api.deleteEvidence(ev.id)
      onUpdate({ evidences: ra.evidences.filter(e => e.id !== ev.id) })
    } catch (e: any) { alert(e.message) }
  }

  const indent = req.depth * 12

  return (
    <div style={{
      border: '1px solid var(--border)', background: 'var(--bg-surface)',
      paddingLeft: indent,
    }}>
      {/* Row header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 12px', cursor: 'pointer',
      }} onClick={onToggle}>
        <button onClick={(e) => { e.stopPropagation(); onToggle() }}
          style={iconButton('var(--text-muted)')}>
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
        <span style={{ fontSize: 12, color: 'var(--accent)', fontFamily: 'var(--font-mono)', minWidth: 70 }}>{req.ref_id}</span>
        <span style={{ flex: 1, fontSize: 14, color: 'var(--text-primary)' }}>{req.name}</span>
        {ra.evidences.length > 0 && (
          <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>{ra.evidences.length} EVIDENCE</span>
        )}
        <span style={{ ...statusBadge(ra.status, true), color: STATUS_COLORS[ra.status], borderColor: STATUS_COLORS[ra.status] }}>
          {STATUS_LABELS[ra.status]}
          {ra.score != null && ` · ${ra.score}`}
        </span>
      </div>

      {expanded && (
        <div style={{ padding: '0 14px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10, borderTop: '1px solid var(--border)' }}>
          {req.description && (
            <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5, marginTop: 10 }}>{req.description}</div>
          )}

          {/* Standard evidence checklist (from framework definition) */}
          {req.typical_evidence && req.typical_evidence.length > 0 && (
            <div style={{ padding: '8px 10px', border: '1px solid var(--border-bright)', background: 'var(--bg-base)' }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: 6,
              }}>
                <span style={{ fontSize: 12, letterSpacing: '0.15em', color: 'var(--text-muted)' }}>
                  ◆ STANDARD EVIDENCE CHECKLIST
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>
                  FROM FRAMEWORK
                </span>
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.7 }}>
                {req.typical_evidence.map((s, i) => (
                  <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 2 }}>
                    <span style={{ flex: 1 }}>{s}</span>
                    <button
                      onClick={() => {
                        setNewEvidence({ name: s.slice(0, 80), body: '', kind: 'text', url: '' })
                        setAddingEv(true)
                      }}
                      title="Pre-fill 'Add evidence' with this item"
                      style={{
                        padding: '0 6px', fontSize: 11, letterSpacing: '0.1em',
                        background: 'transparent', border: '1px solid var(--border-bright)',
                        color: 'var(--text-dim)', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                        height: 18, flexShrink: 0,
                      }}
                    >USE</button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Status / observation editor */}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 4 }}>
            <span style={{ fontSize: 11, letterSpacing: '0.15em', color: 'var(--text-dim)' }}>STATUS</span>
            <select value={editing ? draft.status : ra.status}
              disabled={!editing}
              onChange={e => setDraft(d => ({ ...d, status: e.target.value as ReqStatus }))}
              style={{ ...inputStyle(), height: 26, width: 180 }}>
              {(['not_assessed','compliant','partially_compliant','non_compliant','not_applicable'] as const).map(s =>
                <option key={s} value={s}>{STATUS_LABELS[s]}</option>
              )}
            </select>
            <span style={{ fontSize: 11, letterSpacing: '0.15em', color: 'var(--text-dim)' }}>SCORE</span>
            <input type="number" min={0} max={100}
              disabled={!editing}
              value={editing ? (draft.score ?? '') : (ra.score ?? '')}
              onChange={e => setDraft(d => ({ ...d, score: e.target.value === '' ? null : Number(e.target.value) }))}
              placeholder="0-100"
              style={{ ...inputStyle(), height: 26, width: 90 }} />
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              {editing ? (
                <>
                  <button onClick={() => { setEditing(false); setDraft({ status: ra.status, score: ra.score, observation: ra.observation || '' }) }} style={ghostButton()}>CANCEL</button>
                  <button onClick={save} style={primaryButton()}><Save size={11} /> SAVE</button>
                </>
              ) : (
                <button onClick={() => setEditing(true)} style={ghostButton()}>EDIT</button>
              )}
            </div>
          </div>

          <textarea
            disabled={!editing}
            value={editing ? draft.observation : (ra.observation || '')}
            onChange={e => setDraft(d => ({ ...d, observation: e.target.value }))}
            rows={3}
            placeholder="Observation / justification..."
            style={textareaStyle()}
          />

          {/* AI panel */}
          <div style={{
            display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
            padding: '8px 10px', border: '1px dashed var(--accent-border)', background: 'var(--accent-dim)',
          }}>
            <Wand2 size={12} style={{ color: 'var(--accent)' }} />
            <span style={{ fontSize: 12, color: 'var(--accent)', letterSpacing: '0.1em' }}>AI</span>
            <button onClick={aiSuggest} disabled={aiLoading !== null}
              title="Ask the LLM for additional, context-aware evidence ideas beyond the standard checklist above"
              style={{ ...ghostButton(), opacity: aiLoading ? 0.5 : 1 }}>
              {aiLoading === 'suggest' ? 'THINKING...' : 'AI: MORE IDEAS'}
            </button>
            <button onClick={() => aiAssess(false)} disabled={aiLoading !== null}
              style={{ ...ghostButton(), opacity: aiLoading ? 0.5 : 1 }}>
              {aiLoading === 'assess' ? 'JUDGING...' : 'ASSESS (PREVIEW)'}
            </button>
            <button onClick={() => aiAssess(true)} disabled={aiLoading !== null}
              style={{ ...primaryButton(), opacity: aiLoading ? 0.5 : 1 }}>
              <Sparkles size={11} /> ASSESS & APPLY
            </button>
          </div>

          {suggestions.length > 0 && (
            <div style={{ padding: '8px 10px', border: '1px solid var(--accent-border)', background: 'var(--bg-base)' }}>
              <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--accent)', marginBottom: 6 }}>◆ AI-GENERATED SUGGESTIONS (CONTEXT-AWARE)</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.7 }}>
                {suggestions.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}

          {ra.ai_recommendation && (
            <div style={{ padding: '8px 10px', border: '1px solid var(--accent-border)', background: 'var(--bg-base)' }}>
              <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--accent)', marginBottom: 6 }}>LAST AI VERDICT</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{ra.ai_recommendation}</div>
            </div>
          )}

          {/* Evidence */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 12, letterSpacing: '0.15em', color: 'var(--text-dim)' }}>EVIDENCE</span>
              <button onClick={() => setAddingEv(v => !v)} style={ghostButton()}>
                {addingEv ? <X size={11} /> : <Plus size={11} />}
                {addingEv ? ' CLOSE' : ' ADD'}
              </button>
            </div>

            {addingEv && (
              <div style={{ padding: 10, border: '1px solid var(--border-bright)', background: 'var(--bg-base)', display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
                <input value={newEvidence.name} onChange={e => setNewEvidence(s => ({ ...s, name: e.target.value }))}
                  placeholder="Evidence name" style={inputStyle()} />
                <select value={newEvidence.kind} onChange={e => setNewEvidence(s => ({ ...s, kind: e.target.value as 'text' | 'url' }))} style={inputStyle()}>
                  <option value="text">TEXT</option>
                  <option value="url">URL</option>
                </select>
                {newEvidence.kind === 'text' ? (
                  <textarea value={newEvidence.body} onChange={e => setNewEvidence(s => ({ ...s, body: e.target.value }))}
                    rows={4} placeholder="Paste log excerpt, policy text, etc." style={textareaStyle()} />
                ) : (
                  <input value={newEvidence.url} onChange={e => setNewEvidence(s => ({ ...s, url: e.target.value }))}
                    placeholder="https://..." style={inputStyle()} />
                )}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
                  <button onClick={addEvidence} disabled={savingEv} style={primaryButton()}>
                    {savingEv ? 'SAVING...' : <><Check size={11} /> ADD</>}
                  </button>
                </div>
              </div>
            )}

            {ra.evidences.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-dim)', padding: 6 }}>No evidence yet.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {ra.evidences.map(ev => (
                  <div key={ev.id} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                    padding: '6px 10px', border: '1px solid var(--border)',
                    background: 'var(--bg-base)', fontSize: 13,
                  }}>
                    <FileText size={11} style={{ color: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{ev.name}</div>
                      {ev.kind === 'url' && ev.url && (
                        <a href={ev.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', wordBreak: 'break-all' }}>{ev.url}</a>
                      )}
                      {ev.kind === 'text' && ev.body && (
                        <div style={{ color: 'var(--text-muted)', whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'hidden' }}>{ev.body.slice(0, 240)}{ev.body.length > 240 ? '…' : ''}</div>
                      )}
                    </div>
                    <button onClick={() => deleteEv(ev)} style={iconButton('var(--red)')}><Trash2 size={11} /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Bits & pieces
// ---------------------------------------------------------------------------

function ProgressBar({ progress }: { progress: AssessmentSummary['progress'] }) {
  if (!progress || progress.total === 0) return (
    <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>NO REQUIREMENTS</div>
  )
  const widthOf = (n: number) => `${(n / progress.total) * 100}%`
  return (
    <div>
      <div style={{
        display: 'flex', height: 6, background: 'var(--bg-base)', border: '1px solid var(--border)',
      }}>
        <div style={{ width: widthOf(progress.compliant), background: STATUS_COLORS.compliant }} />
        <div style={{ width: widthOf(progress.partially_compliant), background: STATUS_COLORS.partially_compliant }} />
        <div style={{ width: widthOf(progress.non_compliant), background: STATUS_COLORS.non_compliant }} />
        <div style={{ width: widthOf(progress.not_applicable), background: STATUS_COLORS.not_applicable }} />
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4, letterSpacing: '0.05em' }}>
        {progress.percent}% ASSESSED ({progress.assessed}/{progress.total})
      </div>
    </div>
  )
}

function Modal({ title, children, onClose, wide }: { title: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 9999, padding: 20,
      background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: '100%', maxWidth: wide ? 900 : 640, maxHeight: '90vh',
        background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{
          padding: '12px 16px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 14, letterSpacing: '0.15em', color: 'var(--accent)' }}>{title}</span>
          <button onClick={onClose} style={iconButton('var(--text-dim)')}><X size={14} /></button>
        </div>
        <div style={{ padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {children}
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  )
}

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, letterSpacing: '0.15em' }}>LOADING...</div>
)

const Empty = ({ hint }: { hint: string }) => (
  <div style={{
    padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, letterSpacing: '0.15em',
    border: '1px dashed var(--border-bright)', background: 'var(--bg-surface)',
  }}>{hint}</div>
)

// Style helpers --------------------------------------------------------------
const inputStyle = (): React.CSSProperties => ({
  width: '100%', height: 32, padding: '0 10px',
  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
  color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)', outline: 'none',
})
const textareaStyle = (): React.CSSProperties => ({
  ...inputStyle(), height: 'auto', padding: '8px 10px', lineHeight: 1.5, resize: 'vertical',
})
const card = (): React.CSSProperties => ({
  border: '1px solid var(--border)', background: 'var(--bg-surface)',
  padding: 12, display: 'flex', flexDirection: 'column', gap: 6,
})
const primaryButton = (): React.CSSProperties => ({
  padding: '6px 12px', fontSize: 12, letterSpacing: '0.1em',
  background: 'var(--accent)', border: '1px solid var(--accent-border)',
  color: '#000', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontWeight: 700,
  display: 'inline-flex', alignItems: 'center', gap: 4,
})
const ghostButton = (): React.CSSProperties => ({
  padding: '6px 12px', fontSize: 12, letterSpacing: '0.1em',
  background: 'transparent', border: '1px solid var(--border-bright)',
  color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-mono)',
  display: 'inline-flex', alignItems: 'center', gap: 4,
})
const tabButton = (active: boolean): React.CSSProperties => ({
  padding: '6px 14px', fontSize: 12, letterSpacing: '0.1em',
  background: active ? 'var(--accent-dim)' : 'transparent',
  border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border-bright)'}`,
  color: active ? 'var(--accent)' : 'var(--text-muted)',
  cursor: 'pointer', fontFamily: 'var(--font-mono)',
  display: 'inline-flex', alignItems: 'center', gap: 4,
})
const chipButton = (active: boolean): React.CSSProperties => ({
  padding: '4px 10px', fontSize: 12, letterSpacing: '0.1em',
  background: active ? 'var(--accent-dim)' : 'transparent',
  border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border-bright)'}`,
  color: active ? 'var(--accent)' : 'var(--text-muted)',
  cursor: 'pointer', fontFamily: 'var(--font-mono)',
})
const iconButton = (color: string): React.CSSProperties => ({
  padding: 4, background: 'none', border: 'none', color, cursor: 'pointer',
})
const statusBadge = (status: string, outlined?: boolean): React.CSSProperties => {
  const map: Record<string, string> = {
    planning: 'var(--amber, #ffb000)',
    in_progress: 'var(--accent)',
    completed: 'var(--cyan, #00bcd4)',
    archived: 'var(--text-muted)',
  }
  const c = map[status] || 'var(--text-muted)'
  return {
    fontSize: 11, letterSpacing: '0.12em', padding: '2px 6px',
    border: `1px solid ${c}`,
    color: outlined ? c : c,
    background: outlined ? 'transparent' : 'transparent',
    fontFamily: 'var(--font-mono)',
  }
}
