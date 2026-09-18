import { lazy, Suspense, useState, useEffect } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'
import { useTranslation } from 'react-i18next'
import SidebarNew, { type Tab } from './components/SidebarNew'
import HeaderNew from './components/HeaderNew'
import GlobalSearch from './components/GlobalSearch'
import { SearchProvider } from './context/SearchContext'
import { api } from './api/client'
import { RoleContext, canAccessTab } from './context/permissions'
import Login from './pages/Login'
import { applyTheme, readStoredDark } from './theme'
import { useIdleLogout } from './hooks/useIdleLogout'

const PAGES: Record<Tab, { labelKey: string; component: LazyExoticComponent<ComponentType> }> = {
  chat: { labelKey: 'nav.chat', component: lazy(() => import('./pages/Chat')) },
  agents: { labelKey: 'nav.agents', component: lazy(() => import('./pages/Agents')) },
  providers: { labelKey: 'nav.providers', component: lazy(() => import('./pages/Providers')) },
  skills: { labelKey: 'nav.skills', component: lazy(() => import('./pages/Skills')) },
  tools: { labelKey: 'nav.tools', component: lazy(() => import('./pages/Tools')) },
  knowledge: { labelKey: 'nav.knowledge', component: lazy(() => import('./pages/Knowledge')) },
  mcp: { labelKey: 'nav.mcp', component: lazy(() => import('./pages/MCP')) },
  envvars: { labelKey: 'nav.envvars', component: lazy(() => import('./pages/EnvVars')) },
  security: { labelKey: 'nav.security', component: lazy(() => import('./pages/Security')) },
  token: { labelKey: 'nav.token', component: lazy(() => import('./pages/TokenUsage')) },
  backup: { labelKey: 'nav.backup', component: lazy(() => import('./pages/Backup')) },
  audit: { labelKey: 'nav.audit', component: lazy(() => import('./pages/AuditLogs')) },
  approvals: { labelKey: 'nav.approvals', component: lazy(() => import('./pages/Approvals')) },
  users: { labelKey: 'nav.users', component: lazy(() => import('./pages/Users')) },
  settings: { labelKey: 'nav.settings', component: lazy(() => import('./pages/Settings')) },
  prompts: { labelKey: 'nav.prompts', component: lazy(() => import('./pages/Prompts')) },
  govDashboard: { labelKey: 'nav.govDashboard', component: lazy(() => import('./pages/GovernanceDashboard')) },
}

export default function App() {
  const { i18n } = useTranslation()
  const [tab, setTab] = useState<Tab>(() => {
    const saved = localStorage.getItem('lastTab') as Tab | null
    return saved && PAGES[saved] ? saved : 'chat'
  })
  const [role, setRole] = useState('')
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(() => {
    try {
      return !!localStorage.getItem('token') || /sso_token=/.test(window.location.hash)
    } catch {
      return false
    }
  })
  const [dark, setDark] = useState(readStoredDark)
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
  const allowedTab = canAccessTab(role, tab) ? tab : ((Object.keys(PAGES) as Tab[]).find(t => canAccessTab(role, t)) || 'chat')
  const ActivePage = PAGES[allowedTab].component

  useEffect(() => {
    // SSO callback delivers the JWT in the URL fragment (#sso_token=...).
    const ssoMatch = window.location.hash.match(/sso_token=([^&]+)/)
    if (ssoMatch) {
      localStorage.setItem('token', decodeURIComponent(ssoMatch[1]))
      // Strip the token from the URL so it isn't left in history.
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
    const token = localStorage.getItem('token')
    if (!token) return
    let cancelled = false
    api.getAuthMe()
      .then(user => { if (!cancelled) { setRole((user as { role: string }).role); setAuthed(true) } })
      .catch(() => { localStorage.removeItem('token') })
      .finally(() => { if (!cancelled) setChecking(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const expired = () => { setAuthed(false); setChecking(false) }
    window.addEventListener('cyberguard:session-expired', expired)
    return () => window.removeEventListener('cyberguard:session-expired', expired)
  }, [])

  // Tell the server when a human does something, so an idle session can end.
  useIdleLogout()

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
    if (!canAccessTab(role, t)) return
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
    applyTheme(next)
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
    <RoleContext.Provider value={role}>
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
          <SidebarNew tab={allowedTab} setTab={handleSetTab} />
          <main
            style={{
              flex: 1,
              overflowY: 'auto',
              overflowX: 'hidden',
              marginLeft: 'var(--sidebar-width)',
              padding: '24px 28px 40px',
            }}
          >
            <Suspense fallback={<div style={{ color: 'var(--text-muted)' }}>Loading...</div>}>
              {canAccessTab(role, allowedTab) ? <ActivePage /> : <div role="alert">Permission denied</div>}
            </Suspense>
          </main>
        </div>
        <GlobalSearch
          open={searchOpen}
          onClose={() => setSearchOpen(false)}
          setTab={handleSetTab}
          recentTabs={recentTabs.filter(t => canAccessTab(role, t))}
        />
      </div>
    </SearchProvider>
    </RoleContext.Provider>
  )
}
