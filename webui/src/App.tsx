/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import SidebarNew, { type Tab } from './components/SidebarNew'
import HeaderNew from './components/HeaderNew'
import GlobalSearch from './components/GlobalSearch'
import { SearchProvider } from './context/SearchContext'
import { api } from './api/client'
import Chat from './pages/Chat'
import Providers from './pages/Providers'
import Agents from './pages/Agents'
import Skills from './pages/Skills'
import Tools from './pages/Tools'
import Knowledge from './pages/Knowledge'
import GroupChat from './pages/GroupChat'
import Schedule from './pages/Schedule'
import MCP from './pages/MCP'
import EnvVars from './pages/EnvVars'
import Security from './pages/Security'
import TokenUsage from './pages/TokenUsage'
import Backup from './pages/Backup'
import AuditLogs from './pages/AuditLogs'
import Approvals from './pages/Approvals'
import Users from './pages/Users'
import Settings from './pages/Settings'
import N8N from './pages/N8N'
import Webhooks from './pages/Webhooks'
import Prompts from './pages/Prompts'
import Governance from './pages/Governance'
import Login from './pages/Login'

const PAGES: Record<Tab, { labelKey: string; component: React.ReactNode }> = {
  chat: { labelKey: 'nav.chat', component: <Chat /> },
  agents: { labelKey: 'nav.agents', component: <Agents /> },
  providers: { labelKey: 'nav.providers', component: <Providers /> },
  skills: { labelKey: 'nav.skills', component: <Skills /> },
  tools: { labelKey: 'nav.tools', component: <Tools /> },
  knowledge: { labelKey: 'nav.knowledge', component: <Knowledge /> },
  groupchat: { labelKey: 'nav.groupchat', component: <GroupChat /> },
  schedule: { labelKey: 'nav.schedule', component: <Schedule /> },
  mcp: { labelKey: 'nav.mcp', component: <MCP /> },
  envvars: { labelKey: 'nav.envvars', component: <EnvVars /> },
  security: { labelKey: 'nav.security', component: <Security /> },
  token: { labelKey: 'nav.token', component: <TokenUsage /> },
  backup: { labelKey: 'nav.backup', component: <Backup /> },
  audit: { labelKey: 'nav.audit', component: <AuditLogs /> },
  approvals: { labelKey: 'nav.approvals', component: <Approvals /> },
  users: { labelKey: 'nav.users', component: <Users /> },
  settings: { labelKey: 'nav.settings', component: <Settings /> },
  n8n: { labelKey: 'nav.n8n', component: <N8N /> },
  webhooks: { labelKey: 'nav.webhooks', component: <Webhooks /> },
  prompts: { labelKey: 'nav.prompts', component: <Prompts /> },
  governance: { labelKey: 'nav.governance', component: <Governance /> },
}

export default function App() {
  const { i18n } = useTranslation()
  const [tab, setTab] = useState<Tab>(() => {
    const saved = localStorage.getItem('lastTab') as Tab | null
    return saved && PAGES[saved] ? saved : 'chat'
  })
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(true)
  const [dark, setDark] = useState(true)
  const [searchOpen, setSearchOpen] = useState(false)
  const [recentTabs, setRecentTabs] = useState<Tab[]>(() => {
    try {
      const saved = localStorage.getItem('recentTabs')
      if (!saved) return []
      const parsed: Tab[] = JSON.parse(saved)
      return Array.isArray(parsed)
        ? parsed.filter((t: Tab) => PAGES[t]).slice(0, 3)
        : []
    } catch {
      return []
    }
  })

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme')
    if (savedTheme === 'light') {
      setDark(false)
      document.documentElement.setAttribute('data-theme', 'light')
    } else {
      document.documentElement.removeAttribute('data-theme')
    }
    // SSO callback delivers the JWT in the URL fragment (#sso_token=...).
    const ssoMatch = window.location.hash.match(/sso_token=([^&]+)/)
    if (ssoMatch) {
      localStorage.setItem('token', decodeURIComponent(ssoMatch[1]))
      // Strip the token from the URL so it isn't left in history.
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
    const token = localStorage.getItem('token')
    if (!token) { setChecking(false); return }
    api.getAuthMe()
      .then(() => setAuthed(true))
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setChecking(false))
  }, [])

  // Global CTRL+K listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleSetTab = (t: Tab) => {
    setTab(t)
    localStorage.setItem('lastTab', t)
    setRecentTabs(prev => {
      const next = [t, ...prev.filter(x => x !== t)].slice(0, 3)
      localStorage.setItem('recentTabs', JSON.stringify(next))
      return next
    })
  }

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
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: 'var(--bg-base)',
          color: 'var(--text-muted)',
          fontSize: 13,
          fontFamily: 'var(--font-sans)',
        }}
      >
        Loading...
      </div>
    )
  }

  if (!authed) return <Login />

  return (
    <SearchProvider>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          overflow: 'hidden',
          fontFamily: 'var(--font-sans)',
          background: 'var(--bg-base)',
          color: 'var(--text-primary)',
        }}
      >
        <HeaderNew
          dark={dark}
          toggleDark={toggleDark}
          toggleLang={toggleLang}
          onSearchOpen={() => setSearchOpen(true)}
        />
        <div
          style={{
            display: 'flex',
            flex: 1,
            overflow: 'hidden',
            paddingTop: 'var(--header-height)',
          }}
        >
          <SidebarNew tab={tab} setTab={handleSetTab} />
          <main
            style={{
              flex: 1,
              overflowY: 'auto',
              overflowX: 'hidden',
              marginLeft: 'var(--sidebar-width)',
              padding: '24px 28px 40px',
            }}
          >
            {PAGES[tab].component}
          </main>
        </div>
        <GlobalSearch
          open={searchOpen}
          onClose={() => setSearchOpen(false)}
          setTab={handleSetTab}
          recentTabs={recentTabs}
        />
      </div>
    </SearchProvider>
  )
}
