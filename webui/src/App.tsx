import { useState, useEffect } from 'react'
import Sidebar, { type Tab } from './components/Sidebar'
import Header from './components/Header'
import Chat from './pages/Chat'
import Providers from './pages/Providers'
import Agents from './pages/Agents'
import Skills from './pages/Skills'
import Knowledge from './pages/Knowledge'
import GroupChat from './pages/GroupChat'
import Schedule from './pages/Schedule'
import MCP from './pages/MCP'
import EnvVars from './pages/EnvVars'
import Security from './pages/Security'
import TokenUsage from './pages/TokenUsage'
import Backup from './pages/Backup'
import AuditLogs from './pages/AuditLogs'
import Users from './pages/Users'
import Login from './pages/Login'

const PAGES: Record<Tab, { component: React.ReactNode }> = {
  chat: { component: <Chat /> },
  agents: { component: <Agents /> },
  providers: { component: <Providers /> },
  skills: { component: <Skills /> },
  knowledge: { component: <Knowledge /> },
  groupchat: { component: <GroupChat /> },
  schedule: { component: <Schedule /> },
  mcp: { component: <MCP /> },
  envvars: { component: <EnvVars /> },
  security: { component: <Security /> },
  token: { component: <TokenUsage /> },
  backup: { component: <Backup /> },
  audit: { component: <AuditLogs /> },
  users: { component: <Users /> },
}

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')
  const [dark, setDark] = useState(true)
  const [lang, setLang] = useState<'zh' | 'en'>('zh')
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setChecking(false)
      return
    }
    fetch('/api/v1/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    }).then(r => {
      if (r.ok) {
        setAuthed(true)
      } else {
        localStorage.removeItem('token')
      }
    }).catch(() => {
      localStorage.removeItem('token')
    }).finally(() => {
      setChecking(false)
    })
  }, [])

  document.documentElement.classList.toggle('dark', dark)

  if (checking) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-950 text-white">
        <p className="text-gray-400">检查登录状态...</p>
      </div>
    )
  }

  if (!authed) {
    return <Login />
  }

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      <Sidebar tab={tab} setTab={setTab} />
      <div className="flex flex-col flex-1 min-w-0">
        <Header dark={dark} toggleDark={() => setDark(d => !d)} lang={lang} toggleLang={() => setLang(l => l === 'zh' ? 'en' : 'zh')} />
        <main className="flex-1 overflow-y-auto p-6">
          {PAGES[tab].component}
        </main>
      </div>
    </div>
  )
}
