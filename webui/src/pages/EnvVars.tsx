import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Eye, EyeOff, RefreshCw, Lock } from 'lucide-react'

interface EnvVar {
  id?: number
  key: string
  value_type: 'text' | 'secret'
  description?: string
  is_active?: boolean
}

export default function EnvVars() {
  const [vars, setVars] = useState<EnvVar[]>([])
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')
  const [newType, setNewType] = useState<'text' | 'secret'>('text')
  const [newDesc, setNewDesc] = useState('')
  const [showNew, setShowNew] = useState(false)
  // Per-item: decrypted values cached locally (not stored in DB)
  const [decryptedValues, setDecryptedValues] = useState<Record<number, string>>({})
  const [visibleValues, setVisibleValues] = useState<Record<string, boolean>>({})
  const [decrypting, setDecrypting] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getEnvVars() as { vars: EnvVar[] }
      setVars(data?.vars || [])
    } catch { setVars([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const add = async () => {
    if (!newKey.trim()) return
    try {
      await api.createEnvVar({
        key: newKey.trim().toUpperCase(),
        value: newVal,
        value_type: newType,
        description: newDesc || undefined,
      })
      setNewKey(''); setNewVal(''); setNewType('text'); setNewDesc(''); setShowNew(false)
      load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: number) => {
    if (!confirm('确认删除？')) return
    try {
      await api.deleteEnvVar(id)
      setVars(v => v.filter(x => x.id !== id))
      setDecryptedValues(prev => { const n = { ...prev }; delete n[id]; return n })
    } catch (e: any) { alert(e.message) }
  }

  const toggleActive = async (v: EnvVar) => {
    if (!v.id) return
    try {
      await api.updateEnvVar(v.id, { is_active: !v.is_active })
      load()
    } catch (e: any) { alert(e.message) }
  }

  const decryptValue = async (id: number, key: string) => {
    if (decryptedValues[id]) {
      // Toggle visibility
      setVisibleValues(prev => ({ ...prev, [key]: !prev[key] }))
      return
    }
    setDecrypting(id)
    try {
      const res = await api.decryptEnvVar(id) as { value: string }
      setDecryptedValues(prev => ({ ...prev, [id]: res.value }))
      setVisibleValues(prev => ({ ...prev, [key]: true }))
    } catch (e: any) { alert(e.message) }
    finally { setDecrypting(null) }
  }

  const displayValue = (v: EnvVar) => {
    if (v.value_type !== 'secret') return '（文本类型，不可预览）'
    if (!decryptedValues[v.id!]) return '••••••••'
    if (!visibleValues[v.key]) return '••••••••'
    return decryptedValues[v.id!]
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold">环境变量</h2>
          <p className="text-xs text-slate-500 mt-1">
            系统级密钥和连接信息，AES-256 加密存储，仅 Admin 可解密
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-600 text-white rounded-lg text-sm">
            <RefreshCw size={14} /> 刷新
          </button>
          <button onClick={() => setShowNew(!showNew)}
            className="flex items-center gap-2 px-4 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-lg text-sm">
            + 添加变量
          </button>
        </div>
      </div>

      {/* Add New Form */}
      {showNew && (
        <div className="bg-slate-900 rounded-xl p-5 mb-6 space-y-3">
          <h3 className="text-sm font-medium text-white">新增环境变量</h3>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">变量名</label>
              <input value={newKey} onChange={e => setNewKey(e.target.value.toUpperCase())}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                placeholder="VARIABLE_NAME" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">值</label>
              <input value={newVal} onChange={e => setNewVal(e.target.value)}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white font-mono"
                placeholder="值（会加密存储）" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">类型</label>
              <select value={newType} onChange={e => setNewType(e.target.value as 'text' | 'secret')}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white">
                <option value="text">文本</option>
                <option value="secret">密钥</option>
              </select>
            </div>
            <div className="col-span-3">
              <label className="text-xs text-slate-400 mb-1 block">描述（可选）</label>
              <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white"
                placeholder="用途说明..." />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setShowNew(false)} className="px-4 py-2 bg-slate-800 text-white rounded-lg text-sm">取消</button>
            <button onClick={add} className="px-4 py-2 bg-violet-500 text-white rounded-lg text-sm">添加</button>
          </div>
        </div>
      )}

      {/* Security notice */}
      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl px-4 py-3 mb-6 flex items-start gap-3">
        <Lock size={16} className="text-yellow-400 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-yellow-300">
          环境变量值在传输和存储中使用 AES-256 加密。点击「查看」会实时解密，仅对具有设置写入权限的 Admin 开放。
        </p>
      </div>

      {/* List */}
      <div className="space-y-2">
        {loading ? (
          <p className="text-slate-400 py-8 text-center">加载中...</p>
        ) : vars.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-slate-500">暂无环境变量</p>
            <p className="text-xs text-slate-600 mt-1">点击右上角「添加变量」创建第一个</p>
          </div>
        ) : (
          vars.map(v => (
            <div key={v.id} className="bg-slate-900 rounded-xl p-4 flex items-center gap-4">
              {/* Key */}
              <div className="w-52 flex-shrink-0">
                <span className="text-sm font-mono text-violet-400">{v.key}</span>
                <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${v.value_type === 'secret' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-slate-800 text-slate-400'}`}>
                  {v.value_type === 'secret' ? <Lock size={10} className="inline" /> : null}
                  {v.value_type === 'secret' ? '密钥' : '文本'}
                </span>
              </div>

              {/* Value */}
              <div className="flex-1 flex items-center gap-2">
                {v.value_type === 'secret' ? (
                  <>
                    <span className="text-sm font-mono text-slate-300">
                      {displayValue(v)}
                    </span>
                    {v.is_active && (
                      <button
                        onClick={() => decryptValue(v.id!, v.key)}
                        disabled={decrypting === v.id}
                        className="p-1.5 text-slate-400 hover:text-white disabled:opacity-50"
                        title="解密查看"
                      >
                        {decrypting === v.id ? (
                          <RefreshCw size={14} className="animate-spin" />
                        ) : visibleValues[v.key] ? (
                          <EyeOff size={14} />
                        ) : (
                          <Eye size={14} />
                        )}
                      </button>
                    )}
                  </>
                ) : (
                  <span className="text-xs text-slate-500 italic">（文本类型不可预览）</span>
                )}
              </div>

              {/* Description */}
              <div className="flex-1 text-xs text-slate-500 truncate">{v.description || '—'}</div>

              {/* Active toggle */}
              <button
                onClick={() => toggleActive(v)}
                className={`text-xs px-2 py-1 rounded ${v.is_active ? 'bg-violet-500/20 text-violet-400' : 'bg-slate-800 text-slate-400'}`}
              >
                {v.is_active ? '启用' : '禁用'}
              </button>

              {/* Delete */}
              <button onClick={() => del(v.id!)} className="p-1.5 text-slate-400 hover:text-red-400 flex-shrink-0">
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
