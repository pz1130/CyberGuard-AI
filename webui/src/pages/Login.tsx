import { useState } from 'react'
import { Shield, Loader2 } from 'lucide-react'
import { api } from '../api/client'

export default function Login() {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await api.login({ username, password }) as { access_token: string }
      localStorage.setItem('token', data.access_token)
      window.location.hash = ''
      window.location.reload()
    } catch {
      setError('用户名或密码错误')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center bg-slate-950 overflow-hidden">
      {/* Ambient gradient blobs */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 -left-40 h-96 w-96 rounded-full bg-violet-500/20 blur-3xl" />
        <div className="absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-cyan-500/15 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">
        {/* Brand */}
        <div className="flex items-center gap-3 mb-8 justify-center">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 via-indigo-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-violet-500/30">
            <Shield size={20} className="text-white" />
          </div>
          <div className="leading-tight">
            <div className="text-lg font-semibold text-slate-100 tracking-tight">CyberGuard</div>
            <div className="text-[11px] text-slate-500">AI Agent Platform</div>
          </div>
        </div>

        {/* Card */}
        <div className="bg-slate-900/60 backdrop-blur-xl ring-1 ring-slate-800/80 rounded-2xl p-7 shadow-2xl shadow-black/40">
          <h1 className="text-base font-semibold text-slate-100 mb-1">欢迎回来</h1>
          <p className="text-xs text-slate-500 mb-6">使用账号密码登录管理控制台</p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5 block">用户名</label>
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full bg-slate-950/80 ring-1 ring-slate-800 focus:ring-violet-500/60 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition-shadow"
                placeholder="admin"
                autoComplete="username"
                required
              />
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5 block">密码</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-slate-950/80 ring-1 ring-slate-800 focus:ring-violet-500/60 rounded-lg px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition-shadow"
                placeholder="••••••••"
                autoComplete="current-password"
                required
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 text-xs text-rose-400 bg-rose-500/10 ring-1 ring-rose-500/20 rounded-lg px-3 py-2">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 disabled:opacity-60 text-white rounded-lg py-2.5 text-sm font-medium shadow-lg shadow-violet-500/20 transition-all flex items-center justify-center gap-2"
            >
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? '登录中…' : '登录'}
            </button>
          </form>

          <div className="mt-5 pt-4 border-t border-slate-800/80 text-center">
            <p className="text-[11px] text-slate-500">默认账号: <span className="text-slate-400 font-mono">admin / admin123</span></p>
          </div>
        </div>
      </div>
    </div>
  )
}
