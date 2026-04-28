import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Database, Download, Trash2, Plus, RefreshCw } from 'lucide-react'

interface Backup {
  id?: string
  name: string
  size?: string
  created_at?: string
  type: string
}

export default function Backup() {
  const [items, setItems] = useState<Backup[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [restoring, setRestoring] = useState<string | null>(null)

  const load = async () => {
    try {
      const data = await api.listBackups() as Backup[] | { backups?: Backup[] }
      setItems(Array.isArray(data) ? data : data?.backups || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const create = async () => {
    setCreating(true)
    try {
      await api.createBackup({ name: `backup-${Date.now()}` })
      await load()
    } catch (e: any) { alert(e.message) } finally { setCreating(false) }
  }

  const restore = async (id: string) => {
    if (!confirm('确认恢复此备份？当前数据将被覆盖。')) return
    setRestoring(id)
    try {
      await api.restoreBackup(id)
      alert('恢复成功')
    } catch (e: any) { alert(e.message) } finally { setRestoring(null) }
  }

  const exportConfig = async () => {
    try {
      const data = await api.exportConfig() as any
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'cyberguard-config.json'; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) { alert(e.message) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2"><Database size={20} /> 备份</h2>
          <p className="text-xs text-slate-500 mt-1">本地备份与配置导出</p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportConfig}
            className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-600 text-white rounded-lg text-sm">
            <Download size={16} /> 导出配置
          </button>
          <button onClick={create} disabled={creating}
            className="flex items-center gap-2 px-4 py-2 bg-violet-500 hover:bg-violet-600 disabled:opacity-50 text-white rounded-lg text-sm">
            <Plus size={16} /> {creating ? '创建中...' : '创建备份'}
          </button>
        </div>
      </div>

      <div className="bg-slate-900 rounded-xl p-4 mb-6">
        <p className="text-sm text-slate-400">支持将数据库和配置导出为 JSON，可用于环境迁移或灾备恢复。</p>
      </div>

      {loading ? <p className="text-slate-400">加载中...</p> : items.length === 0 ? (
        <div className="text-center py-16 bg-slate-900 rounded-xl">
          <Database size={40} className="mx-auto text-slate-600 mb-3" />
          <p className="text-slate-500">暂无备份</p>
          <button onClick={create} className="mt-3 text-sm text-violet-400 hover:underline">立即创建第一个备份</button>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(b => (
            <div key={b.id} className="bg-slate-900 rounded-xl p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white">{b.name}</span>
                  <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">{b.type || 'full'}</span>
                </div>
                {b.size && <p className="text-xs text-slate-400 mt-1">{b.size}</p>}
                {b.created_at && <p className="text-xs text-slate-500 mt-0.5">{b.created_at}</p>}
              </div>
              <div className="flex gap-2">
                <button onClick={() => restore(b.id!)} disabled={restoring === b.id}
                  className="flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-600 text-white rounded-lg text-xs">
                  <RefreshCw size={12} className={restoring === b.id ? 'animate-spin' : ''} />
                  {restoring === b.id ? '恢复中...' : '恢复'}
                </button>
                <button className="p-2 text-slate-400 hover:text-red-400"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
