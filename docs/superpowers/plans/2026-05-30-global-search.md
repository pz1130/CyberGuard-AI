# Global Search (CTRL+K) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a functional CTRL+K command-palette modal that searches across Agents, Providers, Skills, Tools, Knowledge Bases, and MCP Servers, then navigates to the target page and highlights the selected item.

**Architecture:** A new `SearchContext` carries the selected search target through the component tree. A `GlobalSearch` modal fetches all 6 data sources on first open, filters client-side, and on selection calls `setTab` + `setSearchTarget`. Each target page reads `searchTarget` from context, scrolls to the matching row (identified by `data-item-id`), and flashes a CSS highlight class.

**Tech Stack:** React 18 (Context, useEffect, useCallback, useRef), TypeScript, existing `api` client, CSS custom properties (matching app theme), Vite/tsc build.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `webui/src/context/SearchContext.tsx` | Context + provider for `searchTarget` state |
| Create | `webui/src/components/GlobalSearch.tsx` | Modal: search input, results list, keyboard nav |
| Modify | `webui/src/App.tsx` | Wrap with provider, CTRL+K listener, render modal, track recents |
| Modify | `webui/src/components/Header.tsx` | Clicking search input opens modal |
| Modify | `webui/src/index.css` | `search-highlight` flash animation |
| Modify | `webui/src/pages/Agents.tsx` | `data-item-id` on card + highlight `useEffect` |
| Modify | `webui/src/pages/Providers.tsx` | `data-item-id` on `ProviderCard` root + highlight `useEffect` |
| Modify | `webui/src/pages/Skills.tsx` | `data-item-id` on card + highlight `useEffect` |
| Modify | `webui/src/pages/Tools.tsx` | `data-item-id` on card + highlight `useEffect` |
| Modify | `webui/src/pages/Knowledge.tsx` | `data-item-id` on list row + highlight `useEffect` |
| Modify | `webui/src/pages/MCP.tsx` | `data-item-id` on server card + highlight `useEffect` |

---

## Task 1: SearchContext

**Files:**
- Create: `webui/src/context/SearchContext.tsx`

- [ ] **Step 1: Create the context file**

```tsx
// webui/src/context/SearchContext.tsx
import { createContext, useContext, useState } from 'react'
import type { Tab } from '../components/Sidebar'

export interface SearchTarget {
  tab: Tab
  id: number | string
  name: string
}

interface SearchContextValue {
  searchTarget: SearchTarget | null
  setSearchTarget: (t: SearchTarget | null) => void
}

export const SearchContext = createContext<SearchContextValue>({
  searchTarget: null,
  setSearchTarget: () => {},
})

export function SearchProvider({ children }: { children: React.ReactNode }) {
  const [searchTarget, setSearchTarget] = useState<SearchTarget | null>(null)
  return (
    <SearchContext.Provider value={{ searchTarget, setSearchTarget }}>
      {children}
    </SearchContext.Provider>
  )
}

export const useSearch = () => useContext(SearchContext)
```

- [ ] **Step 2: Type-check**

```bash
cd webui && npx tsc --noEmit
```

Expected: no errors related to this file.

- [ ] **Step 3: Commit**

```bash
git add webui/src/context/SearchContext.tsx
git commit -m "feat(search): add SearchContext for cross-page highlight state"
```

---

## Task 2: CSS highlight animation

**Files:**
- Modify: `webui/src/index.css`

- [ ] **Step 1: Add animation to index.css**

Append to the end of `webui/src/index.css`:

```css
/* Global search result highlight */
@keyframes search-highlight-flash {
  0%   { outline: 2px solid var(--accent); outline-offset: 2px; background: var(--accent-dim); }
  70%  { outline: 2px solid var(--accent); outline-offset: 2px; background: var(--accent-dim); }
  100% { outline: 2px solid transparent; outline-offset: 2px; background: transparent; }
}

.search-highlight {
  animation: search-highlight-flash 2s ease forwards;
}
```

