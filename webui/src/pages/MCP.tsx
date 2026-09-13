import { useState, useEffect, useContext, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, ChevronDown, ChevronRight, Server, Activity, Wrench } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { SearchContext } from '../context/search'
import { errorMessage } from '../lib/errorMessage'
import Modal from '../components/Modal'

interface MCPServer {
  id?: number
  name: string
  transport_type: string
  command?: string
  args?: string[]
  url?: string
  description?: string
  is_active?: boolean
  timeout_seconds?: number
}

interface MCPTool {
  id?: number
  server_id: number
  tool_name: string
  description?: string
  category?: string
  is_active?: boolean
  use_count?: number
  tags?: string[]
}

interface ServerForm {
  name: string
  transport_type: string
  command: string
  args_text: string
  url: string
  description: string
  timeout: number
  is_active: boolean
}

const emptyServerForm: ServerForm = {
  name: '', transport_type: 'stdio', command: '', args_text: '', url: '',
  description: '', timeout: 30, is_active: true,
}

const CATEGORY_COLORS: Record<string, string> = {
  threat: 'var(--red)',
  log: 'var(--amber)',
  vuln: '#ff6b00',
  recon: 'var(--cyan)',
  general: 'var(--text-muted)',
}

export default function MCP() {
  const { t } = useTranslation()
  const [servers, setServers] = useState<MCPServer[]>([])
  const [tools, setTools] = useState<MCPTool[]>([])
  const [tab, setTab] = useState<'servers' | 'tools'>('servers')
  const [serverTools, setServerTools] = useState<Record<number, MCPTool[]>>({})
  const [expandedServer, setExpandedServer] = useState<number | null>(null)
  const [showServerForm, setShowServerForm] = useState(false)
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null)
  const [serverForm, setServerForm] = useState<ServerForm>(emptyServerForm)
  const [tagFilter, setTagFilter] = useState('')

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

  const loadServers = useCallback(async () => {
    try {
      const data = await api.getMCPServers() as { servers: MCPServer[] }
      setServers(data?.servers || [])
    } catch { setServers([]) }
  }, [])

  const loadTools = useCallback(async (currentServers: MCPServer[]) => {
    const all: MCPTool[] = []
    const map: Record<number, MCPTool[]> = {}
    for (const s of currentServers) {
      if (!s.id) continue
      try {
        const data = await api.getMCPServerTools(s.id) as { tools: MCPTool[] }
        if (data?.tools) {
          all.push(...data.tools)
          map[s.id] = data.tools
        }
      } catch { /* skip a server that fails to list tools */ }
    }
    setTools(all)
    setServerTools(map)
  }, [])

  const loadAllTools = async () => {
    try {
      const data = await api.getAllMcpTools(tagFilter ? `?tag=${encodeURIComponent(tagFilter)}` : '') as MCPTool[] | { tools?: MCPTool[] }
      setTools(Array.isArray(data) ? data : data?.tools || [])
    } catch { setTools([]) }
  }

  useEffect(() => { void Promise.resolve().then(() => loadServers()) }, [loadServers])
  useEffect(() => { if (servers.length) void Promise.resolve().then(() => loadTools(servers)) }, [servers, loadTools])

  const submitServer = async () => {
    if (!serverForm.name) return
    const args = serverForm.args_text.trim() ? serverForm.args_text.split('\n').map(s => s.trim()).filter(Boolean) : undefined
    const payload = {
      name: serverForm.name,
      transport_type: serverForm.transport_type,
      command: serverForm.command || undefined,
      args,
      url: serverForm.url || undefined,
      description: serverForm.description || undefined,
      timeout: serverForm.timeout,
      is_active: serverForm.is_active,
    }
    try {
      if (editingServer?.id) await api.updateMCPServer(editingServer.id, payload)
      else await api.createMCPServer(payload)
      setShowServerForm(false); setEditingServer(null); setServerForm(emptyServerForm)
      loadServers()
    } catch (e: unknown) { alert(errorMessage(e)) }
  }

  const delServer = async (id: number) => {
    if (!confirm('DELETE THIS MCP SERVER?')) return
    try { await api.deleteMCPServer(id); loadServers() } catch (e: unknown) { alert(errorMessage(e)) }
  }

  const toggleExpand = (id: number) => setExpandedServer(expandedServer === id ? null : id)

  const openEditServer = (s: MCPServer) => {
    setEditingServer(s)
    setServerForm({
      name: s.name, transport_type: s.transport_type, command: s.command || '',
      args_text: (s.args || []).join('\n'), url: s.url || '', description: s.description || '',
      timeout: s.timeout_seconds || 30, is_active: s.is_active ?? true,
    })
    setShowServerForm(true)
  }

  return (
    <div>
      <PageHeader
        eyebrow="MODEL CONTEXT PROTOCOL"
        title={t('mcp.title').toUpperCase()}
        actions={
          <button
            onClick={() => { setEditingServer(null); setServerForm(emptyServerForm); setShowServerForm(true) }}
            className="btn btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: 8 }}
          >
            <Plus size={13} /> NEW SERVER
          </button>
        }
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, border: '1px solid var(--border-bright)', borderRadius: 'var(--radius-md)', overflow: 'hidden', width: 'fit-content' }}>
        {([
          { id: 'servers' as const, label: 'SERVERS', count: servers.length },
          { id: 'tools' as const, label: 'TOOLS', count: tools.length },
        ]).map(({ id, label, count }) => (
          <button key={id} onClick={() => setTab(id)}
            style={{
              padding: '8px 20px', height: 34,
              background: tab === id ? 'var(--accent-dim)' : 'transparent',
              border: 'none', borderRight: '1px solid var(--border-bright)',
              color: tab === id ? 'var(--accent)' : 'var(--text-muted)',
              fontSize: 12, letterSpacing: '0.06em', cursor: 'pointer',
                          }}>
            {label} <span style={{ marginLeft: 6, opacity: 0.6 }}>({count})</span>
          </button>
        ))}
      </div>

      {/* Server Form Modal */}
      {showServerForm && (
        <Modal
          eyebrow="SERVER CONFIGURATION"
          title={editingServer ? 'EDIT SERVER' : 'NEW MCP SERVER'}
          onClose={() => { setShowServerForm(false); setEditingServer(null) }}
          footer={(
            <>
              <button onClick={() => { setShowServerForm(false); setEditingServer(null) }} className="btn btn-secondary">
                CANCEL
              </button>
              <button onClick={submitServer} className="btn btn-primary">
                {editingServer ? 'SAVE CHANGES' : 'CREATE SERVER'}
              </button>
            </>
          )}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label className="form-label">NAME *</label>
              <input value={serverForm.name} disabled={!!editingServer}
                onChange={e => setServerForm(f => ({ ...f, name: e.target.value }))}
                placeholder="my-mcp-server"
                className="form-input" />
            </div>
            <div>
              <label className="form-label">TRANSPORT</label>
              <select value={serverForm.transport_type} onChange={e => setServerForm(f => ({ ...f, transport_type: e.target.value }))}
                className="form-input">
                <option value="stdio">STDIO</option>
                <option value="sse">SSE</option>
                <option value="streamable_http">HTTP</option>
              </select>
            </div>
          </div>
          {serverForm.transport_type === 'stdio' ? (
            <>
              <div>
                <label className="form-label">COMMAND</label>
                <input value={serverForm.command} onChange={e => setServerForm(f => ({ ...f, command: e.target.value }))}
                  placeholder="npx"
                  className="form-input" />
              </div>
              <div>
                <label className="form-label">ARGS (ONE PER LINE)</label>
                <textarea value={serverForm.args_text} onChange={e => setServerForm(f => ({ ...f, args_text: e.target.value }))}
                  rows={3}
                  placeholder={"@modelcontextprotocol/server-filesystem\n/path/to/dir"}
                  className="form-textarea" />
              </div>
            </>
          ) : (
            <div>
              <label className="form-label">HTTP ENDPOINT URL</label>
              <input value={serverForm.url} onChange={e => setServerForm(f => ({ ...f, url: e.target.value }))}
                placeholder="https://mcp.example.com"
                className="form-input" />
            </div>
          )}
          <div>
            <label className="form-label">DESCRIPTION</label>
            <input value={serverForm.description} onChange={e => setServerForm(f => ({ ...f, description: e.target.value }))}
              className="form-input" />
          </div>
        </Modal>
      )}

      {/* Servers Tab */}
      {tab === 'servers' && (
        servers.length === 0 ? (
          <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 48, gap: 12 }}>
            <Server size={28} style={{ color: 'var(--text-dim)' }} />
            <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO MCP SERVERS DEFINED</div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>CLICK "NEW SERVER" TO REGISTER ONE</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {servers.map(s => {
              const sTools = (s.id && serverTools[s.id]) || []
              const expanded = expandedServer === s.id
              return (
                <div key={s.id} data-item-id={s.id} className="item-card" style={{ padding: 0, overflow: 'hidden' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px' }}>
                    <button onClick={() => s.id && toggleExpand(s.id)} className="item-card-icon-btn">
                      {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <span className="item-card-pip" style={{ background: s.is_active ? 'var(--accent)' : 'var(--text-dim)' }} />
                        <span className="item-card-title">{s.name}</span>
                        <span className="item-card-badge" style={{ color: 'var(--cyan)' }}>{s.transport_type.toUpperCase()}</span>
                        <span className="item-card-badge" style={{ color: s.is_active ? 'var(--green)' : 'var(--text-dim)' }}>
                          {s.is_active ? 'ACTIVE' : 'INACTIVE'}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{sTools.length} TOOLS</span>
                      </div>
                      {(s.command || s.url) && (
                        <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.03em' }}>
                          {s.command ? `${s.command} ${(s.args || []).join(' ')}` : s.url}
                        </div>
                      )}
                      {s.description && <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>{s.description}</div>}
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => openEditServer(s)} className="item-card-icon-btn">
                        <Edit2 size={13} />
                      </button>
                      <button onClick={() => s.id && delServer(s.id)} className="item-card-icon-btn danger">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                  {expanded && (
                    <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px', background: 'var(--bg-base)' }}>
                      <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 10 }}>TOOLS</div>
                      {sTools.length === 0 ? (
                        <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>NO TOOLS DISCOVERED</div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {sTools.map(t => (
                            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 8px', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
                              <Wrench size={11} style={{ color: CATEGORY_COLORS[t.category || 'general'], flexShrink: 0 }} />
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 13, color: 'var(--text-primary)', letterSpacing: '0.05em' }}>{t.tool_name}</div>
                                {t.description && <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{t.description}</div>}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      )}

      {/* Tools Tab */}
      {tab === 'tools' && (
        <>
          <div style={{ marginBottom: 16 }}>
            <input value={tagFilter} onChange={e => setTagFilter(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') loadAllTools() }}
              placeholder="filter by tag…"
              className="form-input" />
          </div>
          {tools.length === 0 ? (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 48, gap: 12 }}>
              <Wrench size={28} style={{ color: 'var(--text-dim)' }} />
              <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO MCP TOOLS FOUND</div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>REGISTER AND START A SERVER FIRST</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {tools.map(t => {
                const tc = CATEGORY_COLORS[t.category || 'general']
                return (
                <div key={t.id} className="item-card" style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', padding: '10px 14px', gap: 12 }}>
                  <span className="item-card-pip" style={{ background: tc }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className="item-card-title" style={{ fontSize: 14 }}>{t.tool_name}</span>
                      <span className="item-card-badge" style={{ color: tc }}>
                        {(t.category || 'general').toUpperCase()}
                      </span>
                    </div>
                    {t.description && <div className="item-card-desc" style={{ fontSize: 12, marginTop: 2 }}>{t.description}</div>}
                    {t.tags && t.tags.length > 0 && (
                      <span style={{ fontSize: 11, color: 'var(--cyan)', marginTop: 2, display: 'block' }}>{t.tags.join(', ')}</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-dim)', flexShrink: 0 }}>
                    <Activity size={11} />
                    <span>{t.use_count ?? 0} CALLS</span>
                  </div>
                </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
