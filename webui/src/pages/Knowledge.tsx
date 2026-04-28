import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { Plus, Search, Trash2, Upload, FileText, Database, X } from 'lucide-react'

interface KB {
  id: number
  name: string
  description?: string
  embedding_model?: string
  rerank_model?: string
  is_active?: boolean
  created_at?: string
}

interface Doc {
  id: number
  kb_id: number
  filename: string
  file_size?: number
  mime_type?: string
  metadata_json?: { chunk_count?: number }
  created_at?: string
}

interface QueryResult {
  document_id: number
  filename: string
  chunk_index: number
  text: string
  score: number
}

interface ProviderOption {
  id: number
  name: string
  models: string[]
}

export default function Knowledge() {
  // KB state
  const [bases, setBases] = useState<KB[]>([])
  const [selected, setSelected] = useState<KB | null>(null)
  const [loadingKB, setLoadingKB] = useState(true)

  // KB form
  const [showKBForm, setShowKBForm] = useState(false)
  const [kbForm, setKBForm] = useState<Partial<KB>>({ name: '', description: '', embedding_model: 'text-embedding-3-small' })

  // Documents state
  const [docs, setDocs] = useState<Doc[]>([])
  const [loadingDocs, setLoadingDocs] = useState(false)

  // Ingest state
  const [textForm, setTextForm] = useState({ filename: '', content: '' })
  const [showTextForm, setShowTextForm] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Query state
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [results, setResults] = useState<QueryResult[]>([])
  const [querying, setQuerying] = useState(false)

  // Providers (for embedding)
  const [providers, setProviders] = useState<ProviderOption[]>([])
  const [providerId, setProviderId] = useState<number | null>(null)

  // ----- Load -----
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
      const list = data?.providers || []
      setProviders(list)
      if (list.length > 0 && providerId == null) setProviderId(list[0].id)
    } catch { /* ignore */ }
  }

  useEffect(() => { loadKBs(); loadProviders() }, [])
  useEffect(() => { if (selected) { loadDocs(selected.id); setResults([]) } }, [selected?.id])

  // ----- KB CRUD -----
  const submitKB = async () => {
    if (!kbForm.name) return alert('请输入知识库名称')
    try {
      await api.createKnowledgeBase(kbForm)
      setShowKBForm(false)
      setKBForm({ name: '', description: '', embedding_model: 'text-embedding-3-small' })
      loadKBs()
    } catch (e: any) { alert(e.message) }
  }

  const deleteKB = async (kb: KB) => {
    if (!confirm(`确认删除知识库 "${kb.name}"？此操作会删除其中所有文档`)) return
    try {
      await api.deleteKnowledgeBase(kb.id)
      if (selected?.id === kb.id) setSelected(null)
      loadKBs()
    } catch (e: any) { alert(e.message) }
  }

  // ----- Document Ingest -----
  const ingestText = async () => {
    if (!selected) return
    if (!textForm.filename || !textForm.content) return alert('请填写文件名和内容')
    setIngesting(true)
    try {
      await api.ingestText(selected.id, {
        filename: textForm.filename,
        content: textForm.content,
        provider_id: providerId ?? undefined,
      })
      setTextForm({ filename: '', content: '' })
      setShowTextForm(false)
      loadDocs(selected.id)
    } catch (e: any) { alert(`导入失败: ${e.message}`) } finally { setIngesting(false) }
  }

  const uploadFile = async (file: File) => {
    if (!selected) return
    setIngesting(true)
    try {
      await api.uploadDocument(selected.id, file, providerId ?? undefined)
      loadDocs(selected.id)
    } catch (e: any) { alert(`上传失败: ${e.message}`) } finally {
      setIngesting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const deleteDoc = async (doc: Doc) => {
    if (!selected) return
    if (!confirm(`确认删除文档 "${doc.filename}"？`)) return
    try {
      await api.deleteDocument(selected.id, doc.id)
      loadDocs(selected.id)
    } catch (e: any) { alert(e.message) }
  }

  // ----- Query -----
  const search = async () => {
    if (!selected) return alert('请先选择知识库')
    if (!query.trim()) return
    setQuerying(true)
    try {
      const res = await api.queryKnowledge({
        kb_id: selected.id,
        query,
        top_k: topK,
        provider_id: providerId ?? undefined,
      }) as { results: QueryResult[]; message?: string }
      setResults(res.results || [])
      if (res.message) alert(res.message)
    } catch (e: any) { alert(e.message) } finally { setQuerying(false) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">知识库</h2>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Embedding Provider:</span>
            <select
              value={providerId ?? ''}
              onChange={e => setProviderId(Number(e.target.value) || null)}
              className="bg-slate-900 border border-slate-800 text-white text-xs rounded-lg px-2 py-1.5"
            >
              {providers.length === 0 && <option value="">未配置</option>}
              {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button
            onClick={() => setShowKBForm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-lg text-sm"
          >
            <Plus size={16} /> 新增知识库
          </button>
        </div>
      </div>

      {/* New KB form */}
      {showKBForm && (
        <div className="bg-slate-900 rounded-xl p-6 mb-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-slate-300">创建知识库</h3>
            <button onClick={() => setShowKBForm(false)}><X size={16} className="text-slate-400" /></button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">名称 *</label>
              <input value={kbForm.name || ''} onChange={e => setKBForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" placeholder="威胁情报库" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Embedding 模型</label>
              <input value={kbForm.embedding_model || ''} onChange={e => setKBForm(f => ({ ...f, embedding_model: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" placeholder="text-embedding-3-small" />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-400 mb-1 block">描述</label>
              <input value={kbForm.description || ''} onChange={e => setKBForm(f => ({ ...f, description: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowKBForm(false)} className="px-4 py-2 bg-slate-800 text-white rounded-lg text-sm">取消</button>
            <button onClick={submitKB} className="px-4 py-2 bg-violet-500 text-white rounded-lg text-sm">创建</button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        {/* Sidebar: KB list */}
        <div className="col-span-3">
          <h3 className="text-xs font-semibold text-slate-400 uppercase mb-2">知识库列表</h3>
          {loadingKB ? <p className="text-slate-400 text-sm">加载中...</p>
            : bases.length === 0 ? <p className="text-slate-500 text-sm">暂无知识库</p>
            : (
              <div className="space-y-1">
                {bases.map(k => (
                  <div key={k.id}
                    className={`group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${selected?.id === k.id ? 'bg-violet-500/20 border border-violet-500/40' : 'bg-slate-900 hover:bg-slate-800'}`}
                    onClick={() => setSelected(k)}>
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <Database size={14} className={selected?.id === k.id ? 'text-violet-400' : 'text-slate-400'} />
                      <div className="min-w-0">
                        <p className="text-sm text-white truncate">{k.name}</p>
                        {k.embedding_model && <p className="text-xs text-slate-500 truncate">{k.embedding_model}</p>}
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteKB(k) }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
        </div>

        {/* Main: docs + query */}
        <div className="col-span-9 space-y-4">
          {!selected ? (
            <div className="bg-slate-900 rounded-xl p-12 text-center">
              <Database size={32} className="mx-auto text-slate-500 mb-3" />
              <p className="text-slate-400">请从左侧选择或创建一个知识库</p>
            </div>
          ) : (
            <>
              {/* Header */}
              <div className="bg-slate-900 rounded-xl p-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-lg font-semibold text-white">{selected.name}</h3>
                  <span className="text-xs text-slate-400">{docs.length} 个文档</span>
                </div>
                {selected.description && <p className="text-sm text-slate-400">{selected.description}</p>}
              </div>

              {/* Query */}
              <div className="bg-slate-900 rounded-xl p-4">
                <h3 className="text-sm font-medium mb-3 text-slate-300 flex items-center gap-2">
                  <Search size={14} /> 语义检索
                </h3>
                <div className="flex gap-2 mb-3">
                  <input value={query} onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && search()}
                    className="flex-1 bg-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                    placeholder="输入要检索的内容..." />
                  <input type="number" min={1} max={20} value={topK}
                    onChange={e => setTopK(Number(e.target.value))}
                    className="w-20 bg-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                    title="返回结果数量" />
                  <button onClick={search} disabled={querying || docs.length === 0}
                    className="px-4 py-2 bg-violet-500 hover:bg-violet-600 disabled:opacity-50 text-white rounded-lg text-sm flex items-center gap-1">
                    <Search size={14} /> {querying ? '检索中' : '检索'}
                  </button>
                </div>
                {results.length > 0 && (
                  <div className="space-y-2">
                    {results.map((r, i) => (
                      <div key={i} className="bg-slate-800 rounded-lg p-3 border-l-2 border-violet-500">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-slate-400">{r.filename} · 块 #{r.chunk_index}</span>
                          <span className="text-xs px-2 py-0.5 bg-violet-500/20 text-violet-400 rounded">
                            {(r.score * 100).toFixed(1)}%
                          </span>
                        </div>
                        <p className="text-sm text-slate-200 whitespace-pre-wrap">{r.text}</p>
                      </div>
                    ))}
                  </div>
                )}
                {docs.length === 0 && (
                  <p className="text-xs text-slate-500 text-center py-2">先在下方上传文档后再检索</p>
                )}
              </div>

              {/* Docs */}
              <div className="bg-slate-900 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-slate-300 flex items-center gap-2">
                    <FileText size={14} /> 文档
                  </h3>
                  <div className="flex items-center gap-2">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".txt,.md,.csv,.json,text/*"
                      onChange={(e) => {
                        const f = e.target.files?.[0]
                        if (f) uploadFile(f)
                      }}
                      className="hidden"
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={ingesting}
                      className="flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-600 disabled:opacity-50 text-white rounded-lg text-xs"
                    >
                      <Upload size={12} /> 上传文件
                    </button>
                    <button
                      onClick={() => setShowTextForm(s => !s)}
                      className="flex items-center gap-1 px-3 py-1.5 bg-violet-500 hover:bg-violet-600 text-white rounded-lg text-xs"
                    >
                      <Plus size={12} /> 粘贴文本
                    </button>
                  </div>
                </div>

                {showTextForm && (
                  <div className="bg-slate-800 rounded-lg p-3 mb-3 space-y-2">
                    <input
                      value={textForm.filename}
                      onChange={e => setTextForm(f => ({ ...f, filename: e.target.value }))}
                      placeholder="文档名（如 incident-response.md）"
                      className="w-full bg-slate-900 rounded px-3 py-2 text-sm text-white"
                    />
                    <textarea
                      value={textForm.content}
                      onChange={e => setTextForm(f => ({ ...f, content: e.target.value }))}
                      placeholder="粘贴文本内容..."
                      rows={6}
                      className="w-full bg-slate-900 rounded px-3 py-2 text-sm text-white font-mono"
                    />
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setShowTextForm(false)} className="px-3 py-1.5 bg-slate-600 text-white rounded text-xs">取消</button>
                      <button onClick={ingestText} disabled={ingesting} className="px-3 py-1.5 bg-violet-500 disabled:opacity-50 text-white rounded text-xs">
                        {ingesting ? '导入中...' : '导入'}
                      </button>
                    </div>
                  </div>
                )}

                {loadingDocs ? <p className="text-slate-400 text-sm">加载中...</p>
                  : docs.length === 0 ? <p className="text-slate-500 text-sm text-center py-4">暂无文档，请上传或粘贴内容</p>
                  : (
                    <div className="space-y-2">
                      {docs.map(d => (
                        <div key={d.id} className="flex items-center justify-between bg-slate-800 rounded-lg px-3 py-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <FileText size={14} className="text-slate-400 flex-shrink-0" />
                            <div className="min-w-0">
                              <p className="text-sm text-white truncate">{d.filename}</p>
                              <p className="text-xs text-slate-400">
                                {d.metadata_json?.chunk_count ?? 0} 块
                                {d.file_size != null && ` · ${(d.file_size / 1024).toFixed(1)} KB`}
                                {d.mime_type && ` · ${d.mime_type}`}
                              </p>
                            </div>
                          </div>
                          <button onClick={() => deleteDoc(d)} className="p-1.5 text-slate-400 hover:text-red-400">
                            <Trash2 size={12} />
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
