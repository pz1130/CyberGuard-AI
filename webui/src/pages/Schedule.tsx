import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2 } from 'lucide-react'

interface Task {
  id?: string
  name: string
  task_type: string
  cron?: string
  agent_id?: string
  payload?: any
  is_active?: boolean
  next_run?: string
}

export default function Schedule() {
  const [items, setItems] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Task>({ name: '', task_type: 'scheduled', cron: '' })

  const load = async () => {
    try {
      const data = await api.getScheduledTasks() as Task[] | { tasks?: Task[] }
      setItems(Array.isArray(data) ? data : data?.tasks || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      if (editing) await api.updateScheduledTask(editing, form)
      else await api.createScheduledTask(form)
      setShowForm(false); setEditing(null)
      setForm({ name: '', task_type: 'scheduled', cron: '' }); load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: string) => { if (confirm('确认删除？')) { await api.deleteScheduledTask(id); load() } }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">定时任务</h2>
        <button onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', task_type: 'scheduled', cron: '' }) }}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增任务
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-800 rounded-xl p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">任务名称</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">类型</label>
              <select value={form.task_type} onChange={e => setForm(f => ({ ...f, task_type: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white">
                <option value="scheduled">定时执行</option>
                <option value="periodic">周期执行</option>
                <option value="on_demand">手动触发</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Cron 表达式</label>
              <input value={form.cron || ''} onChange={e => setForm(f => ({ ...f, cron: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="0 * * * * (每整点)" />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Agent ID</label>
              <input value={form.agent_id || ''} onChange={e => setForm(f => ({ ...f, agent_id: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="可选" />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm">{editing ? '保存' : '创建'}</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-gray-400">加载中...</p> : items.length === 0 ? <p className="text-gray-500">暂无定时任务</p> : (
        <div className="space-y-3">
          {items.map(t => (
            <div key={t.id} className="bg-gray-800 rounded-xl p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white">{t.name}</span>
                  <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">{t.task_type}</span>
                  {t.is_active ? <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded">启用</span> : <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">停用</span>}
                </div>
                {t.cron && <p className="text-xs text-gray-400 mt-1 font-mono">{t.cron}</p>}
                {t.next_run && <p className="text-xs text-gray-500 mt-0.5">下次执行: {t.next_run}</p>}
              </div>
              <div className="flex gap-2">
                <button onClick={() => { setEditing(t.id!); setForm({ ...t }); setShowForm(true) }} className="p-2 text-gray-400 hover:text-white"><Edit2 size={14} /></button>
                <button onClick={() => del(t.id!)} className="p-2 text-gray-400 hover:text-red-400"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
