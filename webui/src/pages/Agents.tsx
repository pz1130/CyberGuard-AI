import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Play } from 'lucide-react'

interface Agent {
  id?: string
  name: string
  agent_type: string
  description?: string
  model?: string
  skills?: string[]
  is_active?: boolean
}

export default function Agents() {
  const [items, setItems] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Agent>({ name: '', agent_type: 'sub_agent', description: '', model: '' })
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState('')

  const load = async () => {
    try {
      const data = await api.getAgents() as Agent[] | { agents?: Agent[] }
      setItems(Array.isArray(data) ? data : data?.agents || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      if (editing) await api.updateAgent(editing, form)
      else await api.createAgent(form)
      setShowForm(false); setEditing(null)
      setForm({ name: '', agent_type: 'sub_agent', description: '', model: '' })
      load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: string) => {
    if (!confirm('确认删除？')) return
    await api.deleteAgent(id); load()
  }

  const test = async (id: string) => {
    setTesting(id); setTestResult('')
    try {
      const res = await api.testAgent(id, { message: 'Hello' }) as any
      setTestResult(res.response || res.reply || JSON.stringify(res))
    } catch (e: any) { setTestResult(`错误: ${e.message}`) }
    finally { setTesting(null) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">Sub-Agent 管理</h2>
        <button onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', agent_type: 'sub_agent', description: '', model: '' }) }}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增 Agent
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-800 rounded-xl p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">名称</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">类型</label>
              <select value={form.agent_type} onChange={e => setForm(f => ({ ...f, agent_type: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white">
                <option value="sub_agent">Sub Agent</option>
                <option value="master">Master Agent</option>
                <option value="specialist">Specialist</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">模型</label>
              <input value={form.model || ''} onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="gpt-4o" />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-gray-400 mb-1 block">描述</label>
              <input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowForm(false); setEditing(null) }} className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm">{editing ? '保存' : '创建'}</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-gray-400">加载中...</p> : items.length === 0 ? <p className="text-gray-500">暂无 Agent</p> : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map(a => (
            <div key={a.id} className="bg-gray-800 rounded-xl p-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <span className="font-medium text-white">{a.name}</span>
                  <span className="ml-2 text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">{a.agent_type}</span>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => test(a.id!)} className="p-1.5 text-gray-400 hover:text-emerald-400" title="测试"><Play size={14} /></button>
                  <button onClick={() => { setEditing(a.id!); setForm({ ...a }); setShowForm(true) }} className="p-1.5 text-gray-400 hover:text-white"><Edit2 size={14} /></button>
                  <button onClick={() => del(a.id!)} className="p-1.5 text-gray-400 hover:text-red-400"><Trash2 size={14} /></button>
                </div>
              </div>
              <p className="text-xs text-gray-400 mb-2">{a.description || '—'}</p>
              {a.model && <p className="text-xs text-gray-500">模型: {a.model}</p>}
              {testResult && testing === null && (
                <p className="text-xs mt-2 p-2 bg-gray-700 rounded text-gray-300">{testResult}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
