import { useCallback, useContext, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { RoleContext, hasPermission } from '../context/permissions'
import { errorMessage } from '../lib/errorMessage'

type Finding = {
  id: number; title: string; target: string; severity: string; status: string
  description: string; remediation: string; created_by: number; assignee_id: number | null
  version: number; source: string
}
type Event = { id: number; actor_id: number; action: string; note: string; evidence: string; evidence_hash: string; created_at: string }
type Detail = Finding & { events: Event[] }
const statuses = ['pending', 'confirmed', 'in_progress', 'ready_for_retest', 'resolved', 'rejected']
const empty = { title: '', target: '', severity: 'medium', description: '', remediation: '', evidence: '' }

export default function Findings() {
  const { t } = useTranslation()
  const role = useContext(RoleContext)
  const canSubmit = hasPermission(role, 'finding:submit')
  const canManage = hasPermission(role, 'finding:manage')
  const canReview = hasPermission(role, 'finding:review')
  const [items, setItems] = useState<Finding[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [filter, setFilter] = useState('')
  const [detail, setDetail] = useState<Detail | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(empty)
  const [note, setNote] = useState('')
  const [evidence, setEvidence] = useState('')
  const [assignee, setAssignee] = useState('')
  const [owners, setOwners] = useState<{ id: number; username: string }[]>([])
  const [userId, setUserId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const reload = useCallback(async () => {
    const data = await api.getFindings(filter, offset) as { items: Finding[]; total: number }
    setItems(data.items); setTotal(data.total)
  }, [filter, offset])

  useEffect(() => {
    let active = true
    api.getFindings(filter, offset).then(data => {
      if (active) { const result = data as { items: Finding[]; total: number }; setItems(result.items); setTotal(result.total) }
    }).catch(e => { if (active) setError(errorMessage(e)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [filter, offset])
  useEffect(() => {
    api.getAuthMe().then(data => setUserId((data as { id?: number; user_id?: number }).user_id ?? (data as { id: number }).id))
      .catch(e => setError(errorMessage(e)))
    if (canManage) api.getFindingAssignees().then(data => setOwners(data as typeof owners)).catch(e => setError(errorMessage(e)))
  }, [canManage])

  async function open(id: number) {
    setBusy(true); setError('')
    try { setDetail(await api.getFinding(id) as Detail); setCreating(false); setNote(''); setEvidence(''); setAssignee('') }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const saved = await api.createFinding(form) as Finding
      setForm(empty); setCreating(false); await reload()
      setDetail(await api.getFinding(saved.id) as Detail)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  async function change(action: string) {
    if (!detail) return
    setBusy(true); setError('')
    try {
      await api.changeFinding(detail.id, { action, version: detail.version, note, evidence, ...(action === 'assign' ? { assignee_id: Number(assignee) } : {}) })
      setDetail(await api.getFinding(detail.id) as Detail); setNote(''); setEvidence(''); await reload()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  async function download() {
    if (!detail) return
    setBusy(true); setError('')
    try {
      const blob = await api.downloadFindingReport(detail.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = `finding-${detail.id}.md`; a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const independent = userId !== null && detail && userId !== detail.created_by && userId !== detail.assignee_id
  const actions: string[] = []
  if (detail) {
    if (canReview && independent) {
      if (detail.status === 'pending') actions.push('confirm', 'reject')
      if (detail.status === 'ready_for_retest') actions.push('resolve', 'reopen')
      if (['resolved', 'rejected'].includes(detail.status)) actions.push('reopen')
    }
    if (canManage) {
      if (['confirmed', 'in_progress'].includes(detail.status)) actions.push('assign')
      if (detail.status === 'in_progress' && (userId === detail.assignee_id || role === 'admin')) actions.push('ready')
      actions.push('evidence')
    }
  }

  return <section className="findings-page">
    <header className="findings-toolbar"><div><h1>{t('findings.title')}</h1><p>{t('findings.subtitle')}</p></div>
      {canSubmit && <button className="btn btn-primary" disabled={busy} onClick={() => { setCreating(true); setDetail(null); setError('') }}>{t('findings.new')}</button>}
    </header>
    {error && <div role="alert">{error}</div>}
    <label>{t('findings.filter')} <select value={filter} disabled={busy} onChange={e => { setFilter(e.target.value); setOffset(0); setLoading(true) }}>
      <option value="">{t('findings.all')}</option>{statuses.map(s => <option key={s} value={s}>{t(`findings.status.${s}`)}</option>)}
    </select></label>
    <div className="findings-layout">
      <div>
        {loading ? <p role="status">{t('findings.loading')}</p> : <table className="findings-table">
          <thead><tr><th>{t('findings.titleField')}</th><th>{t('findings.severity')}</th><th>{t('findings.state')}</th></tr></thead>
          <tbody>{items.map(row => <tr key={row.id}><td><button className="btn" disabled={busy} onClick={() => open(row.id)}>#{row.id} {row.title}</button></td>
            <td>{t(`findings.severities.${row.severity}`)}</td><td>{t(`findings.status.${row.status}`)}</td></tr>)}</tbody>
        </table>}
        {!loading && !items.length && <p>{t('findings.empty')}</p>}
        <div className="findings-toolbar">
          <button className="btn" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>{t('findings.previous')}</button>
          <span>{t('findings.total', { count: total })}</span>
          <button className="btn" disabled={busy || offset + 50 >= total} onClick={() => setOffset(offset + 50)}>{t('findings.next')}</button>
        </div>
      </div>
      {creating && <form className="findings-panel" onSubmit={create}>
        <h2>{t('findings.new')}</h2>
        {(['title', 'target', 'description', 'remediation', 'evidence'] as const).map(key => <label key={key}>{t(`findings.${key === 'title' ? 'titleField' : key}`)}
          {key === 'title' || key === 'target'
            ? <input required maxLength={key === 'title' ? 200 : 1000} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} />
            : <textarea required maxLength={key === 'evidence' ? 65536 : 20000} rows={4} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} />}
        </label>)}
        <label>{t('findings.severity')}<select value={form.severity} onChange={e => setForm({ ...form, severity: e.target.value })}>
          {['info', 'low', 'medium', 'high', 'critical'].map(s => <option key={s} value={s}>{t(`findings.severities.${s}`)}</option>)}
        </select></label>
        <button className="btn btn-primary" disabled={busy}>{t('findings.submit')}</button>
      </form>}
      {detail && <article className="findings-panel">
        <header className="findings-toolbar"><h2>#{detail.id} {detail.title}</h2><button className="btn" disabled={busy} onClick={download}>{t('findings.export')}</button></header>
        <p>{t('findings.state')}: {t(`findings.status.${detail.status}`)} · {t('findings.source')}: {t(`findings.sources.${detail.source}`)}</p>
        <p>{t('findings.target')}: {detail.target}</p>
        <p>{t('findings.owner')}: {detail.assignee_id ? owners.find(u => u.id === detail.assignee_id)?.username || `#${detail.assignee_id}` : t('findings.unassigned')}</p>
        <h3>{t('findings.description')}</h3><pre>{detail.description}</pre>
        <h3>{t('findings.remediation')}</h3><pre>{detail.remediation}</pre>
        {canReview && !independent && <p>{t('findings.independent')}</p>}
        {!!actions.length && <div>
          <label>{t('findings.note')}<textarea rows={3} maxLength={10000} value={note} onChange={e => setNote(e.target.value)} /></label>
          <label>{t('findings.evidence')}<textarea rows={4} maxLength={65536} value={evidence} onChange={e => setEvidence(e.target.value)} /></label>
          {actions.includes('assign') && <label>{t('findings.owner')}<select value={assignee} onChange={e => setAssignee(e.target.value)}>
            <option value="">{t('findings.chooseOwner')}</option>{owners.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}
          </select></label>}
          <div className="findings-actions">{actions.map(action => <button key={action} className="btn" disabled={busy || !note.trim() || (action === 'assign' && !assignee) || (['resolve', 'reopen', 'evidence'].includes(action) && !evidence.trim())}
            onClick={() => change(action)}>{t(`findings.actions.${action}`)}</button>)}</div>
        </div>}
        <h3>{t('findings.timeline')}</h3>
        {detail.events.map(event => <div className="findings-event" key={event.id}>
          <strong>{t(`findings.actions.${event.action}`)}</strong> · #{event.actor_id} · {event.created_at} UTC
          <pre>{event.note}</pre>{event.evidence && <details><summary>{t('findings.evidence')}</summary><pre>{event.evidence}</pre><small>SHA-256: {event.evidence_hash}</small></details>}
        </div>)}
      </article>}
    </div>
  </section>
}
