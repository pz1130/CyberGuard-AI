import { useState } from 'react'
import { Trash2, Eye, EyeOff } from 'lucide-react'

const INIT_VARS = [
  { key: 'OPENAI_API_KEY', value: '', type: 'secret' },
  { key: 'ANTHROPIC_API_KEY', value: '', type: 'secret' },
  { key: 'DATABASE_URL', value: 'postgresql+asyncpg://postgres:postgres@localhost:5432/cyberguard', type: 'text' },
  { key: 'REDIS_URL', value: 'redis://localhost:6379/0', type: 'text' },
  { key: 'ENCRYPTION_KEY', value: '', type: 'secret' },
  { key: 'JWT_EXPIRATION_MINUTES', value: '30', type: 'text' },
]

export default function EnvVars() {
  const [vars, setVars] = useState(INIT_VARS)
  const [showKey, setShowKey] = useState<Record<string, boolean>>({})
  const [newKey, setNewKey] = useState('')
  const [newVal, setNewVal] = useState('')
  const [newType, setNewType] = useState<'text' | 'secret'>('text')

  const add = () => {
    if (!newKey.trim()) return
    setVars(v => [...v, { key: newKey.trim(), value: newVal, type: newType }])
    setNewKey(''); setNewVal('')
  }

  const del = (key: string) => setVars(v => v.filter(x => x.key !== key))

  const update = (key: string, value: string) =>
    setVars(v => v.map(x => x.key === key ? { ...x, value } : x))

  const toggleShow = (key: string) => setShowKey(s => ({ ...s, [key]: !s[key] }))

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold">环境变量</h2>
          <p className="text-xs text-gray-500 mt-1">配置系统级密钥和连接信息，安全存储于后端</p>
        </div>
      </div>

      {/* Add new */}
      <div className="bg-gray-800 rounded-xl p-4 mb-6 flex gap-3 items-end flex-wrap">
        <div className="flex-1 min-w-32">
          <label className="text-xs text-gray-400 mb-1 block">变量名</label>
          <input value={newKey} onChange={e => setNewKey(e.target.value.toUpperCase())}
            className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono" placeholder="VARIABLE_NAME" />
        </div>
        <div className="flex-1 min-w-48">
          <label className="text-xs text-gray-400 mb-1 block">值</label>
          <input value={newVal} onChange={e => setNewVal(e.target.value)}
            className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="值" />
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">类型</label>
          <select value={newType} onChange={e => setNewType(e.target.value as 'text' | 'secret')}
            className="bg-gray-700 rounded-lg px-3 py-2 text-sm text-white">
            <option value="text">文本</option>
            <option value="secret">密钥</option>
          </select>
        </div>
        <button onClick={add} className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-sm">添加</button>
      </div>

      {/* List */}
      <div className="space-y-2">
        {vars.map(v => (
          <div key={v.key} className="bg-gray-800 rounded-xl p-4 flex items-center gap-4">
            <div className="w-48 flex-shrink-0">
              <span className="text-sm font-mono text-emerald-400">{v.key}</span>
              <span className="ml-2 text-xs bg-gray-700 text-gray-400 px-1.5 py-0.5 rounded">{v.type === 'secret' ? '密钥' : '文本'}</span>
            </div>
            <div className="flex-1 flex items-center gap-2">
              <input type={v.type === 'secret' && !showKey[v.key] ? 'password' : 'text'}
                value={v.value} onChange={e => update(v.key, e.target.value)}
                className="flex-1 bg-gray-700 rounded-lg px-3 py-1.5 text-sm text-white font-mono" />
              {v.type === 'secret' && (
                <button onClick={() => toggleShow(v.key)} className="p-1.5 text-gray-400 hover:text-white">
                  {showKey[v.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              )}
            </div>
            <button onClick={() => del(v.key)} className="p-1.5 text-gray-400 hover:text-red-400 flex-shrink-0"><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
    </div>
  )
}
