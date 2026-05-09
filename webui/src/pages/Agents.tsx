import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Plus, Loader2, Cpu, Trash, Pencil } from 'lucide-react'

interface Agent {
  id?: string
  name: string
  agent_type: string
  backend_type?: string
  description?: string
  model?: string
  endpoint_url?: string
  env_vars?: Record<string, string>
  is_active?: boolean
  // OpenClaw fields (stored in metadata_json or direct)
  api_key?: string
  auth_mode?: 'api_key' | 'bearer' | 'none'
  streaming?: boolean
  system_prompt?: string
  permission_level?: string
  mcp_tool_ids?: number[]
  metadata_json?: Record<string, any>
}

interface MCPTool {
  id: number
  tool_name: string
  description?: string
  category?: string
  server_name?: string
}

const BACKEND_COLORS: Record<string, string> = {
  openclaw: 'var(--green)',
  hermes: 'var(--amber)',
  custom: 'var(--text-muted)',
}

export default function Agents() {
  const [items, setItems] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Agent>({ name: '', agent_type: 'sub_agent', backend_type: 'custom', description: '', model: '', endpoint_url: '', env_vars: {}, api_key: '', auth_mode: 'api_key', streaming: true, system_prompt: '', permission_level: 'medium' })
  const [envVarsText, setEnvVarsText] = useState('')
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, string>>({})
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([])
  const [selectedMcpToolIds, setSelectedMcpToolIds] = useState<number[]>([])

  const load = async () => {
    try {
      const data = await api.getAgents() as Agent[] | { agents?: Agent[] }
      setItems(Array.isArray(data) ? data : data?.agents || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      let envVars: Record<string, string> | undefined
      if (envVarsText.trim()) {
        envVars = {}
        for (const line of envVarsText.trim().split('\n')) {
          const eqIdx = line.indexOf('=')
          if (eqIdx > 0) envVars[line.slice(0, eqIdx).trim()] = line.slice(eqIdx + 1).trim()
        }
      }
      // Build metadata_json with mcp_tool_ids
      const { mcp_tool_ids, metadata_json, ...rest } = form
      const meta = { ...(metadata_json || {}) }
      if (selectedMcpToolIds.length > 0) {
        meta.mcp_tool_ids = selectedMcpToolIds
      }
      const payload = {
        ...rest,
        env_vars: envVars,
        metadata_json: Object.keys(meta).length > 0 ? meta : undefined,
      }
      if (editing) await api.updateAgent(editing, payload)
      else await api.createAgent(payload)
      setShowForm(false); setEditing(null)
      setForm({ name: '', agent_type: 'sub_agent', backend_type: 'custom', description: '', model: '', endpoint_url: '', env_vars: {}, api_key: '', auth_mode: 'api_key', streaming: true, system_prompt: '', permission_level: 'medium' })
      setEnvVarsText('')
      setSelectedMcpToolIds([])
      load()
    } catch (e: any) { alert(e.message) }
  }

  const del = async (id: string) => {
    if (!confirm('CONFIRM DELETION?')) return
    await api.deleteAgent(id); load()
  }

  const test = async (id: string) => {
    setTesting(id); setTestResult(r => ({ ...r, [id]: '' }))
    try {
      const res = await api.testAgent(id, { message: 'Hello' }) as any
      setTestResult(r => ({ ...r, [id]: res.response || res.reply || 'TEST COMPLETE' }))
    } catch (e: any) { setTestResult(r => ({ ...r, [id]: `ERROR: ${e.message}` })) }
    finally { setTesting(null) }
  }

  const openForm = (a?: Agent) => {
    if (a) {
      setEditing(a.id!); setForm({ ...a })
      setEnvVarsText(Object.entries(a.env_vars || {}).map(([k, v]) => `${k}=${v}`).join('\n'))
      const ids = a.mcp_tool_ids || a.metadata_json?.mcp_tool_ids || []
      setSelectedMcpToolIds(Array.isArray(ids) ? ids.map(Number) : [])
    } else {
      setEditing(null)
      setForm({ name: '', agent_type: 'sub_agent', backend_type: 'custom', description: '', model: '', endpoint_url: '', env_vars: {}, api_key: '', auth_mode: 'api_key', streaming: true, system_prompt: '', permission_level: 'medium' })
      setEnvVarsText('')
      setSelectedMcpToolIds([])
    }
    setShowForm(true)
  }

  // Load MCP tools when form opens for openclaw agent
  useEffect(() => {
    if (showForm && form.backend_type === 'openclaw' && mcpTools.length === 0) {
      api.getAllMcpTools().then((data: any) => {
        const list = data?.tools || []
        // Attach server_name if available
        setMcpTools(list)
      }).catch(() => {})
    }
  }, [showForm, form.backend_type])

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>AGENT INFRASTRUCTURE</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SUB-AGENTS</h1>
        </div>
        <button
          onClick={() => openForm()}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '0 16px', height: 36,
            background: 'var(--accent)', border: '1px solid var(--accent-border)',
            color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.15em',
            cursor: 'pointer', fontFamily: 'var(--font-mono)',
            boxShadow: '0 0 16px rgba(0,255,65,0.15)',
          }}>
          <Plus size={13} /> NEW AGENT
        </button>
      </div>

      {/* Grid */}
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 0' }}>
          <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 12 }}>
          <div style={{
            width: 48, height: 48,
            border: '1px solid var(--border-bright)', background: 'var(--bg-surface)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22,
          }}>
            <Cpu size={20} style={{ color: 'var(--text-dim)' }} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO ACTIVE AGENTS</div>
          <button onClick={() => openForm()} style={{ fontSize: 10, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + DEPLOY FIRST AGENT
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {items.map(a => {
            const bc = BACKEND_COLORS[a.backend_type || 'custom'] || 'var(--text-muted)'
            const isActive = !!a.endpoint_url
            return (
              <div key={a.id} style={{
                padding: 20,
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-bright)',
                borderLeft: `3px solid ${bc}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>{a.name}</div>
                  <div style={{
                    display: 'inline-block',
                    padding: '2px 6px',
                    border: `1px solid ${bc}`,
                    fontSize: 8, letterSpacing: '0.15em', color: bc,
                    background: 'var(--bg-base)',
                  }}>
                    {(a.backend_type || 'custom').toUpperCase()}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                  <div style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: isActive ? 'var(--green)' : 'var(--text-dim)',
                    boxShadow: isActive ? '0 0 6px var(--green)' : 'none',
                  }} />
                  <span style={{ fontSize: 10, color: isActive ? 'var(--green)' : 'var(--text-dim)', letterSpacing: '0.1em' }}>
                    {isActive ? 'OPERATIONAL' : 'IDLE'}
                  </span>
                </div>

                {a.description && (
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 12, letterSpacing: '0.02em' }}>
                    {a.description}
                  </div>
                )}

                {a.model && (
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
                    MODEL: {a.model}
                  </div>
                )}

                <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <button
                    onClick={() => test(a.id!)}
                    disabled={testing === a.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 5,
                      padding: '0 10px', height: 28,
                      border: '1px solid var(--border-bright)',
                      background: testing === a.id ? 'var(--bg-elevated)' : 'transparent',
                      color: testing === a.id ? 'var(--text-dim)' : 'var(--accent)',
                      fontSize: 10, letterSpacing: '0.1em', cursor: testing === a.id ? 'not-allowed' : 'pointer',
                      fontFamily: 'var(--font-mono)', transition: 'all 0.15s',
                    }}>
                    {testing === a.id ? 'TESTING...' : 'TEST'}
                  </button>
                  <div style={{ display: 'flex', gap: 12 }}>
                    <button onClick={() => openForm(a)}
                      style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      <Pencil size={12} />
                    </button>
                    <button onClick={() => del(a.id!)}
                      style={{ padding: 4, color: 'var(--red)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      <Trash size={12} />
                    </button>
                  </div>
                </div>

                {testResult[a.id!] && (
                  <div style={{
                    marginTop: 10, padding: '8px 10px',
                    background: 'var(--bg-base)', border: '1px solid var(--border)',
                    fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)',
                    letterSpacing: '0.02em', lineHeight: 1.6,
                  }}>
                    {testResult[a.id!]}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Modal */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px 0' }}
          onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div style={{
            width: 560, maxHeight: 'calc(100vh - 80px)', background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            padding: 24, overflowY: 'auto',
          }}>
            <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 12, marginBottom: 16 }}>
              <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>AGENT CONFIGURATION</div>
              <h3 style={{ fontSize: 16, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{editing ? 'EDIT AGENT' : 'DEPLOY NEW AGENT'}</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>NAME</label>
                  <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="e.g. Threat Intelligence Agent"
                    style={{
                      width: '100%', height: 38, padding: '0 12px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                      fontFamily: 'var(--font-mono)',
                    }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>BACKEND TYPE</label>
                  <select value={form.backend_type || 'custom'} onChange={e => setForm(f => ({ ...f, backend_type: e.target.value }))}
                    style={{
                      width: '100%', height: 38, padding: '0 12px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)',
                    }}>
                    <option value="openclaw">OPENCLAW</option>
                    <option value="hermes">HERMES</option>
                    <option value="custom">CUSTOM</option>
                  </select>
                </div>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>ENDPOINT URL</label>
                <input value={form.endpoint_url || ''} onChange={e => setForm(f => ({ ...f, endpoint_url: e.target.value }))}
                  placeholder="http://localhost:8001"
                  style={{
                    width: '100%', height: 38, padding: '0 12px',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                    fontFamily: 'var(--font-mono)',
                  }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>DESCRIPTION</label>
                <input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  style={{
                    width: '100%', height: 38, padding: '0 12px',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                    fontFamily: 'var(--font-mono)',
                  }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>ENV VARS (KEY=VALUE, ONE PER LINE)</label>
                <textarea value={envVarsText} onChange={e => setEnvVarsText(e.target.value)}
                  placeholder="API_KEY=sk-..."
                  rows={2}
                  style={{
                    width: '100%', padding: '8px 12px',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    color: 'var(--text-primary)', fontSize: 11, letterSpacing: '0.05em',
                    fontFamily: 'var(--font-mono)', resize: 'none',
                  }} />
              </div>

              {/* Permission Level */}
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>PERMISSION LEVEL</label>
                <select value={form.permission_level || 'medium'} onChange={e => setForm(f => ({ ...f, permission_level: e.target.value }))}
                  style={{
                    width: '100%', height: 38, padding: '0 12px',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)',
                  }}>
                  <option value="low">LOW — No approval required</option>
                  <option value="medium">MEDIUM — May require approval</option>
                  <option value="high">HIGH — Always requires admin approval</option>
                </select>
              </div>

              {/* OpenClaw-specific fields */}
              {form.backend_type === 'openclaw' && (
                <>
                  <div>
                    <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>API KEY</label>
                    <input type="password" value={form.api_key || ''} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                      placeholder="sk-... (leave empty if no auth)"
                      style={{
                        width: '100%', height: 38, padding: '0 12px',
                        background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                        color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                        fontFamily: 'var(--font-mono)',
                      }} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div>
                      <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>AUTH MODE</label>
                      <select value={form.auth_mode || 'api_key'} onChange={e => setForm(f => ({ ...f, auth_mode: e.target.value as 'api_key' | 'bearer' | 'none' }))}
                        style={{
                          width: '100%', height: 38, padding: '0 12px',
                          background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                          color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)',
                        }}>
                        <option value="api_key">API KEY (X-API-Key header)</option>
                        <option value="bearer">BEARER TOKEN</option>
                        <option value="none">NONE (no auth)</option>
                      </select>
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>STREAMING</label>
                      <div style={{ display: 'flex', alignItems: 'center', height: 38, gap: 10 }}>
                        <input type="checkbox" checked={form.streaming !== false} onChange={e => setForm(f => ({ ...f, streaming: e.target.checked }))}
                          style={{ width: 16, height: 16, accentColor: 'var(--accent)' }} />
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>Enable streaming responses</span>
                      </div>
                    </div>
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>SYSTEM PROMPT (OPTIONAL OVERRIDE)</label>
                    <textarea value={form.system_prompt || ''} onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                      placeholder="Additional instructions prepended to the agent's system prompt..."
                      rows={2}
                      style={{
                        width: '100%', padding: '8px 12px',
                        background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                        color: 'var(--text-primary)', fontSize: 11, letterSpacing: '0.05em',
                        fontFamily: 'var(--font-mono)', resize: 'none',
                      }} />
                  </div>

                  {/* MCP Tools selector */}
                  <div>
                    <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>MCP TOOLS (LEAVE ALL TO EXPOSE ALL)</label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 120, overflowY: 'auto', padding: '6px 8px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)' }}>
                      {mcpTools.length === 0 && (
                        <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>No MCP tools available — configure MCP servers first</span>
                      )}
                      {mcpTools.map(t => (
                        <label key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={selectedMcpToolIds.includes(t.id)}
                            onChange={e => {
                              if (e.target.checked) setSelectedMcpToolIds(prev => [...prev, t.id])
                              else setSelectedMcpToolIds(prev => prev.filter(id => id !== t.id))
                            }}
                            style={{ width: 14, height: 14, accentColor: 'var(--accent)' }}
                          />
                          <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', letterSpacing: '0.03em' }}>
                            {t.tool_name}
                          </span>
                          {t.server_name && (
                            <span style={{ fontSize: 9, color: 'var(--text-dim)' }}>({t.server_name})</span>
                          )}
                        </label>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Help text for OpenClaw */}
              {form.backend_type === 'openclaw' && (
                <div style={{ padding: '8px 10px', background: 'var(--bg-base)', border: '1px solid var(--border)', fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.6, letterSpacing: '0.03em' }}>
                  <span style={{ color: 'var(--accent)', fontWeight: 600 }}>OPENCLAW</span> — Remote agent must expose:<br />
                  • <span style={{ fontFamily: 'var(--font-mono)' }}>GET /capabilities</span> — Tool list<br />
                  • <span style={{ fontFamily: 'var(--font-mono)' }}>POST /execute</span> — Run tasks<br />
                  • <span style={{ fontFamily: 'var(--font-mono)' }}>GET /health</span> — Health check
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
              <button onClick={() => setShowForm(false)}
                style={{
                  flex: 1, height: 40, border: '1px solid var(--border-bright)',
                  background: 'transparent', color: 'var(--text-muted)',
                  fontSize: 11, letterSpacing: '0.15em', cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                }}>
                CANCEL
              </button>
              <button onClick={submit}
                style={{
                  flex: 1, height: 40, border: '1px solid var(--accent-border)',
                  background: 'var(--accent)', color: '#000',
                  fontWeight: 700, fontSize: 11, letterSpacing: '0.15em', cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                }}>
                {editing ? 'SAVE CHANGES' : 'DEPLOY AGENT'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
