import { useState, useEffect, useRef, useContext } from 'react'
import { api } from '../api/client'
import { Plus, Search, Trash2, Upload, FileText, Database, X, Loader2 } from 'lucide-react'
import { SearchContext } from '../context/SearchContext'

interface KB {
  id: number
  name: string
  description?: string
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
  models: ModelInfo[]
}

function OcrSettingsPanel() {
  const [cfg, setCfg] = useState<any>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { if (open && !cfg) api.getOcrConfig().then(setCfg) }, [open, cfg])
  if (!open) return (
    <button
      onClick={() => setOpen(true)}
      style={{
        fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none',
        cursor: 'pointer', letterSpacing: '0.06em', fontFamily: 'var(--font-mono)',
        padding: '0 4px',
      }}>
      OCR 设置 ▾
    </button>
  )
  if (!cfg) return <div style={{ fontSize: 12, color: 'var(--text-dim)', padding: '8px 0', letterSpacing: '0.06em' }}>加载中…</div>
  const save = async () => { await api.updateOcrConfig(cfg); setOpen(false) }
  return (
    <div style={{ border: '1px solid var(--border-bright)', borderRadius: 4, padding: 12, margin: '8px 0', background: 'var(--bg-surface)' }}>
      <label style={{ display: 'block', marginBottom: 6, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>
        <input type="checkbox" checked={cfg.enabled} onChange={e => setCfg({ ...cfg, enabled: e.target.checked })} style={{ marginRight: 6 }} />
        启用 OCR
      </label>
      <label style={{ display: 'block', marginBottom: 6, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>引擎:&nbsp;
        <select
          value={cfg.engine}
          onChange={e => setCfg({ ...cfg, engine: e.target.value })}
          style={{ background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          <option value="tesseract">Tesseract（本地）</option>
          <option value="vision">Vision LLM</option>
        </select>
      </label>
      {cfg.engine === 'vision' && (
        <>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>Vision Provider ID:&nbsp;
            <input
              type="number"
              value={cfg.vision_provider_id ?? ''}
              onChange={e => setCfg({ ...cfg, vision_provider_id: e.target.value ? Number(e.target.value) : null })}
              style={{ width: 70, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)', padding: '2px 6px' }} />
          </label>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>Vision 模型:&nbsp;
            <input
              value={cfg.vision_model ?? ''}
              onChange={e => setCfg({ ...cfg, vision_model: e.target.value })}
              style={{ width: 180, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)', padding: '2px 6px' }} />
          </label>
        </>
      )}
      <label style={{ display: 'block', marginBottom: 6, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>语言:&nbsp;
        <input
          value={cfg.languages}
          onChange={e => setCfg({ ...cfg, languages: e.target.value })}
          style={{ width: 120, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)', padding: '2px 6px' }} />
      </label>
      <label style={{ display: 'block', marginBottom: 10, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>最大页数:&nbsp;
        <input
          type="number"
          value={cfg.max_pages}
          onChange={e => setCfg({ ...cfg, max_pages: Number(e.target.value) })}
          style={{ width: 70, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)', padding: '2px 6px' }} />
      </label>
      <button
        onClick={save}
        style={{
          padding: '4px 14px', background: 'var(--accent)', color: '#000',
          border: 'none', borderRadius: 4, cursor: 'pointer',
          fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', fontFamily: 'var(--font-mono)',
        }}>
        保存
      </button>
      <button
        onClick={() => setOpen(false)}
        style={{
          marginLeft: 8, background: 'none', border: 'none', color: 'var(--text-muted)',
          cursor: 'pointer', fontSize: 12, letterSpacing: '0.06em', fontFamily: 'var(--font-mono)',
        }}>
        取消
      </button>
    </div>
  )
}

export default function Knowledge() {
  const [bases, setBases] = useState<KB[]>([])
  const [selected, setSelected] = useState<KB | null>(null)
  const [loadingKB, setLoadingKB] = useState(true)
  const [showKBForm, setShowKBForm] = useState(false)
  const [kbForm, setKBForm] = useState<Partial<KB>>({ name: '', description: '', embedding_model: 'text-embedding-3-small', embedding_dim: 1536 })
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

  const loadKBs = async () => {
    setLoadingKB(true)
    try {
      const data = await api.getKnowledgeBases() as { knowledge_bases?: KB[] }
      const list = data?.knowledge_bases || []
      setBases(list)
      if (list.length > 0 && !selected) setSelected(list[0])
    } catch { setBases([]) } finally { setLoadingKB(false) }
  }

  const loadDocs = async (kbId: number) => {
    setLoadingDocs(true)
    try {
      const data = await api.getDocuments(kbId) as { documents?: Doc[] }
      setDocs(data?.documents || [])
    } catch { setDocs([]) } finally { setLoadingDocs(false) }
  }

  const loadProviders = async () => {
    try {
      const data = await api.getProviders() as { providers?: ProviderOption[] }
      setProviders(data?.providers || [])
    } catch {}
  }

  useEffect(() => { loadKBs(); loadProviders() }, [])
  useEffect(() => { if (selected) { loadDocs(selected.id); setResults([]) } }, [selected?.id])

  // Poll every 5s while any document is still processing
  useEffect(() => {
    const hasProcessing = docs.some(d => d.status === 'processing')
    if (!hasProcessing) return
    const t = setInterval(() => { if (selected) loadDocs(selected.id) }, 5000)
    return () => clearInterval(t)
  }, [docs, selected?.id])

  const submitKB = async () => {
    if (!kbForm.name) return alert('NAME REQUIRED')
    try {
      await api.createKnowledgeBase(kbForm)
      setShowKBForm(false)
      setKBForm({ name: '', description: '', embedding_model: 'text-embedding-3-small', embedding_dim: 1536 })
      loadKBs()
    } catch (e: any) { alert(e.message) }
  }

  const deleteKB = async (kb: KB) => {
    if (!confirm(`DELETE "${kb.name}" AND ALL ITS DOCUMENTS?`)) return
    try {
      await api.deleteKnowledgeBase(kb.id)
      if (selected?.id === kb.id) setSelected(null)
      loadKBs()
    } catch (e: any) { alert(e.message) }
  }

  const ingestText = async () => {
    if (!selected || !textForm.filename || !textForm.content) return alert('FILL ALL FIELDS')
    setIngesting(true)
    try {
      await api.ingestText(selected.id, { filename: textForm.filename, content: textForm.content, provider_id: providerId ?? undefined })
      setTextForm({ filename: '', content: '' })
      setShowTextForm(false)
      loadDocs(selected.id)
    } catch (e: any) { alert(`INGEST FAILED: ${e.message}`) } finally { setIngesting(false) }
  }

  const uploadFile = async (file: File) => {
    if (!selected) return
    setIngesting(true)
    try {
      await api.uploadDocument(selected.id, file, providerId ?? undefined)
      loadDocs(selected.id)
    } catch (e: any) { alert(`UPLOAD FAILED: ${e.message}`) } finally {
      setIngesting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const deleteDoc = async (doc: Doc) => {
    if (!selected) return
    if (!confirm(`DELETE "${doc.filename}"?`)) return
    try {
      await api.deleteDocument(selected.id, doc.id)
      loadDocs(selected.id)
    } catch (e: any) { alert(e.message) }
  }

  const search = async () => {
    if (!selected) return alert('SELECT A KNOWLEDGE BASE FIRST')
    if (!query.trim()) return
    setQuerying(true)
    try {
      const res = await api.queryKnowledge({ kb_id: selected.id, query, top_k: topK, provider_id: providerId ?? undefined }) as { results: QueryResult[] }
      setResults(res.results || [])
    } catch (e: any) { alert(e.message) } finally { setQuerying(false) }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>SEMANTIC SEARCH</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>KNOWLEDGE BASE</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, letterSpacing: '0.06em', color: 'var(--text-dim)' }}>EMBEDDING</span>
            <select
              value={providerId ?? ''}
              onChange={e => setProviderId(Number(e.target.value) || null)}
              style={{
                height: 30, padding: '0 8px',
                background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)',
              }}>
              {providers.length === 0 && <option value="">NOT CONFIGURED</option>}
              {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button
            onClick={() => setShowKBForm(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '0 16px', height: 36,
              background: 'var(--accent)', border: '1px solid var(--accent-border)',
              color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em',
              cursor: 'pointer', fontFamily: 'var(--font-mono)',
              boxShadow: '0 0 16px rgba(0,255,65,0.15)',
            }}>
            <Plus size={13} /> NEW KB
          </button>
        </div>
      </div>

      {/* OCR Settings */}
      <OcrSettingsPanel />

      {/* New KB form */}
      {showKBForm && (
        <div style={{
          marginBottom: 24, padding: 24,
          background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>NEW KNOWLEDGE BASE</h3>
            <button onClick={() => setShowKBForm(false)} style={{ color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none', padding: 4 }}>
              <X size={14} />
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>NAME *</label>
              <input value={kbForm.name || ''} onChange={e => setKBForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Threat Intel DB"
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
            </div>
            <div>
              <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>
                <span>EMBEDDING MODEL</span>
                <span style={{ color: 'var(--accent)' }}>DIM: {kbForm.embedding_dim || 1536}</span>
              </label>
              <select value={kbForm.embedding_model || ''}
                onChange={e => {
                  const model = e.target.value
                  setKBForm(f => ({ ...f, embedding_model: model, embedding_dim: dimFromModel(model) }))
                }}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }}>
                <option value="">— None —</option>
                {providers.flatMap(p => p.models || []).filter((m: ModelInfo) => m.model_type === 'embedding').map((m: ModelInfo) => (
                  <option key={m.name} value={m.name}>{m.name}</option>
                ))}
              </select>
              <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.02em' }}>
                创建后维度不可改。3-large=3072，其他=1536。
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>RERANK MODEL</label>
              <select value={kbForm.rerank_model || ''} onChange={e => setKBForm(f => ({ ...f, rerank_model: e.target.value }))}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }}>
                <option value="">— None —</option>
                {providers.flatMap(p => p.models || []).filter((m: ModelInfo) => m.model_type === 'rerank').map((m: ModelInfo) => (
                  <option key={m.name} value={m.name}>{m.name}</option>
                ))}
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>DESCRIPTION</label>
              <input value={kbForm.description || ''} onChange={e => setKBForm(f => ({ ...f, description: e.target.value }))}
                style={{
                  width: '100%', height: 38, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
                  fontFamily: 'var(--font-mono)',
                }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 20 }}>
            <button onClick={() => setShowKBForm(false)}
              style={{
                padding: '0 16px', height: 36,
                border: '1px solid var(--border-bright)', background: 'transparent',
                color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
              }}>
              CANCEL
            </button>
            <button onClick={submitKB}
              style={{
                padding: '0 16px', height: 36,
                border: '1px solid var(--accent-border)', background: 'var(--accent)',
                color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
              }}>
              CREATE
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 16 }}>
        {/* Sidebar: KB list */}
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>KNOWLEDGE BASES</div>
          {loadingKB ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '20px 0' }}>
              <Loader2 size={14} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : bases.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>NO BASES DEFINED</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {bases.map(k => (
                <div
                  key={k.id}
                  data-item-id={k.id}
                  onClick={() => setSelected(k)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '10px 12px', cursor: 'pointer',
                    background: selected?.id === k.id ? 'var(--accent-dim)' : 'var(--bg-surface)',
                    borderLeft: selected?.id === k.id ? '2px solid var(--accent)' : '2px solid transparent',
                    borderBottom: '1px solid var(--border)',
                    transition: 'all 0.15s',
                  }}>
                  <Database size={12} style={{ color: selected?.id === k.id ? 'var(--accent)' : 'var(--text-muted)', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: selected?.id === k.id ? 'var(--accent)' : 'var(--text-primary)', letterSpacing: '0.05em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{k.name}</div>
                    {(k.embedding_model || k.embedding_dim) && (
                      <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {k.embedding_model || '—'}{k.embedding_dim ? ` · ${k.embedding_dim}d` : ''}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteKB(k) }}
                    style={{ padding: 2, color: 'var(--red)', cursor: 'pointer', background: 'none', border: 'none', flexShrink: 0 }}>
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Main */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!selected ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              padding: 48, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
              gap: 12,
            }}>
              <Database size={28} style={{ color: 'var(--text-dim)' }} />
              <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>SELECT OR CREATE A KNOWLEDGE BASE</div>
            </div>
          ) : (
            <>
              {/* KB Header */}
              <div style={{ padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em', marginBottom: 4 }}>{selected.name}</div>
                    {selected.description && <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{selected.description}</div>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>{docs.length} DOCS</div>
                </div>
              </div>

              {/* Query */}
              <div style={{ padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Search size={13} style={{ color: 'var(--accent)' }} />
                  <span style={{ fontSize: 13, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SEMANTIC SEARCH</span>
                </div>
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  <input value={query} onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && search()}
                    placeholder="ENTER QUERY..."
                    style={{
                      flex: 1, height: 36, padding: '0 12px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 13, letterSpacing: '0.05em',
                      fontFamily: 'var(--font-mono)',
                    }} />
                  <input type="number" min={1} max={20} value={topK}
                    onChange={e => setTopK(Number(e.target.value))}
                    title="TOP K"
                    style={{
                      width: 60, height: 36, padding: '0 8px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 13, textAlign: 'center',
                      fontFamily: 'var(--font-mono)',
                    }} />
                  <button onClick={search} disabled={querying || docs.length === 0}
                    style={{
                      padding: '0 14px', height: 36,
                      background: querying ? 'var(--bg-elevated)' : 'var(--accent)',
                      border: '1px solid var(--accent-border)',
                      color: querying ? 'var(--text-dim)' : '#000',
                      fontSize: 13, fontWeight: 700, letterSpacing: '0.1em', cursor: querying ? 'not-allowed' : 'pointer',
                      fontFamily: 'var(--font-mono)',
                    }}>
                    {querying ? 'SEARCHING...' : 'SEARCH'}
                  </button>
                </div>
                {results.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {results.map((r, i) => (
                      <div key={i} style={{
                        padding: 12,
                        background: 'var(--bg-base)', border: '1px solid var(--border)',
                        borderLeft: '2px solid var(--accent)',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                          <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>{r.filename} · CHUNK #{r.chunk_index}</span>
                          <span style={{
                            display: 'inline-block', padding: '1px 6px',
                            background: 'var(--accent-dim)', border: '1px solid var(--accent-border)',
                            color: 'var(--accent)', fontSize: 11, letterSpacing: '0.1em',
                          }}>
                            {(r.score * 100).toFixed(1)}%
                          </span>
                        </div>
                        <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{r.text}</p>
                      </div>
                    ))}
                  </div>
                )}
                {docs.length === 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.1em', textAlign: 'center', padding: '8px 0' }}>
                    UPLOAD DOCUMENTS BEFORE SEARCHING
                  </div>
                )}
              </div>

              {/* Docs */}
              <div style={{ padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FileText size={13} style={{ color: 'var(--accent)' }} />
                    <span style={{ fontSize: 13, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>DOCUMENTS</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".txt,.md,.csv,.json,.html,.pdf,.docx,text/*,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(f) }}
                      style={{ display: 'none' }}
                    />
                    <button onClick={() => fileInputRef.current?.click()} disabled={ingesting}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '0 10px', height: 30,
                        border: '1px solid var(--border-bright)', background: 'transparent',
                        color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: ingesting ? 'not-allowed' : 'pointer',
                        fontFamily: 'var(--font-mono)',
                      }}>
                      <Upload size={10} /> UPLOAD FILE
                    </button>
                    <button onClick={() => setShowTextForm(s => !s)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '0 10px', height: 30,
                        background: 'var(--accent)', border: '1px solid var(--accent-border)',
                        color: '#000', fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', cursor: 'pointer',
                        fontFamily: 'var(--font-mono)',
                      }}>
                      <Plus size={10} /> PASTE TEXT
                    </button>
                  </div>
                </div>

                {showTextForm && (
                  <div style={{ padding: 12, background: 'var(--bg-base)', border: '1px solid var(--border)', marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <input
                      value={textForm.filename}
                      onChange={e => setTextForm(f => ({ ...f, filename: e.target.value }))}
                      placeholder="FILENAME (e.g. incident-response.md)"
                      style={{
                        width: '100%', height: 34, padding: '0 10px',
                        background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                        color: 'var(--text-primary)', fontSize: 13, letterSpacing: '0.05em',
                        fontFamily: 'var(--font-mono)',
                      }} />
                    <textarea
                      value={textForm.content}
                      onChange={e => setTextForm(f => ({ ...f, content: e.target.value }))}
                      placeholder="PASTE TEXT CONTENT..."
                      rows={6}
                      style={{
                        width: '100%', padding: '8px 10px',
                        background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                        color: 'var(--text-primary)', fontSize: 13, letterSpacing: '0.05em',
                        fontFamily: 'var(--font-mono)', resize: 'none',
                      }} />
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                      <button onClick={() => setShowTextForm(false)}
                        style={{
                          padding: '0 12px', height: 30,
                          border: '1px solid var(--border-bright)', background: 'transparent',
                          color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer',
                          fontFamily: 'var(--font-mono)',
                        }}>
                        CANCEL
                      </button>
                      <button onClick={ingestText} disabled={ingesting}
                        style={{
                          padding: '0 12px', height: 30,
                          background: 'var(--accent)', border: '1px solid var(--accent-border)',
                          color: '#000', fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', cursor: ingesting ? 'not-allowed' : 'pointer',
                          fontFamily: 'var(--font-mono)',
                        }}>
                        {ingesting ? 'IMPORTING...' : 'IMPORT'}
                      </button>
                    </div>
                  </div>
                )}

                {loadingDocs ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '20px 0' }}>
                    <Loader2 size={14} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
                  </div>
                ) : docs.length === 0 ? (
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.1em', textAlign: 'center', padding: '20px 0' }}>NO DOCUMENTS — UPLOAD OR PASTE CONTENT</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {docs.map(d => (
                      <div key={d.id} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 12px',
                        background: 'var(--bg-base)', border: '1px solid var(--border)',
                      }}>
                        <FileText size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflow: 'hidden' }}>
                            <span style={{ fontSize: 13, color: 'var(--text-primary)', letterSpacing: '0.05em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename}</span>
                            {d.status === 'processing' && (
                              <span style={{ fontSize: 11, color: '#f59e0b', letterSpacing: '0.08em', flexShrink: 0 }}>● OCR 识别中…</span>
                            )}
                            {d.status === 'failed' && (
                              <span title={d.status_detail || ''} style={{ fontSize: 11, color: '#f87171', letterSpacing: '0.08em', flexShrink: 0 }}>● 失败</span>
                            )}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                            {d.metadata_json?.chunk_count ?? 0} CHUNKS
                            {d.file_size != null && ` · ${(d.file_size / 1024).toFixed(1)} KB`}
                          </div>
                        </div>
                        <button onClick={() => deleteDoc(d)} style={{ padding: 4, color: 'var(--red)', cursor: 'pointer', background: 'none', border: 'none' }}>
                          <Trash2 size={11} />
                        </button>
                      </div>
                    ))}
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