- [ ] **Step 2: Commit**

```bash
git add webui/src/index.css
git commit -m "feat(search): add search-highlight CSS animation"
```

---

## Task 3: GlobalSearch component

**Files:**
- Create: `webui/src/components/GlobalSearch.tsx`

- [ ] **Step 1: Create the component**

```tsx
// webui/src/components/GlobalSearch.tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api/client'
import { useSearch } from '../context/SearchContext'
import type { Tab } from './Sidebar'

interface SearchItem {
  id: number | string
  name: string
  subtitle: string
  tab: Tab
  category: string
  icon: string
}

interface Props {
  open: boolean
  onClose: () => void
  setTab: (t: Tab) => void
  recentTabs: Tab[]
}

const TAB_LABELS: Record<string, string> = {
  chat: 'CHAT', agents: 'AGENTS', providers: 'PROVIDERS',
  skills: 'SKILLS', tools: 'TOOLS', knowledge: 'KNOWLEDGE',
  groupchat: 'GROUP CHAT', schedule: 'SCHEDULE', mcp: 'MCP',
  envvars: 'ENV VARS', security: 'SECURITY', token: 'TOKEN USAGE',
  backup: 'BACKUP', audit: 'AUDIT LOGS', users: 'USERS',
  settings: 'SETTINGS', n8n: 'N8N', webhooks: 'WEBHOOKS',
  prompts: 'PROMPTS', governance: 'GOVERNANCE',
}

export default function GlobalSearch({ open, onClose, setTab, recentTabs }: Props) {
  const [query, setQuery] = useState('')
  const [allItems, setAllItems] = useState<SearchItem[]>([])
  const [loadingData, setLoadingData] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const { setSearchTarget } = useSearch()
  const inputRef = useRef<HTMLInputElement>(null)
  const loadedRef = useRef(false)

  // Load all searchable data once on first open
  useEffect(() => {
    if (!open || loadedRef.current) return
    loadedRef.current = true
    setLoadingData(true)
    Promise.allSettled([
      api.getAgents(),
      api.getProviders(),
      api.getSkills(),
      api.getTools(),
      api.getKnowledgeBases(),
      api.getMCPServers(),
    ]).then(([agents, providers, skills, tools, knowledge, mcp]) => {
      const items: SearchItem[] = []

      if (agents.status === 'fulfilled') {
        const d = agents.value as any
        const list = Array.isArray(d) ? d : (d?.agents || [])
        list.forEach((a: any) => items.push({
          id: a.id, name: a.agent_name || a.name || String(a.id),
          subtitle: (a.backend_type || 'AGENT').toUpperCase(),
          tab: 'agents', category: 'AGENTS', icon: '◆',
        }))
      }

      if (providers.status === 'fulfilled') {
        const d = providers.value as any
        const list = Array.isArray(d) ? d : (d?.providers || [])
        list.forEach((p: any) => items.push({
          id: p.id, name: p.name,
          subtitle: (p.provider_type || 'PROVIDER').toUpperCase(),
          tab: 'providers', category: 'PROVIDERS', icon: '▣',
        }))
      }

      if (skills.status === 'fulfilled') {
        const d = skills.value as any
        const list = Array.isArray(d) ? d : (d?.skills || [])
        list.forEach((s: any) => items.push({
          id: s.id, name: s.name,
          subtitle: s.description ? String(s.description).slice(0, 40) : 'SKILL',
          tab: 'skills', category: 'SKILLS', icon: '◈',
        }))
      }

      if (tools.status === 'fulfilled') {
        const d = tools.value as any
        const list = Array.isArray(d) ? d : (d?.tools || [])
        list.forEach((t: any) => items.push({
          id: t.id, name: t.name,
          subtitle: t.description ? String(t.description).slice(0, 40) : 'TOOL',
          tab: 'tools', category: 'TOOLS', icon: '◇',
        }))
      }

      if (knowledge.status === 'fulfilled') {
        const d = knowledge.value as any
        const list = d?.bases || []
        list.forEach((k: any) => items.push({
          id: k.id, name: k.name,
          subtitle: 'KNOWLEDGE BASE',
          tab: 'knowledge', category: 'KNOWLEDGE', icon: '◉',
        }))
      }

      if (mcp.status === 'fulfilled') {
        const d = mcp.value as any
        const list = d?.servers || (Array.isArray(d) ? d : [])
        list.forEach((m: any) => items.push({
          id: m.id, name: m.name,
          subtitle: m.url || 'MCP SERVER',
          tab: 'mcp', category: 'MCP', icon: '◎',
        }))
      }

      setAllItems(items)
      setLoadingData(false)
    })
  }, [open])

  // Focus input and reset state when opened
  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [open])

  // Filter and group by category
  const q = query.toLowerCase().trim()
  const filtered = q
    ? allItems.filter(item =>
        item.name.toLowerCase().includes(q) ||
        item.subtitle.toLowerCase().includes(q)
      )
    : []

  const grouped: Record<string, SearchItem[]> = {}
  filtered.forEach(item => {
    if (!grouped[item.category]) grouped[item.category] = []
    if (grouped[item.category].length < 5) grouped[item.category].push(item)
  })
  const categories = Object.keys(grouped)
  const flat = categories.flatMap(c => grouped[c])
  const itemIndexMap = new Map(flat.map((item, i) => [item, i]))

  const select = useCallback((item: SearchItem) => {
    onClose()
    setTab(item.tab)
    setSearchTarget({ tab: item.tab, id: item.id, name: item.name })
  }, [onClose, setTab, setSearchTarget])

  // Keyboard: ESC / ArrowUp / ArrowDown / Enter
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex(i => Math.min(i + 1, flat.length - 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex(i => Math.max(i - 1, 0))
      }
      if (e.key === 'Enter' && flat[selectedIndex]) {
        select(flat[selectedIndex])
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, flat, selectedIndex, onClose, select])

  useEffect(() => { setSelectedIndex(0) }, [query])

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.7)',
        }}
      />
      {/* Modal */}
      <div style={{
        position: 'fixed', zIndex: 1001,
        top: '15vh', left: '50%', transform: 'translateX(-50%)',
        width: 600, maxWidth: '90vw',
        background: 'var(--bg-elevated)',
        border: '1px solid var(--accent-border)',
        maxHeight: '70vh',
        display: 'flex', flexDirection: 'column',
        fontFamily: 'var(--font-mono)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      }}>
        {/* Input row */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '0 16px', height: 52,
          borderBottom: '1px solid var(--border-bright)',
          flexShrink: 0,
        }}>
          <span style={{ color: 'var(--accent)', fontSize: 18, flexShrink: 0 }}>⬡</span>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="SEARCH AGENTS / SKILLS / TOOLS / PROVIDERS..."
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              color: 'var(--text-primary)', fontSize: 14,
              letterSpacing: '0.05em', fontFamily: 'var(--font-mono)',
            }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em', flexShrink: 0 }}>ESC</span>
        </div>

        {/* Results area */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loadingData && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.1em' }}>
              LOADING...
            </div>
          )}

          {/* Recent tabs (shown when query is empty) */}
          {!loadingData && !q && recentTabs.length > 0 && (
            <div>
              <div style={{ padding: '8px 16px 4px', fontSize: 11, letterSpacing: '0.15em', color: 'var(--text-dim)' }}>
                RECENT
              </div>
              {recentTabs.map(t => (
                <button
                  key={t}
                  onClick={() => { onClose(); setTab(t) }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    width: '100%', padding: '0 16px', height: 40,
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', textAlign: 'left',
                    fontFamily: 'var(--font-mono)', fontSize: 13, letterSpacing: '0.08em',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                >
                  <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>→</span>
                  {TAB_LABELS[t] || t.toUpperCase()}
                </button>
              ))}
            </div>
          )}

          {!loadingData && !q && recentTabs.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.1em' }}>
              TYPE TO SEARCH ACROSS AGENTS, PROVIDERS, SKILLS, TOOLS, KNOWLEDGE, MCP
            </div>
          )}

          {!loadingData && q && categories.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.1em' }}>
              NO RESULTS — TRY ANOTHER QUERY
            </div>
          )}

          {/* Grouped results */}
          {!loadingData && categories.map(cat => (
            <div key={cat}>
              <div style={{ padding: '8px 16px 4px', fontSize: 11, letterSpacing: '0.15em', color: 'var(--text-dim)' }}>
                {cat}
              </div>
              {grouped[cat].map(item => {
                const currentIdx = itemIndexMap.get(item)!
                const isSelected = selectedIndex === currentIdx
                const nameQ = item.name.toLowerCase().indexOf(q)
                const nameDisplay: React.ReactNode = nameQ >= 0 ? (
                  <>
                    {item.name.slice(0, nameQ)}
                    <span style={{ color: 'var(--accent)', fontWeight: 700 }}>
                      {item.name.slice(nameQ, nameQ + q.length)}
                    </span>
                    {item.name.slice(nameQ + q.length)}
                  </>
                ) : item.name

                return (
                  <div
                    key={`${cat}-${item.id}`}
                    onClick={() => select(item)}
                    onMouseEnter={() => setSelectedIndex(currentIdx)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '0 16px', height: 40, cursor: 'pointer',
                      background: isSelected ? 'var(--accent-dim)' : 'transparent',
                      borderLeft: isSelected ? '2px solid var(--accent)' : '2px solid transparent',
                    }}
                  >
                    <span style={{ color: 'var(--accent)', fontSize: 11, flexShrink: 0 }}>{item.icon}</span>
                    <span style={{
                      fontSize: 13, color: 'var(--text-primary)', flex: 1,
                      minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {nameDisplay}
                    </span>
                    <span style={{
                      fontSize: 11, color: 'var(--text-dim)', flexShrink: 0,
                      maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {item.subtitle}
                    </span>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd webui && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add webui/src/components/GlobalSearch.tsx
git commit -m "feat(search): add GlobalSearch modal component"
```

