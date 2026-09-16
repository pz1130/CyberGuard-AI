import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '../api/client'
import { errorMessage } from '../lib/errorMessage'

/**
 * The auditor's view of chat history.
 *
 * Three capabilities that all need AUDIT_READ and all concern the same thing —
 * what was said, whether it can still be proved, and when it may be disposed
 * of. They live beside the audit log because it is the same person's job.
 */
interface Hit {
  conversation_id: number
  conversation_title: string | null
  message_id: number
  seq: number
  role: string
  created_at: string | null
  snippet: string
}

interface PurgeCandidate {
  conversation_id: number
  messages: number
  object_key: string
}

const card: React.CSSProperties = {
  border: '1px solid var(--border-bright)', background: 'var(--bg-surface)',
  padding: 20, marginBottom: 16, borderRadius: 'var(--radius-md)',
}
const heading: React.CSSProperties = {
  fontSize: 13, fontWeight: 600, letterSpacing: '0.08em',
  color: 'var(--text-primary)', marginBottom: 6,
}
const hint: React.CSSProperties = {
  fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 14,
}
const numberInput: React.CSSProperties = {
  width: 90, height: 32, padding: '0 8px', textAlign: 'right',
}

export default function ChatEvidence() {
  const { t } = useTranslation()

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Hit[] | null>(null)
  const [searching, setSearching] = useState(false)

  const [exportOlder, setExportOlder] = useState(0)
  const [retainDays, setRetainDays] = useState(365)
  const [exportMsg, setExportMsg] = useState('')
  const [exporting, setExporting] = useState(false)

  const [purgeOlder, setPurgeOlder] = useState(365)
  const [candidates, setCandidates] = useState<PurgeCandidate[] | null>(null)
  const [purgeMsg, setPurgeMsg] = useState('')
  const [purging, setPurging] = useState(false)

  const search = async () => {
    const term = query.trim()
    if (!term) return
    setSearching(true); setHits(null)
    try {
      const res = await api.auditorSearchConversations(term) as { results?: Hit[] }
      setHits(res?.results || [])
    } catch (e: unknown) {
      setHits([]); alert(errorMessage(e))
    } finally { setSearching(false) }
  }

  const runExport = async () => {
    setExporting(true); setExportMsg('')
    try {
      const res = await api.exportConversations(exportOlder, retainDays) as {
        exported?: unknown[]; skipped?: unknown[]
      }
      setExportMsg(`exported ${res?.exported?.length ?? 0}, skipped ${res?.skipped?.length ?? 0}`)
    } catch (e: unknown) {
      // A 503 here names the missing S3 variables. It is the whole reason
      // purge finds nothing eligible, so it is shown rather than swallowed.
      setExportMsg(errorMessage(e))
    } finally { setExporting(false) }
  }

  const dryRun = async () => {
    setPurging(true); setPurgeMsg(''); setCandidates(null)
    try {
      const res = await api.purgeConversations(purgeOlder, false) as {
        conversations?: PurgeCandidate[]
      }
      setCandidates(res?.conversations || [])
    } catch (e: unknown) {
      setPurgeMsg(errorMessage(e))
    } finally { setPurging(false) }
  }

  const confirmPurge = async () => {
    const typed = window.prompt(t('audit.confirmPrompt'))
    if (typed !== 'PURGE') return
    setPurging(true)
    try {
      const res = await api.purgeConversations(purgeOlder, true) as {
        messages_deleted?: number
      }
      setPurgeMsg(t('audit.purgeDone', { messages: res?.messages_deleted ?? 0 }))
      setCandidates(null)
    } catch (e: unknown) {
      setPurgeMsg(errorMessage(e))
    } finally { setPurging(false) }
  }

  const totalMessages = (candidates || []).reduce((n, c) => n + c.messages, 0)

  return (
    <div style={{ maxWidth: 780 }}>
      {/* ── cross-user search ── */}
      <div style={card}>
        <div style={heading}>{t('audit.searchTitle').toUpperCase()}</div>
        <div style={hint}>{t('audit.searchHint')}</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input
            aria-label={t('audit.searchTitle')}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void search() }}
            placeholder={t('audit.searchPlaceholder')}
            className="form-input"
            style={{ flex: 1, minWidth: 200, height: 32 }} />
          <button onClick={() => void search()} disabled={!query.trim() || searching}
            className="btn btn-primary btn-sm">
            {searching ? t('audit.working') : t('audit.searchButton')}
          </button>
        </div>

        {hits !== null && hits.length === 0 && (
          <div style={{ ...hint, marginTop: 14, marginBottom: 0 }}>
            {t('audit.searchNoResults')}
          </div>
        )}
        {hits !== null && hits.length > 0 && (
          <div style={{ marginTop: 14 }}>
            {hits.map(h => (
              <div key={h.message_id} style={{
                borderTop: '1px solid var(--border)', padding: '10px 0',
              }}>
                <div style={{ fontSize: 12, color: 'var(--accent)' }}>
                  {h.conversation_title || `#${h.conversation_id}`}
                  <span style={{ color: 'var(--text-dim)', marginLeft: 8 }}>
                    {h.role} · seq {h.seq}
                    {h.created_at ? ` · ${h.created_at.slice(0, 19).replace('T', ' ')}` : ''}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4,
                              lineHeight: 1.6 }}>
                  {h.snippet}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── export ── */}
      <div style={card}>
        <div style={heading}>{t('audit.exportTitle').toUpperCase()}</div>
        <div style={hint}>{t('audit.exportHint')}</div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            <div style={{ marginBottom: 5 }}>{t('audit.olderThanDays')}</div>
            <input type="number" min={0} value={exportOlder} className="form-input font-mono"
              style={numberInput}
              onChange={e => setExportOlder(parseInt(e.target.value) || 0)} />
          </label>
          <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            <div style={{ marginBottom: 5 }}>{t('audit.retainDays')}</div>
            <input type="number" min={1} value={retainDays} className="form-input font-mono"
              style={numberInput}
              onChange={e => setRetainDays(parseInt(e.target.value) || 1)} />
          </label>
          <button onClick={() => void runExport()} disabled={exporting}
            className="btn btn-primary btn-sm">
            {exporting ? t('audit.working') : t('audit.exportButton')}
          </button>
        </div>
        {exportMsg && (
          <div role="status" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.6,
                                      color: 'var(--text-muted)' }}>
            {exportMsg}
          </div>
        )}
      </div>

      {/* ── purge ── */}
      <div style={card}>
        <div style={heading}>{t('audit.purgeTitle').toUpperCase()}</div>
        <div style={hint}>{t('audit.purgeHint')}</div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            <div style={{ marginBottom: 5 }}>{t('audit.olderThanDays')}</div>
            <input type="number" min={0} value={purgeOlder} className="form-input font-mono"
              style={numberInput}
              onChange={e => setPurgeOlder(parseInt(e.target.value) || 0)} />
          </label>
          <button onClick={() => void dryRun()} disabled={purging}
            className="btn btn-sm">
            {purging ? t('audit.working') : t('audit.purgeDryRun')}
          </button>
          {/* Only after a dry run, and only when it found something. */}
          {candidates !== null && candidates.length > 0 && (
            <button onClick={() => void confirmPurge()} disabled={purging}
              className="btn btn-sm"
              style={{ borderColor: 'var(--red)', color: 'var(--red)' }}>
              {t('audit.purgeConfirm')}
            </button>
          )}
        </div>

        {candidates !== null && candidates.length === 0 && (
          <div style={{ ...hint, marginTop: 12, marginBottom: 0 }}>
            {t('audit.purgeNothing')}
          </div>
        )}
        {candidates !== null && candidates.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 8 }}>
              {t('audit.purgeWillDelete', {
                messages: totalMessages, conversations: candidates.length })}
            </div>
            {candidates.map(c => (
              <div key={c.conversation_id} className="font-mono"
                style={{ fontSize: 11, color: 'var(--text-dim)', padding: '3px 0' }}>
                #{c.conversation_id} · {c.messages} msg · {c.object_key}
              </div>
            ))}
          </div>
        )}
        {purgeMsg && (
          <div role="status" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.6,
                                      color: 'var(--text-muted)' }}>
            {purgeMsg}
          </div>
        )}
      </div>
    </div>
  )
}
