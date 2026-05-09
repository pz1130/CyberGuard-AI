import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { GitBranch, Plus, Trash2, Edit2, Play, Square, Loader2, Zap, X } from 'lucide-react'

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

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>AUTOMATION</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>N8N WORKFLOWS</h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => { setEditingConn(null); setConnForm(emptyConnectionForm); setShowConnForm(true) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 36,
              border: '1px solid var(--border-bright)', background: 'transparent',
              color: 'var(--text-muted)', fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
            }}>
            <Plus size={11} /> NEW CONNECTION
          </button>
          <button onClick={() => setShowGenerator(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 36,
              background: 'var(--accent)', border: '1px solid var(--accent-border)',
              color: '#000', fontWeight: 700, fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
            }}>
            <Zap size={11} /> AI GENERATE
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 24 }}>
        {/* Connection Panel */}
        <div>
          <div style={{ fontSize: 10, letterSpacing: '0.15em', color: 'var(--text-muted)', marginBottom: 12, fontWeight: 600 }}>CONNECTIONS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {connections.map(conn => (
              <div key={conn.id} onClick={() => { setSelectedConn(conn); loadWorkflows(conn) }}
                style={{
                  padding: '12px 14px', border: `1px solid ${selectedConn?.id === conn.id ? 'var(--accent)' : 'var(--border-bright)'}`,
                  background: selectedConn?.id === conn.id ? 'var(--accent-dim)' : 'var(--bg-surface)',
                  cursor: 'pointer', transition: 'all 0.15s',
                }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: selectedConn?.id === conn.id ? 'var(--accent)' : 'var(--text-primary)', letterSpacing: '0.05em' }}>
                    {conn.name}
                    {conn.is_default && <span style={{ marginLeft: 6, fontSize: 9, color: 'var(--cyan)' }}>DEFAULT</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={(e) => { e.stopPropagation(); openEditConn(conn) }} style={{ padding: 2, color: 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer' }}><Edit2 size={10} /></button>
                    <button onClick={(e) => deleteConnection(conn, e)} style={{ padding: 2, color: 'var(--red)', background: 'none', border: 'none', cursor: 'pointer' }}><Trash2 size={10} /></button>
                  </div>
                </div>
                <div style={{ fontSize: 9, color: 'var(--text-dim)', marginBottom: 6, wordBreak: 'break-all' }}>{conn.base_url}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: conn.is_active ? 'var(--green)' : 'var(--text-dim)' }} />
                    <span style={{ fontSize: 9, color: 'var(--text-dim)' }}>{conn.is_active ? 'ACTIVE' : 'INACTIVE'}</span>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); testConnection(conn) }} disabled={testing}
                    style={{
                      padding: '2px 8px', fontSize: 9, background: 'none', border: '1px solid var(--border-bright)',
                      color: 'var(--text-dim)', cursor: testing ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-mono)',
                    }}>
                    {testing ? 'TESTING...' : 'TEST'}
                  </button>
                </div>
                {testResult && selectedConn?.id === conn.id && (
                  <div style={{ marginTop: 8, padding: '6px 8px', background: testResult.success ? 'var(--green-dim)' : 'var(--red-dim)', border: `1px solid ${testResult.success ? 'var(--green)' : 'var(--red)'}`, fontSize: 9, color: testResult.success ? 'var(--green)' : 'var(--red)' }}>
                    {testResult.success ? `Connected — ${testResult.workflow_count} workflows` : testResult.error}
                  </div>
                )}
              </div>
            ))}
            {connections.length === 0 && (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-dim)', fontSize: 10, letterSpacing: '0.1em' }}>
                NO CONNECTIONS<br />Click "New Connection" to add
              </div>
            )}
          </div>
        </div>

        {/* Workflow Panel */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <div style={{ fontSize: 10, letterSpacing: '0.15em', color: 'var(--text-muted)', fontWeight: 600 }}>WORKFLOWS</div>
            <input
              type="text" placeholder="Search workflows..." value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{
                width: 200, height: 28, padding: '0 10px', fontSize: 10,
                background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                color: 'var(--text-primary)', fontFamily: 'var(--font-mono)',
              }}
            />
          </div>
          {loadingWorkflows ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>
              <Loader2 size={20} className="spin" style={{ marginBottom: 8 }} /><br />LOADING WORKFLOWS...
            </div>
          ) : !selectedConn ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 10, letterSpacing: '0.1em' }}>
              SELECT A CONNECTION<br />TO VIEW WORKFLOWS
            </div>
          ) : filteredWorkflows.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 10, letterSpacing: '0.1em' }}>
              NO WORKFLOWS FOUND
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {filteredWorkflows.map(wf => (
                <div key={wf.id} style={{
                  padding: '14px 16px', border: '1px solid var(--border-bright)',
                  background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', gap: 12,
                }}>
                  <div style={{
                    width: 32, height: 32, background: 'var(--accent-dim)', border: '1px solid var(--accent-border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <GitBranch size={14} style={{ color: 'var(--accent)' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{wf.name}</div>
                    <div style={{ display: 'flex', gap: 12, fontSize: 9, color: 'var(--text-dim)' }}>
                      <span>{wf.nodes_count} nodes</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <div style={{ width: 6, height: 6, borderRadius: '50%', background: wf.active ? 'var(--green)' : 'var(--text-dim)' }} />
                        {wf.active ? 'ACTIVE' : 'DRAFT'}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button style={{ padding: 6, color: wf.active ? 'var(--amber)' : 'var(--green)', background: 'none', border: '1px solid var(--border-bright)', cursor: 'pointer' }}>
                      {wf.active ? <Square size={12} /> : <Play size={12} />}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Connection Form Modal */}
      {showConnForm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        }} onClick={e => e.target === e.currentTarget && setShowConnForm(false)}>
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            padding: 24, width: 480, maxHeight: '80vh', overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>
                {editingConn ? 'EDIT CONNECTION' : 'NEW CONNECTION'}
              </div>
              <button onClick={() => setShowConnForm(false)} style={{ padding: 4, color: 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer' }}><X size={14} /></button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>NAME</label>
                <input value={connForm.name} onChange={e => setConnForm(f => ({ ...f, name: e.target.value }))}
                  style={{ width: '100%', height: 36, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>BASE URL</label>
                <input value={connForm.base_url} onChange={e => setConnForm(f => ({ ...f, base_url: e.target.value }))} placeholder="https://n8n.example.com"
                  style={{ width: '100%', height: 36, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>API KEY</label>
                <input value={connForm.api_key} onChange={e => setConnForm(f => ({ ...f, api_key: e.target.value }))} type="password" placeholder="Leave empty to keep existing"
                  style={{ width: '100%', height: 36, padding: '0 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)' }} />
              </div>
              <div style={{ display: 'flex', gap: 16 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={connForm.is_active} onChange={e => setConnForm(f => ({ ...f, is_active: e.target.checked }))}
                    style={{ width: 14, height: 14 }} />
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>ACTIVE</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={connForm.is_default} onChange={e => setConnForm(f => ({ ...f, is_default: e.target.checked }))}
                    style={{ width: 14, height: 14 }} />
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>DEFAULT</span>
                </label>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button onClick={() => setShowConnForm(false)} style={{
                  flex: 1, height: 36, border: '1px solid var(--border-bright)', background: 'transparent',
                  color: 'var(--text-muted)', fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}>CANCEL</button>
                <button onClick={submitConnection} style={{
                  flex: 1, height: 36, background: 'var(--accent)', border: '1px solid var(--accent-border)',
                  color: '#000', fontWeight: 700, fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}>{editingConn ? 'UPDATE' : 'CREATE'}</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AI Generator Modal */}
      {showGenerator && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        }} onClick={e => e.target === e.currentTarget && setShowGenerator(false)}>
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            padding: 24, width: 640, maxHeight: '85vh', overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.1em', color: 'var(--accent)' }}>
                <Zap size={14} style={{ marginRight: 8, verticalAlign: 'middle' }} />
                AI WORKFLOW GENERATOR
              </div>
              <button onClick={() => setShowGenerator(false)} style={{ padding: 4, color: 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer' }}><X size={14} /></button>
            </div>
            {!selectedConn ? (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--amber)', fontSize: 10, letterSpacing: '0.1em' }}>
                SELECT A CONNECTION FIRST
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>DESCRIBE YOUR WORKFLOW</label>
                  <textarea value={genDescription} onChange={e => setGenDescription(e.target.value)}
                    rows={4} placeholder="e.g., 每小时检查我的邮箱，如果有来自重要客户的邮件就发送 Slack 通知"
                    style={{
                      width: '100%', padding: '10px 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)', resize: 'vertical',
                    }} />
                </div>
                <button onClick={generateWorkflow} disabled={generating || !genDescription.trim()}
                  style={{
                    height: 36, background: generating ? 'var(--bg-elevated)' : 'var(--accent)',
                    border: '1px solid var(--accent-border)', color: generating ? 'var(--text-muted)' : '#000',
                    fontWeight: 700, fontSize: 10, letterSpacing: '0.1em', cursor: generating ? 'not-allowed' : 'pointer',
                    fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  }}>
                  {generating ? <><Loader2 size={11} className="spin" /> GENERATING...</> : <><Zap size={11} /> GENERATE WORKFLOW JSON</>}
                </button>
                {genError && (
                  <div style={{ padding: '10px 12px', background: 'var(--red-dim)', border: '1px solid var(--red)', fontSize: 10, color: 'var(--red)' }}>
                    ERROR: {genError}
                  </div>
                )}
                {generatedJson && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                      <label style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>GENERATED WORKFLOW JSON</label>
                      <span style={{ fontSize: 9, color: 'var(--accent)' }}>{generatedJson.name || 'Untitled'}</span>
                    </div>
                    <pre style={{
                      padding: 12, background: 'var(--bg-base)', border: '1px solid var(--border)',
                      fontSize: 10, color: 'var(--text-primary)', maxHeight: 300, overflow: 'auto',
                      fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                    }}>
                      {JSON.stringify(generatedJson, null, 2)}
                    </pre>
                    <button onClick={createWorkflowInN8N} disabled={creatingWorkflow}
                      style={{
                        marginTop: 12, height: 36, width: '100%', background: 'var(--green)',
                        border: '1px solid var(--green)', color: '#000', fontWeight: 700,
                        fontSize: 10, letterSpacing: '0.1em', cursor: creatingWorkflow ? 'not-allowed' : 'pointer',
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
      )}
    </div>
  )
}