---

## Task 4: Wire App.tsx

**Files:**
- Modify: `webui/src/App.tsx`

Changes: (a) wrap with `SearchProvider`, (b) add `searchOpen` state + CTRL+K listener, (c) track `recentTabs`, (d) render `<GlobalSearch>`.

- [ ] **Step 1: Update App.tsx**

Replace the entire `App.tsx` with:

```tsx
/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import Sidebar, { type Tab } from './components/Sidebar'
import Header from './components/Header'
import GlobalSearch from './components/GlobalSearch'
import { SearchProvider } from './context/SearchContext'
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
  users: { labelKey: 'nav.users', component: <Users /> },
  settings: { labelKey: 'nav.settings', component: <Settings /> },
  n8n: { labelKey: 'nav.n8n', component: <N8N /> },
  webhooks: { labelKey: 'nav.webhooks', component: <Webhooks /> },
  prompts: { labelKey: 'nav.prompts', component: <Prompts /> },
  governance: { labelKey: 'nav.governance', component: <Governance /> },
}

export default function App() {
  const { i18n } = useTranslation()
  const [tab, setTab] = useState<Tab>('chat')
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(true)
  const [dark, setDark] = useState(true)
  const [searchOpen, setSearchOpen] = useState(false)
  const [recentTabs, setRecentTabs] = useState<Tab[]>([])

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
    setRecentTabs(prev => [t, ...prev.filter(x => x !== t)].slice(0, 3))
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
            fontSize: 22, color: 'var(--accent)',
            animation: 'accent-pulse 2s ease-in-out infinite',
          }}>
            ⬡
          </div>
          <div style={{ fontSize: 13, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>
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
    <SearchProvider>
      <div style={{
        display: 'flex', flexDirection: 'column',
        height: '100vh', overflow: 'hidden',
        fontFamily: 'var(--font-mono)',
        background: 'var(--bg-base)', color: 'var(--text-primary)',
      }}>
        <Header
          dark={dark}
          toggleDark={toggleDark}
          toggleLang={toggleLang}
          onSearchOpen={() => setSearchOpen(true)}
        />
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden', paddingTop: 'var(--header-height)' }}>
          <Sidebar tab={tab} setTab={handleSetTab} />
          <main style={{
            flex: 1, overflowY: 'auto', overflowX: 'hidden',
            marginLeft: 'var(--sidebar-width)',
            padding: '24px 28px',
            animation: 'fade-in 0.2s ease',
          }}>
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
```

