import { useState, useEffect, useContext } from 'react'
import { api } from '../api/client'
import { GitBranch, Plus, Trash2, Edit2, Play, Square, Loader2, Zap, X, Wifi, WifiOff, Search, Workflow, Server, ArrowRight } from 'lucide-react'
import { SearchContext } from '../context/SearchContext'

interface N8NConnection {
  id?: number
  name: string
  base_url: string
  api_key?: string
  is_active?: boolean
  is_default?: boolean
}

interface N8NWorkflow {
  id: string
  name: string
  active: boolean
  nodes_count: number
  tags: string[]
}

interface ConnectionForm {
  name: string
  base_url: string
  api_key: string
  is_active: boolean
  is_default: boolean
}

const emptyConnectionForm: ConnectionForm = {
  name: '',
  base_url: '',
  api_key: '',
  is_active: true,
  is_default: false,
}

export default function N8N() {
  const [connections, setConnections] = useState<N8NConnection[]>([])
  const [workflows, setWorkflows] = useState<N8NWorkflow[]>([])
  const [selectedConn, setSelectedConn] = useState<N8NConnection | null>(null)
  const [showConnForm, setShowConnForm] = useState(false)
  const [editingConn, setEditingConn] = useState<N8NConnection | null>(null)
  const [connForm, setConnForm] = useState<ConnectionForm>(emptyConnectionForm)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; error?: string; workflow_count?: number } | null>(null)
  const [loadingWorkflows, setLoadingWorkflows] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // AI Generation state
  const [showGenerator, setShowGenerator] = useState(false)
  const [genDescription, setGenDescription] = useState('')
  const [generating, setGenerating] = useState(false)
  const [generatedJson, setGeneratedJson] = useState<any>(null)
  const [genError, setGenError] = useState('')
  const [creatingWorkflow, setCreatingWorkflow] = useState(false)

  const loadConnections = async () => {
    try {
      const data = await api.getN8NConnections() as N8NConnection[]
      setConnections(data || [])
      if (data?.length && !selectedConn) {
        const defaultConn = data.find(c => c.is_default) || data[0]
        setSelectedConn(defaultConn)
        loadWorkflows(defaultConn)
      }
    } catch { setConnections([]) }
  }

  const loadWorkflows = async (conn: N8NConnection) => {
    setLoadingWorkflows(true)
    try {
      const data = await api.getN8NWorkflows(conn.id) as N8NWorkflow[]
      setWorkflows(data || [])
    } catch { setWorkflows([]) }
    setLoadingWorkflows(false)
  }

  useEffect(() => { loadConnections() }, [])

  const { searchTarget, setSearchTarget } = useContext(SearchContext)
  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'n8n') return
    const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('search-highlight')
    }
    const t = setTimeout(() => setSearchTarget(null), 2000)
    return () => clearTimeout(t)
  }, [searchTarget, setSearchTarget])

  const submitConnection = async () => {
    if (!connForm.name || !connForm.base_url) return
    try {
      if (editingConn?.id) {
        await api.updateN8NConnection(editingConn.id, connForm)
      } else {
        await api.createN8NConnection(connForm)
      }
      setShowConnForm(false)
      setEditingConn(null)
      setConnForm(emptyConnectionForm)
      loadConnections()
    } catch (e: any) { alert(e.message) }
  }

  const testConnection = async (conn: N8NConnection) => {
    if (!conn.id) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testN8NConnection(conn.id) as any
      setTestResult(result)
    } catch (e: any) { setTestResult({ success: false, error: e.message }) }
    setTesting(false)
  }

  const deleteConnection = async (conn: N8NConnection, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!conn.id || !confirm('Delete this connection?')) return
    try {
      await api.deleteN8NConnection(conn.id)
      if (selectedConn?.id === conn.id) setSelectedConn(null)
      loadConnections()
    } catch (e: any) { alert(e.message) }
  }

  const openEditConn = (conn: N8NConnection) => {
    setEditingConn(conn)
    setConnForm({
      name: conn.name,
      base_url: conn.base_url,
      api_key: conn.api_key === '******' ? '' : (conn.api_key || ''),
      is_active: conn.is_active || false,
      is_default: conn.is_default || false,
    })
    setShowConnForm(true)
  }

  const generateWorkflow = async () => {
    if (!genDescription.trim()) return
    setGenerating(true)
    setGenError('')
    setGeneratedJson(null)
    try {
      const result = await api.generateN8NWorkflow({
        description: genDescription,
        connection_id: selectedConn?.id,
      }) as any
      if (result?.workflow_json?.error) {
        setGenError(result.workflow_json.error)
      } else {
        setGeneratedJson(result?.workflow_json)
      }
    } catch (e: any) { setGenError(e.message) }
    setGenerating(false)
  }

  const createWorkflowInN8N = async () => {
    if (!generatedJson || !selectedConn) return
    const name = generatedJson.name || genDescription.slice(0, 30) || 'Generated Workflow'
    setCreatingWorkflow(true)
    try {
      await api.createN8NWorkflow({ name, workflow_json: generatedJson })
      setShowGenerator(false)
      setGenDescription('')
      setGeneratedJson(null)
      loadWorkflows(selectedConn)
    } catch (e: any) { alert(e.message) }
    setCreatingWorkflow(false)
  }

  const filteredWorkflows = workflows.filter(w =>
    w.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const activeCount = connections.filter(c => c.is_active).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, height: '100%' }}>
      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 12, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Workflow size={11} /> AUTOMATION
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-primary)' }}>N8N WORKFLOWS</h1>
          <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 12, color: 'var(--text-dim)' }}>
            <span>{connections.length} connections · {activeCount} active</span>
            <span>{workflows.length} workflows</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => { setEditingConn(null); setConnForm(emptyConnectionForm); setShowConnForm(true) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 28,
              border: '1px solid var(--border-bright)', background: 'var(--bg-surface)',
              color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.08em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-bright)'; e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <Plus size={12} /> NEW CONNECTION
          </button>
          <button onClick={() => setShowGenerator(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 28,
              background: 'var(--accent)', border: '1px solid var(--accent)',
              color: '#000', fontWeight: 700, fontSize: 12, letterSpacing: '0.08em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', transition: 'opacity 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
            onMouseLeave={e => e.currentTarget.style.opacity = '1'}
          >
            <Zap size={12} /> AI GENERATE
          </button>
        </div>
      </div>

      {/* ── Main Grid ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20, flex: 1, minHeight: 0, alignItems: 'stretch' }}>
        {/* ── Connections Panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, overflow: 'auto', height: '100%' }}>
          <div style={{ fontSize: 12, letterSpacing: '0.08em', color: 'var(--text-dim)', fontWeight: 600, padding: '0 4px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Server size={10} /> CONNECTIONS
          </div>

          {connections.map(conn => {
            const isSelected = selectedConn?.id === conn.id
            return (
              <div key={conn.id} data-item-id={conn.id}
                onClick={() => { setSelectedConn(conn); loadWorkflows(conn) }}
                style={{
                  padding: '14px 16px',
                  border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
                  background: isSelected ? 'rgba(0,255,65,0.04)' : 'var(--bg-surface)',
                  cursor: 'pointer', transition: 'all 0.15s',
                  position: 'relative',
                }}
                onMouseEnter={e => { if (!isSelected) e.currentTarget.style.borderColor = 'var(--border-bright)' }}
                onMouseLeave={e => { if (!isSelected) e.currentTarget.style.borderColor = 'var(--border)' }}
              >
                {isSelected && <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 2, background: 'var(--accent)' }} />}

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: isSelected ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                      border: `1px solid ${isSelected ? 'var(--accent-border)' : 'var(--border)'}`,
                    }}>
                      {conn.is_active
                        ? <Wifi size={12} style={{ color: 'var(--green)' }} />
                        : <WifiOff size={12} style={{ color: 'var(--text-dim)' }} />
                      }
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: isSelected ? 'var(--accent)' : 'var(--text-primary)' }}>
                        {conn.name}
                      </div>
                      {conn.is_default && (
                        <span style={{ fontSize: 9, letterSpacing: '0.08em', color: 'var(--cyan)', fontWeight: 600 }}>DEFAULT</span>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 2 }}>
                    <button onClick={(e) => { e.stopPropagation(); openEditConn(conn) }}
                      style={{ padding: 4, color: 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer', borderRadius: 2 }}
                      onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
                      onMouseLeave={e => e.currentTarget.style.color = 'var(--text-dim)'}
                    ><Edit2 size={11} /></button>
                    <button onClick={(e) => deleteConnection(conn, e)}
                      style={{ padding: 4, color: 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer', borderRadius: 2 }}
                      onMouseEnter={e => e.currentTarget.style.color = 'var(--red)'}
                      onMouseLeave={e => e.currentTarget.style.color = 'var(--text-dim)'}
                    ><Trash2 size={11} /></button>
                  </div>
                </div>

                <div style={{ fontSize: 11, color: 'var(--text-dim)', wordBreak: 'break-all', marginBottom: 8, opacity: 0.7 }}>
                  {conn.base_url}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <div style={{
                      width: 5, height: 5, borderRadius: '50%',
                      background: conn.is_active ? 'var(--green)' : 'var(--text-dim)',
                      boxShadow: conn.is_active ? '0 0 6px var(--green)' : 'none',
                    }} />
                    <span style={{ fontSize: 10, letterSpacing: '0.06em', color: conn.is_active ? 'var(--green)' : 'var(--text-dim)' }}>
                      {conn.is_active ? 'ONLINE' : 'OFFLINE'}
                    </span>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); testConnection(conn) }} disabled={testing}
                    style={{
                      padding: '3px 10px', fontSize: 10, letterSpacing: '0.06em',
                      background: 'transparent', border: '1px solid var(--border)',
                      color: 'var(--text-dim)', cursor: testing ? 'not-allowed' : 'pointer',
                      fontFamily: 'var(--font-mono)', transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { if (!testing) { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = 'var(--accent)' }}}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-dim)'}}
                  >
                    {testing ? '...' : 'TEST'}
                  </button>
                </div>

                {testResult && isSelected && (
                  <div style={{
                    marginTop: 10, padding: '8px 10px', fontSize: 11,
                    background: testResult.success ? 'rgba(0,255,65,0.06)' : 'rgba(255,59,48,0.06)',
                    border: `1px solid ${testResult.success ? 'rgba(0,255,65,0.2)' : 'rgba(255,59,48,0.2)'}`,
                    color: testResult.success ? 'var(--green)' : 'var(--red)',
                  }}>
                    {testResult.success ? `Connected — ${testResult.workflow_count} workflows` : testResult.error}
                  </div>
                )}
              </div>
            )
          })}

          {connections.length === 0 && (
            <div style={{
              padding: '32px 20px', textAlign: 'center',
              border: '1px dashed var(--border)', background: 'var(--bg-surface)',
              flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            }}>
              <Server size={28} style={{ color: 'var(--text-dim)', marginBottom: 12, opacity: 0.4 }} />
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 4, letterSpacing: '0.06em' }}>NO CONNECTIONS</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', opacity: 0.6 }}>Add an N8N instance to get started</div>
              <button onClick={() => { setEditingConn(null); setConnForm(emptyConnectionForm); setShowConnForm(true) }}
                style={{
                  marginTop: 16, padding: '6px 16px', fontSize: 11, letterSpacing: '0.06em',
                  background: 'transparent', border: '1px solid var(--accent)',
                  color: 'var(--accent)', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                }}>
                <Plus size={10} /> ADD CONNECTION
              </button>
            </div>
          )}
        </div>

        {/* ── Workflows Panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflow: 'auto', height: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ fontSize: 12, letterSpacing: '0.08em', color: 'var(--text-dim)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <GitBranch size={10} /> WORKFLOWS
              {selectedConn && <span style={{ fontSize: 10, color: 'var(--text-dim)', opacity: 0.5 }}>· {selectedConn.name}</span>}
            </div>
            {selectedConn && (
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={11} style={{ position: 'absolute', left: 10, color: 'var(--text-dim)' }} />
                <input
                  type="text" placeholder="Search..." value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  style={{
                    width: 180, height: 28, padding: '0 10px 0 28px', fontSize: 11,
                    background: 'var(--bg-surface)', border: '1px solid var(--border)',
                    color: 'var(--text-primary)', fontFamily: 'var(--font-mono)',
                  }}
                />
              </div>
            )}
          </div>

          {loadingWorkflows ? (
            <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-dim)' }}>
              <Loader2 size={24} className="spin" style={{ marginBottom: 12, opacity: 0.4 }} />
              <div style={{ fontSize: 11, letterSpacing: '0.06em' }}>LOADING WORKFLOWS...</div>
            </div>
          ) : !selectedConn ? (
            <div style={{
              padding: 60, textAlign: 'center',
              border: '1px dashed var(--border)', background: 'var(--bg-surface)',
              flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            }}>
              <div style={{
                width: 48, height: 48, margin: '0 auto 16px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--bg-elevated)', border: '1px solid var(--border)',
              }}>
                <ArrowRight size={20} style={{ color: 'var(--text-dim)', opacity: 0.4 }} />
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.06em' }}>SELECT A CONNECTION</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', opacity: 0.5, marginTop: 4 }}>Choose from the left panel to view workflows</div>
            </div>
          ) : filteredWorkflows.length === 0 ? (
            <div style={{
              padding: 60, textAlign: 'center',
              border: '1px dashed var(--border)', background: 'var(--bg-surface)',
            }}>
              <Workflow size={28} style={{ color: 'var(--text-dim)', marginBottom: 12, opacity: 0.4 }} />
              <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.06em' }}>
                {searchQuery ? 'NO MATCHING WORKFLOWS' : 'NO WORKFLOWS'}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', opacity: 0.5, marginTop: 4 }}>
                {searchQuery ? 'Try a different search term' : 'Create one with AI Generate or in N8N directly'}
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {filteredWorkflows.map(wf => (
                <div key={wf.id} style={{
                  padding: '14px 16px', border: '1px solid var(--border)',
                  background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', gap: 14,
                  transition: 'border-color 0.15s',
                }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-bright)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                >
                  <div style={{
                    width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: wf.active ? 'rgba(0,255,65,0.06)' : 'var(--bg-elevated)',
                    border: `1px solid ${wf.active ? 'rgba(0,255,65,0.2)' : 'var(--border)'}`,
                    flexShrink: 0,
                  }}>
                    <GitBranch size={15} style={{ color: wf.active ? 'var(--green)' : 'var(--text-dim)' }} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {wf.name}
                    </div>
                    <div style={{ display: 'flex', gap: 12, fontSize: 10, color: 'var(--text-dim)' }}>
                      <span>{wf.nodes_count} nodes</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <div style={{
                          width: 5, height: 5, borderRadius: '50%',
                          background: wf.active ? 'var(--green)' : 'var(--text-dim)',
                          boxShadow: wf.active ? '0 0 6px var(--green)' : 'none',
                        }} />
                        {wf.active ? 'ACTIVE' : 'DRAFT'}
                      </span>
                    </div>
                  </div>
                  <button style={{
                    width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: wf.active ? 'var(--amber)' : 'var(--green)',
                    background: 'transparent', border: '1px solid var(--border)', cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                    onMouseEnter={e => e.currentTarget.style.borderColor = wf.active ? 'var(--amber)' : 'var(--green)'}
                    onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
                  >
                    {wf.active ? <Square size={11} /> : <Play size={11} />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Connection Form Modal ── */}
      {showConnForm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        }} onClick={e => e.target === e.currentTarget && setShowConnForm(false)}>
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            padding: 0, width: 480, maxHeight: '85vh', overflowY: 'auto',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '16px 20px', borderBottom: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', color: 'var(--text-primary)' }}>
                {editingConn ? 'EDIT CONNECTION' : 'NEW CONNECTION'}
              </div>
              <button onClick={() => setShowConnForm(false)}
                style={{ padding: 4, color: 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer' }}>
                <X size={14} />
              </button>
            </div>
            <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 10, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>NAME</label>
                <input value={connForm.name} onChange={e => setConnForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="My N8N Instance"
                  style={{ width: '100%', height: 36, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 10, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>BASE URL</label>
                <input value={connForm.base_url} onChange={e => setConnForm(f => ({ ...f, base_url: e.target.value }))} placeholder="https://n8n.example.com"
                  style={{ width: '100%', height: 36, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 10, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>API KEY</label>
                <input value={connForm.api_key} onChange={e => setConnForm(f => ({ ...f, api_key: e.target.value }))} type="password" placeholder="Leave empty to keep existing"
                  style={{ width: '100%', height: 36, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)' }} />
              </div>
              <div style={{ display: 'flex', gap: 20 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={connForm.is_active} onChange={e => setConnForm(f => ({ ...f, is_active: e.target.checked }))}
                    style={{ width: 14, height: 14, accentColor: 'var(--accent)' }} />
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>ACTIVE</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={connForm.is_default} onChange={e => setConnForm(f => ({ ...f, is_default: e.target.checked }))}
                    style={{ width: 14, height: 14, accentColor: 'var(--accent)' }} />
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>DEFAULT</span>
                </label>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button onClick={() => setShowConnForm(false)} style={{
                  flex: 1, height: 36, border: '1px solid var(--border)', background: 'transparent',
                  color: 'var(--text-muted)', fontSize: 11, letterSpacing: '0.06em', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}>CANCEL</button>
                <button onClick={submitConnection} style={{
                  flex: 1, height: 36, background: 'var(--accent)', border: '1px solid var(--accent)',
                  color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.06em', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}>{editingConn ? 'UPDATE' : 'CREATE'}</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── AI Generator Modal ── */}
      {showGenerator && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        }} onClick={e => e.target === e.currentTarget && setShowGenerator(false)}>
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            padding: 0, width: 600, maxHeight: '85vh', overflowY: 'auto',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '16px 20px', borderBottom: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Zap size={14} /> AI WORKFLOW GENERATOR
              </div>
              <button onClick={() => setShowGenerator(false)}
                style={{ padding: 4, color: 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer' }}>
                <X size={14} />
              </button>
            </div>
            <div style={{ padding: 20 }}>
              {!selectedConn ? (
                <div style={{ padding: 30, textAlign: 'center', color: 'var(--amber)', fontSize: 12, letterSpacing: '0.06em' }}>
                  SELECT A CONNECTION FIRST
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 10, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>DESCRIBE YOUR WORKFLOW</label>
                    <textarea value={genDescription} onChange={e => setGenDescription(e.target.value)}
                      rows={4} placeholder="e.g., 每小时检查邮箱，重要客户邮件发送 Slack 通知"
                      style={{
                        width: '100%', padding: '10px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)',
                        color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)', resize: 'vertical',
                      }} />
                  </div>
                  <button onClick={generateWorkflow} disabled={generating || !genDescription.trim()}
                    style={{
                      height: 36, background: generating ? 'var(--bg-elevated)' : 'var(--accent)',
                      border: `1px solid ${generating ? 'var(--border)' : 'var(--accent)'}`,
                      color: generating ? 'var(--text-muted)' : '#000',
                      fontWeight: 700, fontSize: 11, letterSpacing: '0.06em',
                      cursor: generating ? 'not-allowed' : 'pointer',
                      fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    }}>
                    {generating ? <><Loader2 size={11} className="spin" /> GENERATING...</> : <><Zap size={11} /> GENERATE WORKFLOW JSON</>}
                  </button>
                  {genError && (
                    <div style={{ padding: '10px 12px', background: 'rgba(255,59,48,0.06)', border: '1px solid rgba(255,59,48,0.2)', fontSize: 11, color: 'var(--red)' }}>
                      ERROR: {genError}
                    </div>
                  )}
                  {generatedJson && (
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <label style={{ fontSize: 10, letterSpacing: '0.08em', color: 'var(--text-dim)' }}>GENERATED JSON</label>
                        <span style={{ fontSize: 11, color: 'var(--accent)' }}>{generatedJson.name || 'Untitled'}</span>
                      </div>
                      <pre style={{
                        padding: 12, background: 'var(--bg-base)', border: '1px solid var(--border)',
                        fontSize: 11, color: 'var(--text-primary)', maxHeight: 260, overflow: 'auto',
                        fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.5,
                      }}>
                        {JSON.stringify(generatedJson, null, 2)}
                      </pre>
                      <button onClick={createWorkflowInN8N} disabled={creatingWorkflow}
                        style={{
                          marginTop: 12, height: 36, width: '100%',
                          background: 'var(--green)', border: '1px solid var(--green)',
                          color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.06em',
                          cursor: creatingWorkflow ? 'not-allowed' : 'pointer',
                          fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                        }}>
                        {creatingWorkflow ? <><Loader2 size={11} className="spin" /> CREATING...</> : <><GitBranch size={11} /> CREATE IN N8N</>}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
