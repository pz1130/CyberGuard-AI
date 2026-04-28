import { Moon, Sun, Globe, LogOut, User } from 'lucide-react'
import { useState, useEffect } from 'react'

interface Props {
  dark: boolean
  toggleDark: () => void
  lang: 'zh' | 'en'
  toggleLang: () => void
}

export default function Header({ dark, toggleDark, lang, toggleLang }: Props) {
  const [username, setUsername] = useState<string>('—')
  const [role, setRole] = useState<string>('')

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) return
    fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then((d) => {
        if (d) { setUsername(d.username || '—'); setRole(d.role || '') }
      })
      .catch(() => {})
  }, [])

  const logout = () => {
    localStorage.removeItem('token')
    window.location.reload()
  }

  return (
    <header className="h-14 bg-slate-950/80 backdrop-blur supports-[backdrop-filter]:bg-slate-950/60 border-b border-slate-800/80 flex items-center justify-end px-5 flex-shrink-0">
      <div className="flex items-center gap-1.5">
        <button
          onClick={toggleLang}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 text-xs font-medium transition-colors"
          title="切换语言"
        >
          <Globe size={14} />
          {lang === 'zh' ? '中文' : 'EN'}
        </button>
        <button
          onClick={toggleDark}
          className="p-2 rounded-lg text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 transition-colors"
          title={dark ? '切换到浅色' : '切换到深色'}
        >
          {dark ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        <div className="h-5 w-px bg-slate-800 mx-2" />

        <div className="flex items-center gap-2 pl-1.5 pr-1">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-indigo-500 flex items-center justify-center">
            <User size={13} className="text-white" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-xs font-medium text-slate-200">{username}</span>
            {role && <span className="text-[10px] text-slate-500 capitalize">{role}</span>}
          </div>
        </div>

        <button
          onClick={logout}
          className="p-2 rounded-lg text-slate-400 hover:bg-rose-500/10 hover:text-rose-400 transition-colors"
          title="退出登录"
        >
          <LogOut size={15} />
        </button>
      </div>
    </header>
  )
}
