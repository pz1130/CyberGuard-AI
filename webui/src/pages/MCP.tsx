import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Trash2, Plus, Edit2, ChevronDown, ChevronRight, Server, Activity, Wrench } from 'lucide-react'

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
  const [servers, setServers] = useState<MCPServer[]>([])
  const [tools, setTools] = useState<MCPTool[]>([])
  const [tab, setTab] = useState<'servers' | 'tools'>('servers')
  const [serverTools, setServerTools] = useState<Record<number, MCPTool[]>>({})
  const [expandedServer, setExpandedServer] = useState<number | null>(null)
  const [showServerForm, setShowServerForm] = useState(false)
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null)
  const [serverForm, setServerForm] = useState<ServerForm>(emptyServerForm)
  const [tagFilter, setTagFilter] = useState('')

  const loadServers = async () => {
    try {
      const data = await api.getMCPServers() as { servers: MCPServer[] }
      setServers(data?.servers || [])
    } catch { setServers([]) }
  }

  const loadTools = async (currentServers: MCPServer[]) => {
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
      } catch {}
    }
    setTools(all)
    setServerTools(map)
  }

  const loadAllTools = async () => {
    try {
      const data = await api.getAllMcpTools(tagFilter ? `?tag=${encodeURIComponent(tagFilter)}` : '') as MCPTool[] | { tools?: MCPTool[] }
      setTools(Array.isArray(data) ? data : data?.tools || [])
    } catch { setTools([]) }
  }

  useEffect(() => { loadServers() }, [])
  useEffect(() => { if (servers.length) loadTools(servers) }, [servers.length])

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
    } catch (e: any) { alert(e.message) }
  }

  const delServer = async (id: number) => {
    if (!confirm('DELETE THIS MCP SERVER?')) return
    try { await api.deleteMCPServer(id); loadServers() } catch (e: any) { alert(e.message) }
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
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>MODEL CONTEXT PROTOCOL</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>MCP SERVERS</h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => { setEditingServer(null); setServerForm(emptyServerForm); setShowServerForm(true) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '0 16px', height: 36,
              background: 'var(--accent)', border: '1px solid var(--accent-border)',
              color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
            }}>
            <Plus size={13} /> NEW SERVER
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, border: '1px solid var(--border-bright)', width: 'fit-content' }}>
        {[['servers', 'SERVERS', servers.length], ['tools', 'TOOLS', tools.length]].map(([t, label, count]) => (
          <button key={t} onClick={() => setTab(t as any)}
            style={{
              padding: '8px 20px', height: 34,
              background: tab === t ? 'var(--accent-dim)' : 'transparent',
              border: 'none', borderRight: '1px solid var(--border-bright)',
              color: tab === t ? 'var(--accent)' : 'var(--text-muted)',
              fontSize: 12, letterSpacing: '0.15em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
            }}>
            {label} <span style={{ marginLeft: 6, opacity: 0.6 }}>({count})</span>
          </button>
        ))}
      </div>

      {/* Server Form Modal */}
      {showServerForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
          onClick={e => e.target === e.currentTarget && setShowServerForm(false)}>
          <div style={{ width: 560, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', padding: 32 }}>
            <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 16, marginBottom: 24 }}>
              <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>SERVER CONFIGURATION</div>
              <h3 style={{ fontSize: 18, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{editingServer ? 'EDIT SERVER' : 'NEW MCP SERVER'}</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>NAME *</label>
                  <input value={serverForm.name} disabled={!!editingServer}
                    onChange={e => setServerForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="my-mcp-server"
                    style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>TRANSPORT</label>
                  <select value={serverForm.transport_type} onChange={e => setServerForm(f => ({ ...f, transport_type: e.target.value }))}
                    style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }}>
                    <option value="stdio">STDIO</option>
                    <option value="sse">SSE</option>
                    <option value="streamable_http">HTTP</option>
                  </select>
                </div>
              </div>
              {serverForm.transport_type === 'stdio' ? (
                <>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>COMMAND</label>
                    <input value={serverForm.command} onChange={e => setServerForm(f => ({ ...f, command: e.target.value }))}
                      placeholder="npx"
                      style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }} />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>ARGS (ONE PER LINE)</label>
                    <textarea value={serverForm.args_text} onChange={e => setServerForm(f => ({ ...f, args_text: e.target.value }))}
                      rows={3}
                      placeholder="@modelcontextprotocol/server-filesystem\n/path/to/dir"
                      style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)', resize: 'none' }} />
                  </div>
                </>
              ) : (
                <div>
                  <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>HTTP ENDPOINT URL</label>
                  <input value={serverForm.url} onChange={e => setServerForm(f => ({ ...f, url: e.target.value }))}
                    placeholder="https://mcp.example.com"
                    style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }} />
                </div>
              )}
              <div>
                <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>DESCRIPTION</label>
                <input value={serverForm.description} onChange={e => setServerForm(f => ({ ...f, description: e.target.value }))}
                  style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)' }} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 28 }}>
              <button onClick={() => { setShowServerForm(false); setEditingServer(null) }}
                style={{ flex: 1, height: 40, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                CANCEL
              </button>
              <button onClick={submitServer}
                style={{ flex: 1, height: 40, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                {editingServer ? 'SAVE CHANGES' : 'CREATE SERVER'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Servers Tab */}
      {tab === 'servers' && (
        servers.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 12, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
            <Server size={28} style={{ color: 'var(--text-dim)' }} />
            <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO MCP SERVERS DEFINED</div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>CLICK "NEW SERVER" TO REGISTER ONE</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {servers.map(s => {
              const sTools = (s.id && serverTools[s.id]) || []
              const expanded = expandedServer === s.id
              return (
                <div key={s.id} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px' }}>
                    <button onClick={() => s.id && toggleExpand(s.id)}
                      style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>{s.name}</span>
                        <span style={{ padding: '2px 6px', border: '1px solid var(--border)', color: 'var(--cyan)', fontSize: 10, letterSpacing: '0.15em', background: 'var(--bg-base)' }}>{s.transport_type.toUpperCase()}</span>
                        <span style={{ padding: '2px 6px', border: `1px solid ${s.is_active ? 'var(--green)' : 'var(--border)'}`, color: s.is_active ? 'var(--green)' : 'var(--text-dim)', fontSize: 10, letterSpacing: '0.15em', background: s.is_active ? 'rgba(0,255,65,0.05)' : 'transparent' }}>
                          {s.is_active ? 'ACTIVE' : 'INACTIVE'}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{sTools.length} TOOLS</span>
                      </div>
                      {(s.command || s.url) && (
                        <div style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', letterSpacing: '0.03em' }}>
                          {s.command ? `${s.command} ${(s.args || []).join(' ')}` : s.url}
                        </div>
                      )}
                      {s.description && <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>{s.description}</div>}
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => openEditServer(s)}
                        style={{ padding: 6, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: '1px solid var(--border-bright)' }}>
                        <Edit2 size={12} />
                      </button>
                      <button onClick={() => s.id && delServer(s.id)}
                        style={{ padding: 6, color: 'var(--red)', cursor: 'pointer', background: 'none', border: '1px solid rgba(255,59,48,0.2)' }}>
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  {expanded && (
                    <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px', background: 'var(--bg-base)' }}>
                      <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 10 }}>TOOLS</div>
                      {sTools.length === 0 ? (
                        <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>NO TOOLS DISCOVERED</div>
                      ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
                          {sTools.map(t => (
                            <div key={t.id} style={{ padding: '10px 12px', background: 'var(--bg-surface)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                              <Wrench size={11} style={{ color: CATEGORY_COLORS[t.category || 'general'], flexShrink: 0 }} />
                              <div>
                                <div style={{ fontSize: 13, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', letterSpacing: '0.05em' }}>{t.tool_name}</div>
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
              style={{ width: '100%', height: 38, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }} />
          </div>
          {tools.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 12, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
              <Wrench size={28} style={{ color: 'var(--text-dim)' }} />
              <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO MCP TOOLS FOUND</div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>REGISTER AND START A SERVER FIRST</div>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              {tools.map(t => (
                <div key={t.id} style={{ padding: 16, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
                    <div style={{ fontSize: 14, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', letterSpacing: '0.05em' }}>{t.tool_name}</div>
                    <span style={{ padding: '2px 6px', border: `1px solid ${CATEGORY_COLORS[t.category || 'general']}`, color: CATEGORY_COLORS[t.category || 'general'], fontSize: 10, letterSpacing: '0.15em', background: 'var(--bg-base)' }}>
                      {(t.category || 'general').toUpperCase()}
                    </span>
                  </div>
                  {t.description && <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 10 }}>{t.description}</div>}
                  {t.tags && t.tags.length > 0 && (
                    <span style={{ fontSize: 11, color: '#60a5fa' }}>{t.tags.join(', ')}</span>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                    <Activity size={10} style={{ color: 'var(--text-dim)' }} />
                    <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{t.use_count ?? 0} CALLS</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