- [ ] **Step 2: Type-check**

```bash
cd webui && npx tsc --noEmit
```

Expected: one error about `onSearchOpen` prop not existing on `Header` yet — that's fine, fix in Task 5.

- [ ] **Step 3: Commit**

```bash
git add webui/src/App.tsx
git commit -m "feat(search): wire GlobalSearch into App — CTRL+K, context provider, recent tabs"
```

---

## Task 5: Update Header.tsx

**Files:**
- Modify: `webui/src/components/Header.tsx`

Add `onSearchOpen` prop; make the search input open the modal on click; mark it `readOnly`.

- [ ] **Step 1: Update Header props interface and input**

Change the `Props` interface (lines 4-8):

```tsx
interface Props {
  dark: boolean
  toggleDark: () => void
  toggleLang: () => void
  onSearchOpen: () => void
}
```

Change the function signature (line 10):

```tsx
export default function Header({ dark, toggleDark, toggleLang, onSearchOpen }: Props) {
```

Replace the search `<input>` (the block starting with `<input type="text" id="global-search" ...`) with:

```tsx
        <input
          type="text"
          id="global-search"
          readOnly
          placeholder="SEARCH AGENTS / SKILLS / TOOLS / PROVIDERS..."
          onClick={onSearchOpen}
          style={{
            width: '100%', height: 34,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-bright)',
            paddingLeft: 36, paddingRight: 12,
            fontSize: 14, letterSpacing: '0.05em',
            color: 'var(--text-primary)',
            cursor: 'pointer',
          }}
        />
```

