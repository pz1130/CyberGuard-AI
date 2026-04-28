import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus } from 'lucide-react'

interface MCPServer {
  name: string
  type: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  is_active?: boolean
}

export default function MCP() {
  const [items, setItems] = useState<MCPServer[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<MCPServer>({ name: '', type: 'stdio' })
  const [envInput, setEnvInput] = useState('')

  const load = async () => {
    try {
      const data = await api.getMCPServers() as MCPServer[] | { servers?: MCPServer[] }
      setItems(Array.isArray(data) ? data : data?.servers || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      await api.createMCPServer(form)
      setShowForm(false); setForm({ name: '', type: 'stdio' }); setEnvInput(''); load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (name: string) => {
    if (!confirm(`删除 ${name}？`)) return
    await api.deleteMCPServer(name); load()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">MCP 服务器</h2>
        <button onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增服务器
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
              <label className="text-xs text-gray-400 mb-1 block">传输类型</label>
              <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white">
                <option value="stdio">STDIO</option>
                <option value="sse">SSE</option>
                <option value="streamable">Streamable HTTP</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs text-gray-400 mb-1 block">启动命令</label>
              <input value={form.command || ''} onChange={e => setForm(f => ({ ...f, command: e.target.value }))}
                className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="npx" />
            </div>
            <div className="col-span-2">
              <label className="text-xs text-gray-400 mb-1 block">环境变量 (KEY=VALUE, 每行一个)</label>
              <textarea value={envInput} onChange={e => setEnvInput(e.target.value)}
                rows={3} className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono" placeholder="API_KEY=xxx" />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm">创建</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-gray-400">加载中...</p> : items.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-500 mb-4">暂无 MCP 服务器</p>
          <p className="text-xs text-gray-600">MCP (Model Context Protocol) 服务器用于扩展 Agent 工具能力</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map(s => (
            <div key={s.name} className="bg-gray-800 rounded-xl p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white">{s.name}</span>
                  <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">{s.type}</span>
                </div>
                <button onClick={() => del(s.name)} className="p-1.5 text-gray-400 hover:text-red-400"><Trash2 size={14} /></button>
              </div>
              {s.command && <p className="text-xs text-gray-400 font-mono">{s.command}</p>}
              {s.is_active !== undefined && (
                <span className={`inline-block mt-2 text-xs px-2 py-0.5 rounded ${s.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-gray-700 text-gray-400'}`}>
                  {s.is_active ? '运行中' : '已停止'}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
