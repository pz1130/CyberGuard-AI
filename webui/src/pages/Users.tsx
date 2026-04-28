import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, Shield } from 'lucide-react'

interface User {
  id?: number
  username: string
  email?: string
  role: string
  is_active?: boolean
  created_at?: string
}

const ROLES = ['admin', 'operator', 'viewer']

export default function Users() {
  const [items, setItems] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState<User>({ username: '', email: '', role: 'viewer' })
  const [password, setPassword] = useState('')

  const load = async () => {
    try {
      const data = await api.getUsers() as User[] | { users?: User[] }
      setItems(Array.isArray(data) ? data : data?.users || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.username || (!password && !editing)) return
    try {
      const payload = { ...form }
      if (password) Object.assign(payload, { password })
      if (editing) {
        await api.updateUser(editing, payload)
      } else {
        await api.createUser(payload)
      }
      setShowForm(false); setEditing(null)
      setForm({ username: '', email: '', role: 'viewer' }); setPassword(''); load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: number) => {
    if (!confirm('确认删除此用户？')) return
    await api.deleteUser(id); load()
  }

  const roleColor = (role: string) => {
    if (role === 'admin') return 'bg-red-500/20 text-red-400'
    if (role === 'operator') return 'bg-blue-500/20 text-blue-400'
    return 'bg-slate-500/20 text-slate-400'
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2"><Shield size={20} /> 用户管理</h2>
          <p className="text-xs text-slate-500 mt-1">RBAC 角色：Admin / Operator / Viewer</p>
        </div>
        <button onClick={() => { setShowForm(true); setEditing(null); setForm({ username: '', email: '', role: 'viewer' }); setPassword('') }}
          className="flex items-center gap-2 px-4 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-lg text-sm">
          <Plus size={16} /> 新增用户
        </button>
      </div>

      {showForm && (
        <div className="bg-slate-900 rounded-xl p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">用户名</label>
              <input value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">邮箱</label>
              <input type="email" value={form.email || ''} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">角色</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white">
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">{editing ? '新密码（留空不修改）' : '密码'}</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                className="w-full bg-slate-800 rounded-lg px-3 py-2 text-sm text-white" placeholder={editing ? '留空不修改' : ''} />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowForm(false); setEditing(null) }} className="px-4 py-2 bg-slate-800 text-white rounded-lg text-sm">取消</button>
            <button onClick={submit} className="px-4 py-2 bg-violet-500 text-white rounded-lg text-sm">{editing ? '保存' : '创建'}</button>
          </div>
        </div>
      )}

      {loading ? <p className="text-slate-400">加载中...</p> : items.length === 0 ? <p className="text-slate-500">暂无用户</p> : (
        <div className="bg-slate-900 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">用户</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">邮箱</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">角色</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">状态</th>
                <th className="text-right px-4 py-3 text-slate-400 font-medium text-xs">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map(u => (
                <tr key={u.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="px-4 py-3 text-white font-medium">{u.username}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{u.email || '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${roleColor(u.role)}`}>{u.role}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${u.is_active !== false ? 'bg-violet-500/20 text-violet-400' : 'bg-slate-800 text-slate-400'}`}>
                      {u.is_active !== false ? '激活' : '停用'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => { setEditing(u.id!); setForm({ ...u }); setShowForm(true); setPassword('') }}
                      className="p-1.5 text-slate-400 hover:text-white"><Edit2 size={14} /></button>
                    <button onClick={() => del(u.id!)} className="p-1.5 text-slate-400 hover:text-red-400 ml-1"><Trash2 size={14} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
