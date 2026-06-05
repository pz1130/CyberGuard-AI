// webui/src/components/GlobalSearch.tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import { useSearch } from '../context/SearchContext'
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
  const loadedAtRef = useRef(0)
  const CACHE_TTL = 60_000

  // Load all searchable data; re-fetch when cache is stale (> 60s old)
  useEffect(() => {
    if (!open) return
    const stale = Date.now() - loadedAtRef.current > CACHE_TTL
    if (!stale) return
    if (allItems.length === 0) setLoadingData(true)
    Promise.allSettled([
      api.getAgents(),
      api.getProviders(),
      api.getSkills(),
      api.getTools(),
      api.getKnowledgeBases(),
      api.getMCPServers(),
      api.getScheduledTasks(),
      api.getWebhooks(),
      api.getFrameworks(),
      api.getAssessments(),
      api.getPromptTemplates(),
      api.getN8NConnections(),
      api.getConversations(),
    ]).then(([agents, providers, skills, tools, knowledge, mcp, schedule, webhooks, frameworks, assessments, prompts, n8n, convos]) => {
      const items: SearchItem[] = []

      if (agents.status === 'fulfilled') {
        const d = agents.value as any
        const list = Array.isArray(d) ? d : (d?.agents || [])
        list.forEach((a: any) => {
          const k = (a.kind || '').toLowerCase()
          const isInternal = k === 'internal' || a.backend_type === '__internal__'
          const suffix = isInternal ? 'INTERNAL' : (a.backend_type || 'AGENT').toUpperCase()
          items.push({
            id: a.id, name: a.agent_name || a.name || String(a.id),
            subtitle: suffix,
            tab: 'agents', category: 'AGENTS', icon: '◆',
          })
        })
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
        const list = Array.isArray(d) ? d : (d?.bases || [])
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

      if (schedule.status === 'fulfilled') {
        const d = schedule.value as any
        const list = Array.isArray(d) ? d : (d?.tasks || d?.schedules || [])
        list.forEach((t: any) => items.push({
          id: t.task_id || t.id, name: t.name,
          subtitle: (t.task_type || 'TASK').toUpperCase(),
          tab: 'schedule', category: 'SCHEDULE', icon: '○',
        }))
      }

      if (webhooks.status === 'fulfilled') {
        const d = webhooks.value as any
        const list = Array.isArray(d) ? d : (d?.webhooks || [])
        list.forEach((w: any) => items.push({
          id: w.id, name: w.name,
          subtitle: (w.direction || 'WEBHOOK').toUpperCase(),
          tab: 'webhooks', category: 'WEBHOOKS', icon: '⟳',
        }))
      }

      if (frameworks.status === 'fulfilled') {
        const d = frameworks.value as any
        const list = Array.isArray(d) ? d : []
        list.forEach((f: any) => items.push({
          id: f.id, name: f.name,
          subtitle: f.version ? `v${f.version}` : 'FRAMEWORK',
          tab: 'governance', category: 'FRAMEWORKS', icon: '▦',
          subview: 'frameworks',
        }))
      }

      if (assessments.status === 'fulfilled') {
        const d = assessments.value as any
        const list = Array.isArray(d) ? d : []
        list.forEach((a: any) => items.push({
          id: a.id, name: a.name,
          subtitle: a.framework_name || 'ASSESSMENT',
          tab: 'governance', category: 'ASSESSMENTS', icon: '▧',
          subview: 'list',
        }))
      }

      if (prompts.status === 'fulfilled') {
        const d = prompts.value as any
        const list = Array.isArray(d) ? d : []
        list.forEach((p: any) => items.push({
          id: p.id, name: p.name,
          subtitle: (p.category || 'PROMPT').toUpperCase(),
          tab: 'prompts', category: 'PROMPTS', icon: '≡',
        }))
      }

      if (n8n.status === 'fulfilled') {
        const d = n8n.value as any
        const list = Array.isArray(d) ? d : (d?.connections || [])
        list.forEach((c: any) => items.push({
          id: c.id, name: c.name,
          subtitle: c.base_url || 'N8N CONNECTION',
          tab: 'n8n', category: 'N8N', icon: '⌥',
        }))
      }

      if (convos.status === 'fulfilled') {
        const d = convos.value as any
        const list = Array.isArray(d) ? d : (d?.conversations || [])
        list.forEach((c: any) => {
          // Parse messages for search
          let msgs: Array<{ role: string; content: string }> = []
          try {
            msgs = typeof c.messages_json === 'string' ? JSON.parse(c.messages_json || '[]') : []
          } catch { msgs = [] }
          // Build a searchable text from the last few messages
          const lastMsgs = msgs.slice(-6)
          const previewText = lastMsgs.map(m => m.content || '').join(' ').slice(0, 200)
          items.push({
            id: c.id,
            name: c.title || `Conversation #${c.id}`,
            subtitle: msgs.length > 0 ? `${msgs.length} messages` : 'EMPTY',
            tab: 'chat',
            category: 'CONVERSATIONS',
            icon: '◉',
            preview: previewText,
          })
        })
      }

      setAllItems(items)
      setLoadingData(false)
      loadedAtRef.current = Date.now()
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
    ? allItems.filter(item => {
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

          {!loadingData && !q && recentTabs.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.1em' }}>
              TYPE TO SEARCH ACROSS AGENTS, PROVIDERS, SKILLS, TOOLS, KNOWLEDGE, MCP, SCHEDULE, WEBHOOKS, PROMPTS, N8N, GOVERNANCE
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