- [ ] **Step 2: Type-check**

```bash
cd webui && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add webui/src/components/Header.tsx
git commit -m "feat(search): Header search bar opens GlobalSearch modal on click"
```

---

## Task 6: Highlight — Agents page

**Files:**
- Modify: `webui/src/pages/Agents.tsx`

- [ ] **Step 1: Add import and useSearch hook call**

At the top of the file, add the import after the existing imports:

```tsx
import { useContext, useEffect } from 'react'  // add useContext, useEffect if not already imported
import { SearchContext } from '../context/SearchContext'
```

Note: `useEffect` is likely already imported. Add only what's missing.

Inside the `Agents` component (the main exported function), add after the existing state declarations:

```tsx
const { searchTarget, setSearchTarget } = useContext(SearchContext)

useEffect(() => {
  if (!searchTarget || searchTarget.tab !== 'agents') return
  const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('search-highlight')
  const timer = setTimeout(() => {
    el.classList.remove('search-highlight')
    setSearchTarget(null)
  }, 2000)
  return () => clearTimeout(timer)
}, [searchTarget, setSearchTarget])
```

- [ ] **Step 2: Add data-item-id to agent card**

Find line ~555 (the card div in `items.filter(...).map(a => { return (`):

```tsx
// Before
<div key={a.id} style={{
  padding: 18, background: 'var(--bg-surface)',
  border: '1px solid var(--border-bright)',
  borderLeft: `3px solid ${bc}`,
}}>

// After
<div key={a.id} data-item-id={a.id} style={{
  padding: 18, background: 'var(--bg-surface)',
  border: '1px solid var(--border-bright)',
  borderLeft: `3px solid ${bc}`,
}}>
```

- [ ] **Step 3: Type-check**

```bash
cd webui && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add webui/src/pages/Agents.tsx
git commit -m "feat(search): Agents page — data-item-id + search highlight"
```

