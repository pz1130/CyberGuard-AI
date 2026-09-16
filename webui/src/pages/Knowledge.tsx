import { useState, useEffect, useRef, useContext, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Plus, Search, Trash2, Upload, FileText, Database, Loader2, Settings2 } from 'lucide-react'
import { SearchContext } from '../context/search'
import { errorMessage } from '../lib/errorMessage'
import PageHeader from '../components/PageHeader'
import Modal from '../components/Modal'

interface KB {
  id: number
  name: string
  description?: string
  provider_id?: number | null
  embedding_model?: string
  embedding_dim?: number
  rerank_model?: string
  is_active?: boolean
}

// Auto-detect vector dim from the embedding model name. Default 1536 (most providers).
const dimFromModel = (model?: string): number => {
  if (!model) return 1536
  if (/embedding-3-large|text-embedding-3-large/i.test(model)) return 3072
  return 1536
}

interface Doc {
  id: number
  kb_id: number
  filename: string
  file_size?: number
  metadata_json?: { chunk_count?: number }
  created_at?: string
  status?: 'ready' | 'processing' | 'failed'
  status_detail?: string | null
}

interface QueryResult {
  document_id: number
  filename: string
  chunk_index: number
  text: string
  score: number
}

interface ModelInfo {
  name: string
  model_type: 'chat' | 'embedding' | 'rerank'
}

interface ProviderOption {
  id: number
  name: string
  base_url?: string
  api_key?: string | null
  is_active?: boolean
  models: ModelInfo[]
}

function isMinimaxProvider(p: ProviderOption): boolean {
  return /minimax/i.test(p.base_url || '') || /minimax/i.test(p.name || '')
}

function providerHasEmbedding(p: ProviderOption): boolean {
  return p.is_active !== false && p.api_key === '******' && (
    (p.models || []).some(m => m.model_type === 'embedding') || isMinimaxProvider(p)
  )
}

interface OcrConfig {
  enabled?: boolean
  engine?: string
  vision_provider_id?: number | null
  vision_model?: string | null
  languages?: string
  max_pages?: number
}

function OcrSettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const [cfg, setCfg] = useState<OcrConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [prevOpen, setPrevOpen] = useState(open)

  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setLoading(true)
  }

  useEffect(() => {
    if (!open) return
    let cancelled = false
    void api.getOcrConfig()
      .then(res => { if (!cancelled) setCfg(res as OcrConfig) })
      .catch(() => { if (!cancelled) onClose() })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, onClose])

  if (!open) return null

  const save = async () => {
    if (!cfg) return
    setSaving(true)
    try {
      await api.updateOcrConfig(cfg)
      onClose()
    } catch (e: unknown) {
      alert(errorMessage(e) || 'Failed to update OCR config')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      eyebrow={t('knowledge.ocrEyebrow', 'OCR CONFIGURATION').toUpperCase()}
      title={t('knowledge.ocrSettings')}
      onClose={onClose}
      width={520}
      footer={
        <>
          <button onClick={onClose} className="btn btn-secondary">
            {t('knowledge.cancel', 'Cancel')}
          </button>
          <button onClick={save} disabled={saving || loading || !cfg} className="btn btn-primary">
            {saving ? (
              <>
                <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                {t('knowledge.save', 'Save')}
              </>
            ) : (
              t('knowledge.save', 'Save')
            )}
          </button>
        </>
      }
    >
      {loading || !cfg ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '36px 0', gap: 8 }}>
          <Loader2 size={18} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>{t('knowledge.loading')}</span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: 'var(--bg-elevated)', borderRadius: 0, border: '1px solid var(--border)' }}>
            <input
              id="ocr-enabled"
              type="checkbox"
              checked={cfg.enabled ?? false}
              onChange={e => setCfg({ ...cfg, enabled: e.target.checked })}
              style={{ accentColor: 'var(--accent)', cursor: 'pointer', width: 16, height: 16 }}
            />
            <label htmlFor="ocr-enabled" style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', cursor: 'pointer' }}>
              {t('knowledge.enableOcr')}
            </label>
          </div>

          <div>
            <label className="form-label">{t('knowledge.engine')}</label>
            <select
              value={cfg.engine || 'tesseract'}
              onChange={e => setCfg({ ...cfg, engine: e.target.value })}
              className="form-input"
            >
              <option value="tesseract">{t('knowledge.tesseractLocal')}</option>
              <option value="vision">Vision LLM</option>
            </select>
          </div>

          {cfg.engine === 'vision' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
              <div>
                <label className="form-label">{t('knowledge.visionProviderId')}</label>
                <input
                  type="number"
                  value={cfg.vision_provider_id ?? ''}
                  onChange={e => setCfg({ ...cfg, vision_provider_id: e.target.value ? Number(e.target.value) : null })}
                  className="form-input"
                  placeholder="e.g. 1"
                />
              </div>
              <div>
                <label className="form-label">{t('knowledge.visionModel')}</label>
                <input
                  value={cfg.vision_model ?? ''}
                  onChange={e => setCfg({ ...cfg, vision_model: e.target.value })}
                  className="form-input"
                  placeholder="e.g. gpt-4o or claude-3-5-sonnet"
                />
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label className="form-label">{t('knowledge.lang')}</label>
              <input
                value={cfg.languages || 'eng+chi_sim'}
                onChange={e => setCfg({ ...cfg, languages: e.target.value })}
                className="form-input"
                placeholder="eng+chi_sim"
              />
            </div>
            <div>
              <label className="form-label">{t('knowledge.maxPages')}</label>
              <input
                type="number"
                value={cfg.max_pages ?? 20}
                onChange={e => setCfg({ ...cfg, max_pages: Number(e.target.value) })}
                className="form-input"
                min={1}
                max={200}
              />
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

export default function Knowledge() {
  const { t } = useTranslation()
  const [bases, setBases] = useState<KB[]>([])
  const [selected, setSelected] = useState<KB | null>(null)
  const [loadingKB, setLoadingKB] = useState(true)
  const [showKBForm, setShowKBForm] = useState(false)
  const [showOcrModal, setShowOcrModal] = useState(false)
  const [kbForm, setKBForm] = useState<Partial<KB>>({ name: '', description: '', embedding_model: '', embedding_dim: 1536 })
  const [docs, setDocs] = useState<Doc[]>([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [textForm, setTextForm] = useState({ filename: '', content: '' })
  const [showTextForm, setShowTextForm] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { searchTarget, setSearchTarget } = useContext(SearchContext)

  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'knowledge') return
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

  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [results, setResults] = useState<QueryResult[]>([])
  const [querying, setQuerying] = useState(false)
  const [providers, setProviders] = useState<ProviderOption[]>([])
  const [providerId, setProviderId] = useState<number | null>(null)
  const [prevSelectedId, setPrevSelectedId] = useState(selected?.id)

  if (selected?.id !== prevSelectedId) {
    setPrevSelectedId(selected?.id)
    setResults([])
    setProviderId(selected?.provider_id ?? null)
    if (selected) setLoadingDocs(true)
  }

  const loadKBs = useCallback(async () => {
    try {
      const data = await api.getKnowledgeBases() as { knowledge_bases?: KB[] }
      const list = data?.knowledge_bases || []
      setBases(list)
      if (list.length > 0) {
        setSelected(prev => {
          if (!prev) return list[0]
          const existing = list.find(item => item.id === prev.id)
          return existing || list[0]
        })
      } else {
        setSelected(null)
      }
    } catch { setBases([]) } finally { setLoadingKB(false) }
  }, [])

  const loadDocs = useCallback(async (kbId: number) => {
    try {
      const data = await api.getDocuments(kbId) as { documents?: Doc[] }
      setDocs(data?.documents || [])
    } catch { setDocs([]) } finally { setLoadingDocs(false) }
  }, [])

  const loadProviders = useCallback(async () => {
    try {
      const data = await api.getProviders() as { providers?: ProviderOption[] }
      const list = data?.providers || []
      setProviders(list)
      const capable = list.filter(providerHasEmbedding)
      setProviderId(prev => {
        if (prev && capable.some(p => p.id === prev)) return prev
        return capable[0]?.id ?? null
      })
    } catch { /* keep previous providers */ }
  }, [])

  useEffect(() => {
    void Promise.resolve().then(() => { void loadKBs(); void loadProviders() })
  }, [loadKBs, loadProviders])
  useEffect(() => {
    if (selected) void Promise.resolve().then(() => loadDocs(selected.id))
  }, [selected, loadDocs])

  useEffect(() => {
    const hasProcessing = docs.some(d => d.status === 'processing')
    if (!hasProcessing) return
    const timer = setInterval(() => { if (selected) void loadDocs(selected.id) }, 5000)
    return () => clearInterval(timer)
  }, [docs, selected, loadDocs])

  const embeddingModels = providers.flatMap(p =>
    (p.models || [])
      .filter((m: ModelInfo) => m.model_type === 'embedding')
      .map(m => ({ ...m, providerId: p.id, providerName: p.name })),
  )

  const submitKB = async () => {
    if (!kbForm.name?.trim()) return alert(t('knowledge.enterKbName'))
    if (!kbForm.embedding_model) {
      return alert(t('knowledge.embeddingRequired'))
    }
    if (!kbForm.provider_id) {
      return alert(t('knowledge.noEmbeddingProvider'))
    }
    try {
      const created = await api.createKnowledgeBase(kbForm) as KB
      setShowKBForm(false)
      setKBForm({ name: '', description: '', provider_id: null, embedding_model: '', embedding_dim: 1536 })
      await loadKBs()
      if (created?.id) setSelected(created)
    } catch (e: unknown) { alert(errorMessage(e)) }
  }

  const deleteKB = async (kb: KB) => {
    const msg = t('knowledge.deleteKbConfirm', { name: kb.name, defaultValue: `Delete "${kb.name}" and all its documents?` })
    if (!confirm(msg)) return
    try {
      await api.deleteKnowledgeBase(kb.id)
      if (selected?.id === kb.id) setSelected(null)
      loadKBs()
    } catch (e: unknown) { alert(errorMessage(e)) }
  }

  const ingestText = async () => {
    if (!selected || !textForm.filename?.trim() || !textForm.content?.trim()) {
      return alert(t('knowledge.fillNameContent'))
    }
    const chosen = providers.find(p => p.id === selected.provider_id)
    if (!chosen || !providerHasEmbedding(chosen)) {
      return alert(t('knowledge.noEmbeddingProvider'))
    }
    setIngesting(true)
    try {
      await api.ingestText(selected.id, { filename: textForm.filename, content: textForm.content, provider_id: selected.provider_id ?? undefined })
      setTextForm({ filename: '', content: '' })
      setShowTextForm(false)
      loadDocs(selected.id)
    } catch (e: unknown) {
      alert(`${t('knowledge.importFailed')}: ${errorMessage(e)}`)
    } finally {
      setIngesting(false)
    }
  }

  const uploadFile = async (file: File) => {
    if (!selected) return
    const chosen = providers.find(p => p.id === selected.provider_id)
    if (!chosen || !providerHasEmbedding(chosen)) {
      return alert(t('knowledge.noEmbeddingProvider'))
    }
    setIngesting(true)
    try {
      const res = await api.uploadDocument(selected.id, file, selected.provider_id ?? undefined) as { status?: string }
      loadDocs(selected.id)
      if (res?.status === 'processing') {
        alert(t('knowledge.scanUploadedOcr'))
      }
    } catch (e: unknown) {
      alert(`${t('knowledge.uploadFailed')}: ${errorMessage(e)}`)
    } finally {
      setIngesting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const deleteDoc = async (doc: Doc) => {
    if (!selected) return
    if (!confirm(t('knowledge.confirmDelete', { defaultValue: `Delete "${doc.filename}"?` }))) return
    try {
      await api.deleteDocument(selected.id, doc.id)
      loadDocs(selected.id)
    } catch (e: unknown) { alert(errorMessage(e)) }
  }

  const search = async () => {
    if (!selected) return alert(t('knowledge.selectKbHint'))
    if (!query.trim()) return
    const chosen = providers.find(p => p.id === selected.provider_id)
    if (!chosen || !providerHasEmbedding(chosen)) {
      return alert(t('knowledge.noEmbeddingProvider'))
    }
    setQuerying(true)
    try {
      const res = await api.queryKnowledge({ kb_id: selected.id, query, top_k: topK, provider_id: selected.provider_id ?? undefined }) as { results: QueryResult[] }
      setResults(res.results || [])
    } catch (e: unknown) { alert(errorMessage(e)) } finally { setQuerying(false) }
  }

  return (
    <div>
      {/* Unified Page Header */}
      <PageHeader
        eyebrow={t('knowledge.eyebrow', 'SEMANTIC SEARCH').toUpperCase()}
        title={t('knowledge.title', 'KNOWLEDGE BASE').toUpperCase()}
        description={t('knowledge.description', 'Manage document embeddings, knowledge bases, and semantic retrieval.')}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 11, letterSpacing: '0.06em', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                {t('knowledge.embeddingProvider').toUpperCase()}
              </span>
              <select
                value={selected?.provider_id ?? providerId ?? ''}
                onChange={e => setProviderId(Number(e.target.value) || null)}
                disabled={Boolean(selected)}
                className="form-input"
                style={{ width: 160, height: 34, fontSize: 12, padding: '0 8px' }}
              >
                {providers.filter(providerHasEmbedding).length === 0 && (
                  <option value="">{t('knowledge.noEmbeddingProviderShort')}</option>
                )}
                {providers.filter(providerHasEmbedding).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>

            <button
              onClick={() => setShowOcrModal(true)}
              className="btn btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: 6, height: 34 }}
            >
              <Settings2 size={13} />
              {t('knowledge.ocrSettings')}
            </button>

            <button
              onClick={() => {
                const first = embeddingModels[0]
                setKBForm(f => ({
                  ...f,
                  provider_id: f.provider_id || first?.providerId || null,
                  embedding_model: f.embedding_model || first?.name || '',
                  embedding_dim: dimFromModel(f.embedding_model || first?.name),
                }))
                setShowKBForm(true)
              }}
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: 6, height: 34 }}
            >
              <Plus size={13} />
              {t('knowledge.newKb')}
            </button>
          </div>
        }
      />

      {/* OCR Settings Modal */}
      <OcrSettingsModal open={showOcrModal} onClose={() => setShowOcrModal(false)} />

      {/* New KB Modal */}
      {showKBForm && (
        <Modal
          eyebrow="KNOWLEDGE BASE"
          title={t('knowledge.newKbTitle')}
          onClose={() => setShowKBForm(false)}
          width={560}
          footer={
            <>
              <button onClick={() => setShowKBForm(false)} className="btn btn-secondary">
                {t('knowledge.cancel')}
              </button>
              <button onClick={submitKB} className="btn btn-primary">
                {t('knowledge.create')}
              </button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label className="form-label">{t('knowledge.name')} *</label>
              <input
                value={kbForm.name || ''}
                onChange={e => setKBForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Threat Intel DB"
                className="form-input"
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t('knowledge.embeddingModel')}</span>
                  <span style={{ color: 'var(--accent)', fontWeight: 700 }}>
                    {kbForm.embedding_dim || 1536}d
                  </span>
                </label>
                <select
                  value={kbForm.provider_id && kbForm.embedding_model ? `${kbForm.provider_id}:${kbForm.embedding_model}` : ''}
                  onChange={e => {
                    const separator = e.target.value.indexOf(':')
                    const selectedProviderId = Number(e.target.value.slice(0, separator))
                    const model = e.target.value.slice(separator + 1)
                    setKBForm(f => ({ ...f, provider_id: selectedProviderId, embedding_model: model, embedding_dim: dimFromModel(model) }))
                  }}
                  className="form-input"
                >
                  <option value="">— None —</option>
                  {embeddingModels.map(m => (
                    <option key={`${m.providerId}-${m.name}`} value={`${m.providerId}:${m.name}`}>{m.providerName} / {m.name}</option>
                  ))}
                </select>
                <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.4 }}>
                  {embeddingModels.length === 0 ? t('knowledge.noEmbeddingModelHint') : t('knowledge.dimNote')}
                </div>
              </div>

              <div>
                <label className="form-label">{t('knowledge.rerankModel')}</label>
                <select
                  value={kbForm.rerank_model || ''}
                  onChange={e => setKBForm(f => ({ ...f, rerank_model: e.target.value }))}
                  className="form-input"
                >
                  <option value="">— None —</option>
                  {providers.flatMap(p => p.models || []).filter((m: ModelInfo) => m.model_type === 'rerank').map((m: ModelInfo) => (
                    <option key={m.name} value={m.name}>{m.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="form-label">{t('knowledge.desc')}</label>
              <input
                value={kbForm.description || ''}
                onChange={e => setKBForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Optional description of this knowledge base"
                className="form-input"
              />
            </div>
          </div>
        </Modal>
      )}

      {/* Paste Text Modal */}
      {showTextForm && (
        <Modal
          eyebrow="DOCUMENTS"
          title={t('knowledge.importTextTitle')}
          onClose={() => setShowTextForm(false)}
          width={580}
          footer={
            <>
              <button onClick={() => setShowTextForm(false)} className="btn btn-secondary">
                {t('knowledge.cancel')}
              </button>
              <button onClick={ingestText} disabled={ingesting} className="btn btn-primary">
                {ingesting ? (
                  <>
                    <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                    {t('knowledge.importing')}
                  </>
                ) : (
                  t('knowledge.import')
                )}
              </button>
            </>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label className="form-label">{t('knowledge.filename')} *</label>
              <input
                value={textForm.filename}
                onChange={e => setTextForm(f => ({ ...f, filename: e.target.value }))}
                placeholder="e.g. incident-response-playbook.md"
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">{t('knowledge.content')} *</label>
              <textarea
                value={textForm.content}
                onChange={e => setTextForm(f => ({ ...f, content: e.target.value }))}
                placeholder="Paste document text content here..."
                rows={8}
                className="form-textarea"
              />
            </div>
          </div>
        </Modal>
      )}

      {/* Two-column Master-Detail Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 20, alignItems: 'start' }}>
        {/* Sidebar: Knowledge Bases Card */}
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid var(--border)' }}>
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
              {t('knowledge.kbList').toUpperCase()}
            </span>
            <span className="badge badge-neutral">{bases.length}</span>
          </div>

          {loadingKB ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '32px 0' }}>
              <Loader2 size={16} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : bases.length === 0 ? (
            <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
              {t('knowledge.noBases')}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {bases.map(k => {
                const isSelected = selected?.id === k.id
                return (
                  <div
                    key={k.id}
                    data-item-id={k.id}
                    onClick={() => setSelected(k)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '10px 12px',
                      borderRadius: 0,
                      border: `1px solid ${isSelected ? 'var(--accent-border)' : 'var(--border)'}`,
                      background: isSelected ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                      cursor: 'pointer',
                      transition: 'all var(--transition-fast)',
                    }}
                  >
                    <Database
                      size={14}
                      style={{
                        color: isSelected ? 'var(--accent)' : 'var(--text-muted)',
                        flexShrink: 0,
                      }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: isSelected ? 600 : 500,
                          color: isSelected ? 'var(--accent)' : 'var(--text-primary)',
                          letterSpacing: '0.02em',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {k.name}
                      </div>
                      {(k.embedding_model || k.embedding_dim) && (
                        <div
                          style={{
                            fontSize: 11,
                            color: 'var(--text-dim)',
                            marginTop: 2,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {k.embedding_model || '—'}{k.embedding_dim ? ` · ${k.embedding_dim}d` : ''}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteKB(k) }}
                      title={t('common.delete', 'Delete')}
                      className="item-card-icon-btn danger"
                      style={{ flexShrink: 0 }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Main Content Area */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!selected ? (
            <div
              className="card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '64px 24px',
                textAlign: 'center',
                gap: 14,
              }}
            >
              <div style={{
                width: 48,
                height: 48,
                borderRadius: 0,
                background: 'var(--bg-elevated)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid var(--border)',
              }}>
                <Database size={24} style={{ color: 'var(--text-dim)' }} />
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                  {t('knowledge.selectKbHint')}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                  {t('knowledge.selectKbSubhint')}
                </div>
              </div>
              <button
                onClick={() => setShowKBForm(true)}
                className="btn btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}
              >
                <Plus size={13} /> {t('knowledge.newKb')}
              </button>
            </div>
          ) : (
            <>
              {/* Selected KB Info Card */}
              <div className="card" style={{ padding: '16px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
                      <h2 style={{ fontSize: 17, fontWeight: 700, letterSpacing: '0.04em', color: 'var(--text-primary)', margin: 0 }}>
                        {selected.name}
                      </h2>
                      <span className="badge badge-info">{docs.length} DOCS</span>
                      {selected.embedding_dim && (
                        <span className="badge badge-neutral">{selected.embedding_dim}d</span>
                      )}
                      {selected.embedding_model && (
                        <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
                          {selected.embedding_model}
                        </span>
                      )}
                      {selected.rerank_model && (
                        <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
                          rerank: {selected.rerank_model}
                        </span>
                      )}
                    </div>
                    {selected.description && (
                      <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.5 }}>
                        {selected.description}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => deleteKB(selected)}
                    className="btn btn-secondary btn-sm"
                    style={{ color: 'var(--red)', borderColor: 'rgba(248, 113, 113, 0.3)', flexShrink: 0 }}
                  >
                    <Trash2 size={12} /> {t('common.delete', 'DELETE')}
                  </button>
                </div>
              </div>

              {/* Semantic Search Card */}
              <div className="card" style={{ padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                  <Search size={14} style={{ color: 'var(--accent)' }} />
                  <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', color: 'var(--text-primary)' }}>
                    {t('knowledge.semanticSearch').toUpperCase()}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 10, marginBottom: results.length > 0 ? 16 : 0 }}>
                  <input
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && search()}
                    placeholder={t('knowledge.searchPlaceholder')}
                    className="form-input"
                    style={{ flex: 1 }}
                  />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>
                      {t('knowledge.topK', 'TOP-K')}
                    </span>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={topK}
                      onChange={e => setTopK(Number(e.target.value))}
                      className="form-input"
                      style={{ width: 64, textAlign: 'center', padding: '0 4px' }}
                    />
                  </div>
                  <button
                    onClick={search}
                    disabled={querying || docs.length === 0}
                    className="btn btn-primary"
                    style={{ flexShrink: 0, minWidth: 90, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
                  >
                    {querying ? (
                      <>
                        <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                        {t('knowledge.searching')}
                      </>
                    ) : (
                      <>
                        <Search size={13} />
                        {t('knowledge.searchBtn')}
                      </>
                    )}
                  </button>
                </div>

                {results.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
                    {results.map((r, i) => (
                      <div
                        key={i}
                        style={{
                          padding: 14,
                          background: 'var(--bg-elevated)',
                          border: '1px solid var(--border)',
                          borderLeft: '3px solid var(--accent)',
                          borderRadius: 0,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
                          <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', letterSpacing: '0.04em' }}>
                            {r.filename} <span style={{ color: 'var(--text-dim)', fontWeight: 400 }}>· Chunk #{r.chunk_index}</span>
                          </span>
                          <span
                            className="badge badge-info"
                            style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}
                          >
                            {(r.score * 100).toFixed(1)}%
                          </span>
                        </div>
                        <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, whiteSpace: 'pre-wrap', margin: 0 }}>
                          {r.text}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                {docs.length === 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', textAlign: 'center', padding: '12px 0' }}>
                    {t('knowledge.noDocsSearchHint')}
                  </div>
                )}
              </div>

              {/* Documents Card */}
              <div className="card" style={{ padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FileText size={14} style={{ color: 'var(--accent)' }} />
                    <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', color: 'var(--text-primary)' }}>
                      {t('knowledge.documents').toUpperCase()}
                    </span>
                    <span className="badge badge-neutral">{docs.length}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".txt,.md,.csv,.json,.html,.pdf,.docx,text/*,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(f) }}
                      style={{ display: 'none' }}
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={ingesting}
                      className="btn btn-secondary btn-sm"
                      style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      <Upload size={12} /> {t('knowledge.uploadFile')}
                    </button>
                    <button
                      onClick={() => setShowTextForm(true)}
                      className="btn btn-primary btn-sm"
                      style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      <Plus size={12} /> {t('knowledge.pasteText')}
                    </button>
                  </div>
                </div>

                {loadingDocs ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '32px 0' }}>
                    <Loader2 size={16} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
                  </div>
                ) : docs.length === 0 ? (
                  <div style={{
                    padding: '36px 16px',
                    textAlign: 'center',
                    color: 'var(--text-dim)',
                    fontSize: 12,
                    border: '1px dashed var(--border)',
                    borderRadius: 0,
                    background: 'var(--bg-elevated)',
                  }}>
                    {t('knowledge.noDocs')}
                  </div>
                ) : (
                  <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
                    <table className="data-table" style={{ width: '100%' }}>
                      <thead>
                        <tr>
                          <th>{t('knowledge.filename', 'DOCUMENT').toUpperCase()}</th>
                          <th style={{ textAlign: 'right' }}>{t('knowledge.chunks', 'CHUNKS').toUpperCase()}</th>
                          <th style={{ textAlign: 'right' }}>{t('knowledge.fileSize', 'SIZE').toUpperCase()}</th>
                          <th style={{ width: 60, textAlign: 'center' }}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {docs.map(d => (
                          <tr key={d.id}>
                            <td>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <FileText size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                                <span style={{
                                  fontSize: 13,
                                  fontWeight: 500,
                                  color: 'var(--text-primary)',
                                  letterSpacing: '0.02em',
                                }}>
                                  {d.filename}
                                </span>
                                {d.status === 'processing' && (
                                  <span className="badge badge-warning" style={{ fontSize: 10, flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} />
                                    {t('knowledge.ocrInProgress')}
                                  </span>
                                )}
                                {d.status === 'failed' && (
                                  <span title={d.status_detail || ''} className="badge badge-error" style={{ fontSize: 10, flexShrink: 0 }}>
                                    {t('knowledge.failed')}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                              {d.metadata_json?.chunk_count ?? 0}
                            </td>
                            <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                              {d.file_size != null ? `${(d.file_size / 1024).toFixed(1)} KB` : '—'}
                            </td>
                            <td style={{ textAlign: 'center' }}>
                              <button
                                onClick={() => deleteDoc(d)}
                                title={t('common.delete', 'Delete')}
                                className="item-card-icon-btn danger"
                                style={{ margin: '0 auto' }}
                              >
                                <Trash2 size={12} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
