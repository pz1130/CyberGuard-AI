import { useState } from 'react'
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

  document.documentElement.classList.toggle('dark', dark)

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
