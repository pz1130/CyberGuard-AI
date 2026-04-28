import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2 } from 'lucide-react'

interface Skill {
  id?: string
  name: string
  description?: string
  type: string
  config?: any
}

export default function Skills() {
  const [items, setItems] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Skill>({ name: '', type: 'tool', description: '' })
  const [configText, setConfigText] = useState('')

  const load = async () => {
    try {
      const data = await api.getSkills() as Skill[] | { skills?: Skill[] }
      setItems(Array.isArray(data) ? data : data?.skills || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      const payload = { ...form, config: configText ? JSON.parse(configText) : {} }
      if (editing) await api.updateSkill(editing, payload)
      else await api.createSkill(payload)
      setShowForm(false); setEditing(null)
      setForm({ name: '', type: 'tool', description: '' }); setConfigText('')
      load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: string) => { if (confirm('确认删除？')) { await api.deleteSkill(id); load() } }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">Skill Pool</h2>
        <button onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', type: 'tool', description: '' }); setConfigText('') }}
          className="flex items-center gap-2 px-4 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增 Skill
        </button>
      </div>

      {showForm && (
        <div className="bg-slate-900 rounded-xl p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">名称</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">类型</label>
              <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white">
                <option value="tool">Tool</option>
                <option value="skill">Skill</option>
                <option value="workflow">Workflow</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-400 mb-1 block">描述</label>
              <input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-slate-400 mb-1 block">配置 (JSON)</label>
              <textarea value={configText} onChange={e => setConfigText(e.target.value)}
                rows={4} className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono" placeholder="{}" />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-slate-800 text-white rounded-lg text-sm">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-violet-500 text-white rounded-lg text-sm">{editing ? '保存' : '创建'}</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-slate-400">加载中...</p> : items.length === 0 ? <p className="text-slate-500">暂无 Skill</p> : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map(s => (
            <div key={s.id} className="bg-slate-900 rounded-xl p-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <span className="font-medium text-white">{s.name}</span>
                  <span className="ml-2 text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">{s.type}</span>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => { setEditing(s.id!); setForm({ ...s }); setShowForm(true) }} className="p-1.5 text-slate-400 hover:text-white"><Edit2 size={14} /></button>
                  <button onClick={() => del(s.id!)} className="p-1.5 text-slate-400 hover:text-red-400"><Trash2 size={14} /></button>
                </div>
              </div>
              <p className="text-xs text-slate-400">{s.description || '—'}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
