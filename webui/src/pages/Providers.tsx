import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, X } from 'lucide-react'

interface Provider {
  id?: string
  name: string
  provider_type: string
  api_base?: string
  api_key?: string
  models: string[]
  is_default?: boolean
}

export default function Providers() {
  const [items, setItems] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Provider>({ name: '', provider_type: 'openai', models: [] })
  const [modelInput, setModelInput] = useState('')

  const load = async () => {
    try {
      const data = await api.getProviders() as Provider[] | { providers?: Provider[] }
      setItems(Array.isArray(data) ? data : data?.providers || [])
    } catch { setItems([]) } finally { setLoading(false) }
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
        await api.updateProvider(editing, form)
      } else {
        await api.createProvider(form)
      }
      setShowForm(false)
      setEditing(null)
      setForm({ name: '', provider_type: 'openai', models: [] })
      load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: string) => {
    if (!confirm('确认删除？')) return
    await api.deleteProvider(id)
    load()
  }

  const startEdit = (p: Provider) => {
    setEditing(p.id!)
    setForm({ ...p })
    setShowForm(true)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">AI Provider 配置</h2>
        <button onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', provider_type: 'openai', models: [] }) }}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增 Provider
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-800 rounded-xl p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">名称</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="e.g. OpenAI" />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">类型</label>
              <select value={form.provider_type} onChange={e => setForm(f => ({ ...f, provider_type: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white">
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="azure">Azure OpenAI</option>
                <option value="google">Google Gemini</option>
                <option value="ollama">Ollama</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs text-gray-400 mb-1 block">API Base URL</label>
              <input value={form.api_base || ''} onChange={e => setForm(f => ({ ...f, api_base: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="https://api.openai.com/v1" />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-gray-400 mb-1 block">API Key</label>
              <input type="password" value={form.api_key || ''} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="sk-..." />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">模型（按回车添加）</label>
            <div className="flex gap-2 mb-2">
              <input value={modelInput} onChange={e => setModelInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addModel())}
                className="flex-1 bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="gpt-4o" />
              <button onClick={addModel} className="px-3 py-2 bg-gray-700 text-white rounded-lg text-sm">+</button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.models.map(m => (
                <span key={m} className="inline-flex items-center gap-1 px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded text-xs">
                  {m} <X size={10} className="cursor-pointer" onClick={() => setForm(f => ({ ...f, models: f.models.filter(x => x !== m) }))} />
                </span>
              ))}
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowForm(false); setEditing(null) }} className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm">{editing ? '保存' : '创建'}</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-gray-400">加载中...</p> : items.length === 0 ? <p className="text-gray-500">暂无 Provider</p> : (
        <div className="space-y-3">
          {items.map(p => (
            <div key={p.id} className="bg-gray-800 rounded-xl p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white">{p.name}</span>
                  <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded">{p.provider_type}</span>
                  {p.is_default && <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">默认</span>}
                </div>
                <p className="text-xs text-gray-400 mt-1">{p.api_base || 'Default'}</p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(p.models || []).map(m => <span key={m} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{m}</span>)}
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => startEdit(p)} className="p-2 text-gray-400 hover:text-white"><Edit2 size={14} /></button>
                <button onClick={() => del(p.id!)} className="p-2 text-gray-400 hover:text-red-400"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
