import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { FileText, Download, Search } from 'lucide-react'

interface Log {
  id?: number
  user_id?: number
  agent_id?: string
  action: string
  input_hash?: string
  output_hash?: string
  request_id?: string
  timestamp?: string
}

export default function AuditLogs() {
  const [logs, setLogs] = useState<Log[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [limit, setLimit] = useState(50)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getAuditLogs({ limit }) as Log[] | { logs?: Log[] }
      setLogs(Array.isArray(data) ? data : data?.logs || [])
    } catch { setLogs([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [limit])

  const exportLogs = async () => {
    try {
      const data = await api.exportAuditLogs() as any
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `audit-logs-${Date.now()}.json`; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) { alert(e.message) }
  }

  const filtered = logs.filter(l =>
    !filter || l.action?.toLowerCase().includes(filter.toLowerCase()) ||
    String(l.user_id)?.includes(filter)
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2"><FileText size={20} /> 审计日志</h2>
          <p className="text-xs text-gray-500 mt-1">所有操作行为记录，支持 SIEM 格式导出</p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportLogs}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">
            <Download size={16} /> 导出
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <div className="flex-1 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={filter} onChange={e => setFilter(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white" placeholder="搜索操作或用户 ID..." />
        </div>
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white">
          <option value={20}>20 条</option>
          <option value={50}>50 条</option>
          <option value={100}>100 条</option>
          <option value={500}>500 条</option>
        </select>
        <button onClick={load} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm">刷新</button>
      </div>

      {/* Table */}
      <div className="bg-gray-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left px-4 py-3 text-gray-400 font-medium text-xs">时间</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium text-xs">用户</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium text-xs">操作</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium text-xs">Request ID</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4} className="text-center py-8 text-gray-500">加载中...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={4} className="text-center py-8 text-gray-500">暂无日志</td></tr>
            ) : filtered.map((log, i) => (
              <tr key={i} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{log.timestamp ? new Date(log.timestamp).toLocaleString('zh-CN') : '—'}</td>
                <td className="px-4 py-3 text-gray-300 text-xs">{log.user_id ?? '—'}</td>
                <td className="px-4 py-3 text-white text-xs font-mono">{log.action}</td>
                <td className="px-4 py-3 text-gray-500 text-xs font-mono">{log.request_id ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
