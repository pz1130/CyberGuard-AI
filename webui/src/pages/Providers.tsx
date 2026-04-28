import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, X, Zap, ZapOff } from 'lucide-react'

interface Provider {
  id?: number
  name: string
  provider_type: string
  base_url?: string
  api_key?: string
  api_version?: string
  models: string[]
  is_active?: boolean
}

export default function Providers() {
  const [items, setItems] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState<Provider>({
    name: '',
    provider_type: 'openai',
    base_url: '',
    api_key: '',
    models: [],
  })
  const [modelInput, setModelInput] = useState('')
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<Record<number, { success: boolean; latency_ms?: number; error?: string; model?: string }>>({})

  const load = async () => {
    try {
      const data = await api.getProviders() as { total: number; providers: Provider[] }
      setItems(data?.providers || [])
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const addModel = () => {
    if (!modelInput.trim()) return
    setForm(f => ({ ...f, models: [...f.models, modelInput.trim()] }))
    setModelInput('')
  }

  const submit = async () => {
    if (!form.name) return
    try {
      if (editing) {
        await api.updateProvider(String(editing), form)
      } else {
        await api.createProvider(form)
      }
      setShowForm(false)
      setEditing(null)
      setForm({ name: '', provider_type: 'openai', base_url: '', api_key: '', models: [] })
      load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: number) => {
    if (!confirm('确认删除？')) return
    await api.deleteProvider(String(id))
    load()
  }

  const startEdit = (p: Provider) => {
    setEditing(p.id!)
    setForm({ ...p })
    setShowForm(true)
  }

  const testConnection = async (id: number) => {
    setTestingId(id)
    setTestResult(r => ({ ...r, [id]: { success: false } }))
    try {
      const result = await api.testProvider(id) as { success: boolean; latency_ms?: number; error?: string; model?: string }
      setTestResult(r => ({ ...r, [id]: result }))
    } catch (e: any) {
      setTestResult(r => ({ ...r, [id]: { success: false, error: e.message } }))
    } finally {
      setTestingId(null)
    }
  }

  const statusIcon = (p: Provider) => {
    const r = testResult[p.id!]
    if (!r) return null
    if (r.success) {
      return (
        <span title={`✓ 延迟 ${r.latency_ms}ms${r.error ? ' — ' + r.error : ''}`}
          className="flex items-center gap-1 text-xs text-violet-400">
          <Zap size={12} /> {r.latency_ms}ms
        </span>
      )
    }
    return (
      <span title={r.error || '连接失败'} className="flex items-center gap-1 text-xs text-red-400">
        <ZapOff size={12} /> {r.error?.slice(0, 40) || '失败'}
      </span>
    )
  }

  const providerTypeOptions = [
    { value: 'openai', label: 'OpenAI (兼容)' },
    { value: 'anthropic', label: 'Anthropic' },
    { value: 'azure', label: 'Azure OpenAI' },
    { value: 'groq', label: 'Groq' },
    { value: 'openrouter', label: 'OpenRouter' },
    { value: 'ollama', label: 'Ollama (本地)' },
    { value: 'custom', label: 'Custom' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">AI Provider 配置</h2>
        <button onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', provider_type: 'openai', base_url: '', api_key: '', models: [] }) }}
          className="flex items-center gap-2 px-4 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增 Provider
        </button>
      </div>

      {showForm && (
        <div className="bg-slate-900 rounded-xl p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">名称</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" placeholder="e.g. OpenAI" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">类型</label>
              <select value={form.provider_type} onChange={e => setForm(f => ({ ...f, provider_type: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white">
                {providerTypeOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-400 mb-1 block">API Base URL</label>
              <input value={form.base_url || ''} onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                placeholder={form.provider_type === 'ollama' ? 'http://localhost:11434/v1' : 'https://api.openai.com/v1'} />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-400 mb-1 block">API Key</label>
              <input type="password" value={form.api_key || ''} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" placeholder={form.provider_type === 'ollama' ? '任意非空字符串' : 'sk-...'} />
            </div>
            {form.provider_type === 'azure' && (
              <div className="col-span-2">
                <label className="text-xs text-slate-400 mb-1 block">API Version</label>
                <input value={form.api_version || ''} onChange={e => setForm(f => ({ ...f, api_version: e.target.value }))}
                  className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" placeholder="2024-02-01" />
              </div>
            )}
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">模型列表（按回车添加）</label>
            <div className="flex gap-2 mb-2">
              <input value={modelInput} onChange={e => setModelInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addModel())}
                className="flex-1 bg-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                placeholder={form.models[0] || 'gpt-4o'} />
              <button onClick={addModel} className="px-3 py-2 bg-slate-800 text-white rounded-lg text-sm hover:bg-slate-600">+</button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.models.map(m => (
                <span key={m} className="inline-flex items-center gap-1 px-2 py-1 bg-violet-500/20 text-violet-400 rounded text-xs">
                  {m} <X size={10} className="cursor-pointer hover:text-white" onClick={() => setForm(f => ({ ...f, models: f.models.filter(x => x !== m) }))} />
                </span>
              ))}
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowForm(false); setEditing(null) }} className="px-4 py-2 bg-slate-800 text-white rounded-lg text-sm hover:bg-slate-600">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-violet-500 text-white rounded-lg text-sm hover:bg-violet-600">{editing ? '保存' : '创建'}</button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-slate-400">加载中...</p>
      ) : items.length === 0 ? (
        <p className="text-slate-500">暂无 Provider，请点击上方「新增 Provider」添加</p>
      ) : (
        <div className="space-y-3">
          {items.map(p => (
            <div key={p.id} className="bg-slate-900 rounded-xl p-4 flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-white">{p.name}</span>
                  <span className="text-xs bg-violet-500/20 text-violet-400 px-2 py-0.5 rounded">{p.provider_type}</span>
                  {p.is_active === false && <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded">已禁用</span>}
                </div>
                <p className="text-xs text-slate-400 mt-1 truncate">{p.base_url || '(使用默认地址)'}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(p.models || []).map(m => (
                    <span key={m} className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded">{m}</span>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {statusIcon(p)}
                <button
                  onClick={() => testConnection(p.id!)}
                  disabled={testingId === p.id}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-600 text-slate-300 rounded-lg disabled:opacity-50"
                  title="测试连接"
                >
                  {testingId === p.id ? (
                    <span className="animate-spin">↻</span>
                  ) : (
                    <Zap size={12} />
                  )}
                  {testingId === p.id ? '测试中...' : '测试'}
                </button>
                <button onClick={() => startEdit(p)} className="p-2 text-slate-400 hover:text-white"><Edit2 size={14} /></button>
                <button onClick={() => del(p.id!)} className="p-2 text-slate-400 hover:text-red-400"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
