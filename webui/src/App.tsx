/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
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
import Settings from './pages/Settings'
import N8N from './pages/N8N'
import Login from './pages/Login'

const PAGES: Record<Tab, { labelKey: string; component: React.ReactNode }> = {
  chat: { labelKey: 'nav.chat', component: <Chat /> },
  agents: { labelKey: 'nav.agents', component: <Agents /> },
  providers: { labelKey: 'nav.providers', component: <Providers /> },
  skills: { labelKey: 'nav.skills', component: <Skills /> },
  knowledge: { labelKey: 'nav.knowledge', component: <Knowledge /> },
  groupchat: { labelKey: 'nav.groupchat', component: <GroupChat /> },
  schedule: { labelKey: 'nav.schedule', component: <Schedule /> },
  mcp: { labelKey: 'nav.mcp', component: <MCP /> },
  envvars: { labelKey: 'nav.envvars', component: <EnvVars /> },
  security: { labelKey: 'nav.security', component: <Security /> },
  token: { labelKey: 'nav.token', component: <TokenUsage /> },
  backup: { labelKey: 'nav.backup', component: <Backup /> },
  audit: { labelKey: 'nav.audit', component: <AuditLogs /> },
  users: { labelKey: 'nav.users', component: <Users /> },
  settings: { labelKey: 'nav.settings', component: <Settings /> },
  n8n: { labelKey: 'nav.n8n', component: <N8N /> },
}

export default function App() {
  const { i18n } = useTranslation()
  const [tab, setTab] = useState<Tab>('chat')
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(true)
  const [dark, setDark] = useState(true)
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme')
    if (savedTheme === 'light') {
      setDark(false)
      document.documentElement.setAttribute('data-theme', 'light')
    }
    const token = localStorage.getItem('token')
    if (!token) { setChecking(false); return }
    fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { if (r.ok) setAuthed(true); else localStorage.removeItem('token') })
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setChecking(false))
  }, [])

  const toggleLang = () => {
    const next = i18n.language === 'zh' ? 'en' : 'zh'
    i18n.changeLanguage(next)
    localStorage.setItem('lang', next)
  }

  const toggleDark = () => {
    const next = !dark
    setDark(next)
    document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light')
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }

  if (checking) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: 'var(--bg-base)',
      }}>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
          fontFamily: 'var(--font-mono)',
        }}>
          <div style={{
            width: 40, height: 40,
            border: '1px solid var(--accent-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20, color: 'var(--accent)',
            animation: 'accent-pulse 2s ease-in-out infinite',
          }}>
            ⬡
          </div>
          <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>
            INITIALIZING CYBERGUARD OS...
          </div>
          <div style={{
            width: 200, height: 2, background: 'var(--border-bright)', position: 'relative', overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute', left: 0, top: 0, bottom: 0,
              width: '40%',
              background: 'var(--accent)',
              animation: 'shimmer 1.5s ease-in-out infinite',
            }} />
          </div>
        </div>
        <style>{`@keyframes shimmer { 0% { left: -40%; } 100% { left: 100%; } }`}</style>
      </div>
    )
  }

  if (!authed) return <Login />

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100vh', overflow: 'hidden',
      fontFamily: 'var(--font-mono)',
      background: 'var(--bg-base)', color: 'var(--text-primary)',
    }}>
      <Header dark={dark} toggleDark={toggleDark} toggleLang={toggleLang} />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', paddingTop: 'var(--header-height)' }}>
        <Sidebar tab={tab} setTab={setTab} />
        <main style={{
          flex: 1, overflowY: 'auto', overflowX: 'hidden',
          marginLeft: 'var(--sidebar-width)',
          padding: '24px 28px',
          animation: 'fade-in 0.2s ease',
        }}>
          {PAGES[tab].component}
        </main>
      </div>
    </div>
  )
}