---

## Task 7: Highlight — Providers page

**Files:**
- Modify: `webui/src/pages/Providers.tsx`

- [ ] **Step 1: Add import and useSearch hook call**

Add import at top of file:

```tsx
import { useContext, useEffect } from 'react'  // add if not already present
import { SearchContext } from '../context/SearchContext'
```

Inside the main `Providers` component, after existing state declarations:

```tsx
const { searchTarget, setSearchTarget } = useContext(SearchContext)

useEffect(() => {
  if (!searchTarget || searchTarget.tab !== 'providers') return
  const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('search-highlight')
  const timer = setTimeout(() => {
    el.classList.remove('search-highlight')
    setSearchTarget(null)
  }, 2000)
  return () => clearTimeout(timer)
}, [searchTarget, setSearchTarget])
```

- [ ] **Step 2: Add data-item-id to ProviderCard root div**

Find the `ProviderCard` function (~line 423). Its `return` block starts with:

```tsx
// Before
  return (
    <div style={{
      padding: 18, background: 'var(--bg-surface)',

// After
  return (
    <div data-item-id={provider.id} style={{
      padding: 18, background: 'var(--bg-surface)',
```

- [ ] **Step 3: Type-check and commit**

```bash
cd webui && npx tsc --noEmit
git add webui/src/pages/Providers.tsx
git commit -m "feat(search): Providers page — data-item-id + search highlight"
```

---

## Task 8: Highlight — Skills page

**Files:**
- Modify: `webui/src/pages/Skills.tsx`

- [ ] **Step 1: Add import and hook**

```tsx
import { useContext, useEffect } from 'react'  // add if missing
import { SearchContext } from '../context/SearchContext'
```

Inside the `Skills` component:

```tsx
const { searchTarget, setSearchTarget } = useContext(SearchContext)

useEffect(() => {
  if (!searchTarget || searchTarget.tab !== 'skills') return
  const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('search-highlight')
  const timer = setTimeout(() => {
    el.classList.remove('search-highlight')
    setSearchTarget(null)
  }, 2000)
  return () => clearTimeout(timer)
}, [searchTarget, setSearchTarget])
```

- [ ] **Step 2: Add data-item-id to skill card**

Find line ~318 (card div in `items.map(s => ...`):

```tsx
// Before
<div key={s.id} style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', borderLeft: `3px solid ${tc}` }}>

// After
<div key={s.id} data-item-id={s.id} style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', borderLeft: `3px solid ${tc}` }}>
```

- [ ] **Step 3: Type-check and commit**

```bash
cd webui && npx tsc --noEmit
git add webui/src/pages/Skills.tsx
git commit -m "feat(search): Skills page — data-item-id + search highlight"
```

---

## Task 9: Highlight — Tools page

**Files:**
- Modify: `webui/src/pages/Tools.tsx`

- [ ] **Step 1: Add import and hook**

```tsx
import { useContext, useEffect } from 'react'  // add if missing
import { SearchContext } from '../context/SearchContext'
```

Inside the `Tools` component:

```tsx
const { searchTarget, setSearchTarget } = useContext(SearchContext)

useEffect(() => {
  if (!searchTarget || searchTarget.tab !== 'tools') return
  const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('search-highlight')
  const timer = setTimeout(() => {
    el.classList.remove('search-highlight')
    setSearchTarget(null)
  }, 2000)
  return () => clearTimeout(timer)
}, [searchTarget, setSearchTarget])
```

- [ ] **Step 2: Add data-item-id to tool card**

Find line ~305 (card div in `items.map(t => ...`):

```tsx
// Before
<div key={t.id} style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', borderLeft: `3px solid ${tc}` }}>

// After
<div key={t.id} data-item-id={t.id} style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', borderLeft: `3px solid ${tc}` }}>
```

- [ ] **Step 3: Type-check and commit**

