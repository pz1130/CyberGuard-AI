import { RoleContext, canAccessTab } from '../context/permissions'
// webui/src/components/GlobalSearch.tsx
import { useState, useEffect, useRef, useCallback, useContext } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import { useSearch } from '../context/search'
import { unwrapList } from '../lib/unwrapList'
import type { Tab } from './SidebarNew'

interface SearchItem {
  id: number | string
  name: string
  subtitle: string
  tab: Tab
  category: string
  icon: string
  subview?: string
  /** Preview snippet (for conversation search results) */
  preview?: string
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
  mcp: 'MCP',
  envvars: 'ENV VARS', security: 'SECURITY', token: 'TOKEN USAGE',
  backup: 'BACKUP', audit: 'AUDIT LOGS', users: 'USERS',
  settings: 'SETTINGS',
  prompts: 'PROMPTS', govDashboard: 'AGENT GOVERNANCE',
}

export default function GlobalSearch({ open, onClose, setTab, recentTabs }: Props) {
  const role = useContext(RoleContext)
  const [query, setQuery] = useState('')
  const [allItems, setAllItems] = useState<SearchItem[]>([])
  // Keyed by the term they answer, so results from a previous query are simply
  // not used rather than cleared — clearing synchronously inside the effect
  // cascades renders, and leaving them unkeyed showed stale hits while the next
  // response was in flight.
  const [messageHits, setMessageHits] =
    useState<{ term: string; items: SearchItem[] }>({ term: '', items: [] })
  const [catalogReady, setCatalogReady] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [prevOpen, setPrevOpen] = useState(open)
  const [prevQuery, setPrevQuery] = useState(query)
  const { setSearchTarget } = useSearch()
  const inputRef = useRef<HTMLInputElement>(null)
  const loadedAtRef = useRef(0)
  const CACHE_TTL = 60_000

  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setQuery('')
      setSelectedIndex(0)
    }
  }
  if (query !== prevQuery) {
    setPrevQuery(query)
    setSelectedIndex(0)
  }

  // Load all searchable data; re-fetch when cache is stale (> 60s old)
  useEffect(() => {
    if (!open) return
    const stale = Date.now() - loadedAtRef.current > CACHE_TTL
    if (!stale) return
    Promise.allSettled([
      api.getAgents(),
      api.getProviders(),
      api.getSkills(),
      api.getTools(),
      canAccessTab(role, 'knowledge') ? api.getKnowledgeBases() : Promise.resolve([]),
      api.getMCPServers(),
      canAccessTab(role, 'prompts') ? api.getPromptTemplates() : Promise.resolve([]),
      api.getConversations(),
    ]).then(([agents, providers, skills, tools, knowledge, mcp, prompts, convos]) => {
      const items: SearchItem[] = []

      type AgentRow = { id?: number | string; name?: string; agent_name?: string; kind?: string; backend_type?: string }
      type NamedRow = { id?: number | string; name?: string; description?: string; provider_type?: string; url?: string; category?: string }
      type ConvRow = {
        id: number
        title?: string
        message_count?: number
        last_message_preview?: string | null
      }

      if (agents.status === 'fulfilled') {
        for (const a of unwrapList<AgentRow>(agents.value, 'agents')) {
          const k = (a.kind || '').toLowerCase()
          const isInternal = k === 'internal' || a.backend_type === '__internal__'
          const suffix = isInternal ? 'INTERNAL' : (a.backend_type || 'AGENT').toUpperCase()
          items.push({
            id: a.id ?? '', name: a.agent_name || a.name || String(a.id),
            subtitle: suffix,
            tab: 'agents', category: 'AGENTS', icon: '◆',
          })
        }
      }

      if (providers.status === 'fulfilled') {
        for (const p of unwrapList<NamedRow>(providers.value, 'providers')) {
          items.push({
            id: p.id ?? '', name: p.name || '',
            subtitle: (p.provider_type || 'PROVIDER').toUpperCase(),
            tab: 'providers', category: 'PROVIDERS', icon: '▣',
          })
        }
      }

      if (skills.status === 'fulfilled') {
        for (const s of unwrapList<NamedRow>(skills.value, 'skills')) {
          items.push({
            id: s.id ?? '', name: s.name || '',
            subtitle: s.description ? String(s.description).slice(0, 40) : 'SKILL',
            tab: 'skills', category: 'SKILLS', icon: '◈',
          })
        }
      }

      if (tools.status === 'fulfilled') {
        for (const t of unwrapList<NamedRow>(tools.value, 'tools')) {
          items.push({
            id: t.id ?? '', name: t.name || '',
            subtitle: t.description ? String(t.description).slice(0, 40) : 'TOOL',
            tab: 'tools', category: 'TOOLS', icon: '◇',
          })
        }
      }

      if (knowledge.status === 'fulfilled') {
        for (const k of unwrapList<NamedRow>(knowledge.value, 'knowledge_bases', 'bases')) {
          items.push({
            id: k.id ?? '', name: k.name || '',
            subtitle: 'KNOWLEDGE BASE',
            tab: 'knowledge', category: 'KNOWLEDGE', icon: '◉',
          })
        }
      }

      if (mcp.status === 'fulfilled') {
        for (const m of unwrapList<NamedRow>(mcp.value, 'servers')) {
          items.push({
            id: m.id ?? '', name: m.name || '',
            subtitle: m.url || 'MCP SERVER',
            tab: 'mcp', category: 'MCP', icon: '◎',
          })
        }
      }

      if (prompts.status === 'fulfilled') {
        for (const p of unwrapList<NamedRow>(prompts.value, 'templates')) {
          items.push({
            id: p.id ?? '', name: p.name || '',
            subtitle: (p.category || 'PROMPT').toUpperCase(),
            tab: 'prompts', category: 'PROMPTS', icon: '≡',
          })
        }
      }

      if (convos.status === 'fulfilled') {
        for (const c of unwrapList<ConvRow>(convos.value, 'conversations')) {
          const count = c.message_count ?? 0
          items.push({
            id: c.id,
            name: c.title || `Conversation #${c.id}`,
            subtitle: count > 0 ? `${count} messages` : 'EMPTY',
            tab: 'chat',
            category: 'CONVERSATIONS',
            icon: '◉',
            // The transcript is no longer shipped with the listing. Full-text
            // search over messages arrives with the server-side endpoint.
            preview: c.last_message_preview || '',
          })
        }
      }

      setAllItems(items.filter(item => canAccessTab(role, item.tab)))
      setCatalogReady(true)
      loadedAtRef.current = Date.now()
    })
  }, [open, role])

  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => inputRef.current?.focus(), 30)
      return () => clearTimeout(timer)
    }
  }, [open, role])

  // Message search runs on the server: the conversation list no longer carries
  // transcripts, and the browser only ever held the 50 most recent anyway.
  useEffect(() => {
    const term = query.trim()
    if (!open || !term) return

    let cancelled = false
    const timer = setTimeout(() => {
      void api.searchConversationMessages(term)
        .then(res => {
          if (cancelled) return
          const rows = (res as { results?: Array<{
            conversation_id: number; conversation_title?: string | null
            hits?: number
            matches?: Array<{ message_id: number; snippet?: string }>
          }> }).results || []
          setMessageHits({
            term,
            items: rows.map(r => ({
              id: `msg-${r.conversation_id}`,
              name: r.conversation_title || `Conversation #${r.conversation_id}`,
              // One row per conversation; the count is what the reader would
              // otherwise have had to gather from repeated rows.
              subtitle: (r.hits ?? 1) > 1 ? `${r.hits} MATCHES` : 'MATCH',
              tab: 'chat' as Tab,
              category: 'CONVERSATIONS',
              icon: '◉',
              // The palette shows one line; the evidence panel shows them all.
              preview: r.matches?.[0]?.snippet || '',
            })),
          })
        })
        .catch(() => { if (!cancelled) setMessageHits({ term, items: [] }) })
    }, 250)

    return () => { cancelled = true; clearTimeout(timer) }
  }, [query, open])

  // Filter and group by category
  const q = query.toLowerCase().trim()
  // Server-side message hits are already matched; only the catalog needs
  // filtering. Titles still match locally, so a title hit needs no round trip.
  const hits = messageHits.term === q ? messageHits.items : []
  const filtered = q
    ? [...hits, ...allItems].filter(item => {
        if (!canAccessTab(role, item.tab)) return false
        if (item.id.toString().startsWith('msg-')) return true
        if (item.name.toLowerCase().includes(q) || item.subtitle.toLowerCase().includes(q)) return true
        // Also search inside conversation preview text
        if (item.category === 'CONVERSATIONS' && item.preview) {
          return item.preview.toLowerCase().includes(q)
        }
        return false
      })
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
    setSearchTarget({ tab: item.tab, id: item.id, name: item.name, subview: item.subview })
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

  const catalogLoading = !catalogReady && allItems.length === 0

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
            placeholder="SEARCH AGENTS / SKILLS / TOOLS / WEBHOOKS / SCHEDULE..."
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              color: 'var(--text-primary)', fontSize: 14,
              letterSpacing: '0.05em',             }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em', flexShrink: 0 }}>ESC</span>
        </div>

        {/* Results area */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {catalogLoading && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.1em' }}>
              LOADING...
            </div>
          )}

          {/* Recent tabs (shown when query is empty) */}
          {!catalogLoading && !q && recentTabs.length > 0 && (
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
                    fontSize: 13, letterSpacing: '0.08em',
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

          {!catalogLoading && !q && recentTabs.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.1em' }}>
              TYPE TO SEARCH ACROSS AGENTS, PROVIDERS, SKILLS, TOOLS, KNOWLEDGE, MCP, PROMPTS
            </div>
          )}

          {!catalogLoading && q && categories.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.1em' }}>
              NO RESULTS — TRY ANOTHER QUERY
            </div>
          )}

          {/* Grouped results */}
          {!catalogLoading && categories.map(cat => (
            <div key={cat}>
              <div style={{ padding: '8px 16px 4px', fontSize: 11, letterSpacing: '0.15em', color: 'var(--text-dim)' }}>
                {cat}
              </div>
              {grouped[cat].map(item => {
                const currentIdx = itemIndexMap.get(item)!
                const isSelected = selectedIndex === currentIdx
                const nameQ = item.name.toLowerCase().indexOf(q)
                const nameDisplay: ReactNode = nameQ >= 0 ? (
                  <>
                    {item.name.slice(0, nameQ)}
                    <span style={{ color: 'var(--accent)', fontWeight: 700 }}>
                      {item.name.slice(nameQ, nameQ + q.length)}
                    </span>
                    {item.name.slice(nameQ + q.length)}
                  </>
                ) : item.name

                // Build a highlighted preview snippet for conversation results
                let previewDisplay: ReactNode = null
                if (item.category === 'CONVERSATIONS' && item.preview && q) {
                  const pLow = item.preview.toLowerCase()
                  const pIdx = pLow.indexOf(q)
                  if (pIdx >= 0) {
                    const start = Math.max(0, pIdx - 30)
                    const end = Math.min(item.preview.length, pIdx + q.length + 50)
                    const before = (start > 0 ? '…' : '') + item.preview.slice(start, pIdx)
                    const match = item.preview.slice(pIdx, pIdx + q.length)
                    const after = item.preview.slice(pIdx + q.length, end) + (end < item.preview.length ? '…' : '')
                    previewDisplay = (
                      <div style={{
                        fontSize: 12, color: 'var(--text-dim)', marginTop: 3,
                        lineHeight: 1.5, fontFamily: 'var(--font-sans)',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                      }}>
                        {before}<span style={{ color: 'var(--accent)', fontWeight: 600 }}>{match}</span>{after}
                      </div>
                    )
                  } else {
                    previewDisplay = (
                      <div style={{
                        fontSize: 12, color: 'var(--text-dim)', marginTop: 3,
                        lineHeight: 1.5, fontFamily: 'var(--font-sans)',
                        overflow: 'hidden', textOverflow: 'ellipsis',
                        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                      }}>
                        {item.preview.slice(0, 100)}{item.preview.length > 100 ? '…' : ''}
                      </div>
                    )
                  }
                }

                return (
                  <div
                    key={`${cat}-${item.id}`}
                    onClick={() => select(item)}
                    onMouseEnter={() => setSelectedIndex(currentIdx)}
                    style={{
                      padding: previewDisplay ? '8px 16px' : '0 16px',
                      minHeight: 40,
                      cursor: 'pointer',
                      background: isSelected ? 'var(--accent-dim)' : 'transparent',
                      borderLeft: isSelected ? '2px solid var(--accent)' : '2px solid transparent',
                      transition: 'background 0.1s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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
                    {previewDisplay}
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
