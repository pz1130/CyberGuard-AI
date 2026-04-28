import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Plus, Search } from 'lucide-react'

interface KB {
  id?: string
  name: string
  description?: string
  embedding_model?: string
}

export default function Knowledge() {
  const [bases, setBases] = useState<KB[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<KB>({ name: '', description: '' })
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [querying, setQuerying] = useState(false)

  const load = async () => {
    try {
      const data = await api.getKnowledgeBases() as KB[] | { bases?: KB[] }
      setBases(Array.isArray(data) ? data : data?.bases || [])
    } catch { setBases([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      await api.createKnowledgeBase(form)
      setShowForm(false); setForm({ name: '', description: '' }); load()
    } catch (e: any) { alert(e.message) }
  }

  const search = async () => {
    if (!query.trim()) return
    setQuerying(true)
    try {
      const res = await api.queryKnowledge({ query, top_k: 5 }) as any
      setResults(res.results || res || [])
    } catch (e: any) { alert(e.message) }
    finally { setQuerying(false) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">知识库</h2>
        <button onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增知识库
        </button>
      </div>

      {/* Search */}
      <div className="bg-gray-800 rounded-xl p-4 mb-6">
        <h3 className="text-sm font-medium mb-3 text-gray-300">知识检索</h3>
        <div className="flex gap-2">
          <input value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            className="flex-1 bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="输入查询内容..." />
          <button onClick={search} disabled={querying}
            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-white rounded-lg text-sm">
            <Search size={16} />
          </button>
        </div>
        {results.length > 0 && (
          <div className="mt-3 space-y-2">
            {results.map((r, i) => (
              <div key={i} className="bg-gray-700 rounded-lg p-3">
                <p className="text-sm text-gray-200">{typeof r === 'string' ? r : r.content || r.text || JSON.stringify(r)}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <div className="bg-gray-800 rounded-xl p-6 mb-6 space-y-4">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">名称</label>
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">描述</label>
            <input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm">创建</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-gray-400">加载中...</p> : bases.length === 0 ? <p className="text-gray-500">暂无知识库</p> : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {bases.map(k => (
            <div key={k.id} className="bg-gray-800 rounded-xl p-4">
              <div className="flex items-start justify-between">
                <div>
                  <span className="font-medium text-white">{k.name}</span>
                  <p className="text-xs text-gray-400 mt-1">{k.description || '—'}</p>
                  {k.embedding_model && <p className="text-xs text-gray-500 mt-1">模型: {k.embedding_model}</p>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