```bash
cd webui && npx tsc --noEmit
git add webui/src/pages/Tools.tsx
git commit -m "feat(search): Tools page — data-item-id + search highlight"
```

---

## Task 10: Highlight — Knowledge page

**Files:**
- Modify: `webui/src/pages/Knowledge.tsx`

- [ ] **Step 1: Add import and hook**

```tsx
import { useContext, useEffect } from 'react'  // add if missing
import { SearchContext } from '../context/SearchContext'
```

Inside the main `Knowledge` component:

```tsx
const { searchTarget, setSearchTarget } = useContext(SearchContext)

useEffect(() => {
  if (!searchTarget || searchTarget.tab !== 'knowledge') return
  const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('search-highlight')
  const timer = setTimeout(() => {
    el.classList.remove('search-highlight')
    setSearchTarget(null)
  }, 2000)
  return () => clearTimeout(timer)
}, [searchTarget, setSearchTarget])
```

- [ ] **Step 2: Add data-item-id to knowledge base list item**

Find line ~307 (list item div in `bases.map(k => ...`):

```tsx
// Before
<div
  key={k.id}
  onClick={() => setSelected(k)}
  style={{

// After
<div
  key={k.id}
  data-item-id={k.id}
  onClick={() => setSelected(k)}
  style={{
```

- [ ] **Step 3: Type-check and commit**

```bash
cd webui && npx tsc --noEmit
git add webui/src/pages/Knowledge.tsx
git commit -m "feat(search): Knowledge page — data-item-id + search highlight"
```

---

## Task 11: Highlight — MCP page

**Files:**
- Modify: `webui/src/pages/MCP.tsx`

- [ ] **Step 1: Add import and hook**

```tsx
import { useContext, useEffect } from 'react'  // add if missing
import { SearchContext } from '../context/SearchContext'
```

Inside the `MCP` component (the main exported component, not sub-components):

```tsx
const { searchTarget, setSearchTarget } = useContext(SearchContext)

useEffect(() => {
  if (!searchTarget || searchTarget.tab !== 'mcp') return
  const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('search-highlight')
  const timer = setTimeout(() => {
    el.classList.remove('search-highlight')
    setSearchTarget(null)
  }, 2000)
  return () => clearTimeout(timer)
}, [searchTarget, setSearchTarget])
```

- [ ] **Step 2: Add data-item-id to MCP server card**

Find line ~260 (card div in `servers.map(s => ...`):

```tsx
// Before
<div key={s.id} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', overflow: 'hidden' }}>

// After
<div key={s.id} data-item-id={s.id} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
```

- [ ] **Step 3: Type-check and commit**

```bash
cd webui && npx tsc --noEmit
git add webui/src/pages/MCP.tsx
git commit -m "feat(search): MCP page — data-item-id + search highlight"
```

---

## Task 12: Manual verification

- [ ] **Step 1: Start dev server**

```bash
cd webui && npm run dev
```

- [ ] **Step 2: Verify CTRL+K opens modal**

Press CTRL+K on any page. The search modal should appear centered with a dark backdrop. The search input should be auto-focused.

- [ ] **Step 3: Verify clicking Header search bar also opens modal**

Click the search bar in the Header (where it says "SEARCH AGENTS / SKILLS / TOOLS..."). Modal should open.

- [ ] **Step 4: Verify search and keyboard navigation**

Type any partial agent/skill/tool name. Results should appear grouped by category with matching text highlighted in green. Press ↑↓ to move selection. Press ESC to close.

- [ ] **Step 5: Verify navigation and highlight**

Click a result (e.g., an Agent). The modal should close, the Agents tab should activate, and the matching card should scroll into view and flash a green outline for ~2 seconds.

- [ ] **Step 6: Verify recent tabs**

Open the modal without typing. The RECENT section should show the last 3 tabs you visited as quick-jump shortcuts.

- [ ] **Step 7: Verify empty state**

Type a query that matches nothing. Should show: `NO RESULTS — TRY ANOTHER QUERY`.

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "feat(search): CTRL+K global search — complete implementation"
```
