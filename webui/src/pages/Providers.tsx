import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Plus, Loader2, Plug, ArrowRight, Pencil, Trash, X } from 'lucide-react'

interface ModelInfo {
  name: string
  model_type: 'chat' | 'embedding' | 'rerank'
}

interface Provider {
  id?: number
  name: string
  provider_type: string
  base_url?: string
  api_key?: string
  models: ModelInfo[]
  is_active?: boolean
  metadata_json?: Record<string, any>
}

const TYPE_COLORS: Record<string, string> = {
  openai: 'var(--green)',
  anthropic: 'var(--amber)',
  azure: '#636f1f',
  groq: 'var(--cyan)',
  openrouter: 'var(--purple)',
  ollama: 'var(--green)',
  custom: 'var(--text-muted)',
}

const TYPE_LABELS: Record<string, string> = {
  openai: 'OPENAI COMPAT',
  anthropic: 'ANTHROPIC COMPAT',
  azure: 'AZURE OPENAI',
  groq: 'GROQ',
  openrouter: 'OPENROUTER',
  ollama: 'OLLAMA (LOCAL)',
  custom: 'CUSTOM PROVIDER',
}

export default function Providers() {
  const [items, setItems] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState<Provider>({
    name: '', provider_type: 'openai', base_url: '', api_key: '', models: [], metadata_json: { preserve_think: false },
  })
  // formModels is a list of ModelInfo for the model list editor
  const [formModels, setFormModels] = useState<ModelInfo[]>([])
  const [newModelName, setNewModelName] = useState('')
  const [newModelType, setNewModelType] = useState<'chat' | 'embedding' | 'rerank'>('chat')
  const [testingModelId, setTestingModelId] = useState<string | null>(null)
  const [modelTestResults, setModelTestResults] = useState<Record<string, { success: boolean; latency_ms?: number; error?: string }>>({})
  const [fetchingModels, setFetchingModels] = useState(false)
  const [modelsError, setModelsError] = useState('')
  const [testResult, setTestResult] = useState<Record<number, { success: boolean; latency_ms?: number; error?: string }>>({})
  const [testingProviderId, setTestingProviderId] = useState<number | null>(null)

  const load = async () => {
    try {
      const data = await api.getProviders() as { total: number; providers: Provider[] }
      setItems(data?.providers || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const submit = async () => {
    if (!form.name) return
    try {
      const payload = { ...form, models: formModels }
      if (editing) await api.updateProvider(String(editing), payload)
      else await api.createProvider(payload)
      setShowForm(false); setEditing(null)
      setForm({ name: '', provider_type: 'openai', base_url: '', api_key: '', models: [], metadata_json: { preserve_think: false } })
      setFormModels([])
      setNewModelName('')
      setNewModelType('chat')
      load()
    } catch (e: any) { alert(e.message) }
  }

  const addModel = () => {
    if (!newModelName.trim()) return
    if (formModels.some(m => m.name === newModelName.trim())) {
      setModelsError('Model already added')
      return
    }
    setFormModels(prev => [...prev, { name: newModelName.trim(), model_type: newModelType }])
    setNewModelName('')
    setModelsError('')
  }

  const removeModel = (name: string) => {
    setFormModels(prev => prev.filter(m => m.name !== name))
  }

  const convertLegacyModels = (models: any[]): ModelInfo[] => {
    if (!models || !models.length) return []
    if (typeof models[0] === 'string') {
      return (models as string[]).map(name => ({ name, model_type: 'chat' as const }))
    }
    return models as ModelInfo[]
  }

  const testConnection = async (id: number) => {
    setTestingProviderId(id)
    setTestResult(r => ({ ...r, [id]: { success: false } }))
    try {
      const result = await api.testProvider(id) as { success: boolean; latency_ms?: number; error?: string }
      setTestResult(r => ({ ...r, [id]: result }))
    } catch (e: any) {
      setTestResult(r => ({ ...r, [id]: { success: false, error: e.message } }))
    } finally { setTestingProviderId(null) }
  }

  const fetchModels = async (p: Provider) => {
    if (!p.base_url) {
      setModelsError('BASE URL is required to fetch models')
      return
    }
    setFetchingModels(true)
    setModelsError('')
    try {
      const base = p.base_url.replace(/\/$/, '')
      // Ollama: api_key can be empty or "ollama"
      const headers = p.api_key ? { 'Authorization': `Bearer ${p.api_key}` } : { 'Authorization': '' }
      // Try OpenAI-compatible /models endpoint first
      let modelIds: string[] = []
      try {
        const resp = await fetch(`${base}/models`, { headers })
        if (resp.ok) {
          const data = await resp.json()
          // OpenAI format: { data: [{ id: "gpt-4o" }, ...] }
          if (Array.isArray(data.data)) {
            modelIds = data.data.map((m: any) => m.id).filter(Boolean)
          }
          // Ollama format: { models: [{ name: "llama3.2:latest" }, ...] }
          else if (Array.isArray(data.models)) {
            modelIds = data.models.map((m: any) => m.name).filter(Boolean)
          }
        }
      } catch { /* try next */ }
      if (modelIds.length === 0) {
        setModelsError('No models found or request failed — is the provider running?')
      } else {
        const newModels: ModelInfo[] = modelIds.map(name => ({ name, model_type: 'chat' }))
        setFormModels(newModels)
        setForm(f => ({ ...f, models: newModels }))
        setModelsError('')
      }
    } catch (e: any) {
      setModelsError(e.message)
    } finally { setFetchingModels(false) }
  }

  const testModel = async (p: Provider, modelName: string) => {
    const key = `${p.id}:${modelName}`
    setTestingModelId(key)
    setModelTestResults(r => ({ ...r, [key]: { success: false } }))
    try {
      const base = (p.base_url || '').replace(/\/$/, '')
      const start = Date.now()
      const headers = {
        'Authorization': `Bearer ${p.api_key}`,
        'Content-Type': 'application/json',
      }
      let ok = false
      try {
        const resp = await fetch(`${base}/chat/completions`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            model: modelName,
            messages: [{ role: 'user', content: 'hi' }],
            max_tokens: 5,
          }),
        })
        ok = resp.ok
      } catch { ok = false }
      setModelTestResults(r => ({
        ...r,
        [key]: {
          success: ok,
          latency_ms: Date.now() - start,
          error: ok ? undefined : 'REQUEST FAILED',
        },
      }))
    } catch (e: any) {
      setModelTestResults(r => ({ ...r, [key]: { success: false, error: e.message } }))
    } finally { setTestingModelId(null) }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>AI INFRASTRUCTURE</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>PROVIDER CONFIG</h1>
        </div>
        <button
          onClick={() => { setShowForm(true); setEditing(null); setForm({ name: '', provider_type: 'openai', base_url: '', api_key: '', models: [], metadata_json: { preserve_think: false } }); setFormModels([]); setNewModelName(''); setNewModelType('chat'); setModelsError('') }}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '0 16px', height: 36,
            background: 'var(--accent)', border: '1px solid var(--accent-border)',
            color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.15em',
            cursor: 'pointer', fontFamily: 'var(--font-mono)',
            boxShadow: '0 0 16px rgba(0,255,65,0.15)',
          }}>
          <Plus size={13} /> NEW PROVIDER
        </button>
      </div>

      {/* Provider Cards Grid */}
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 0' }}>
          <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16, marginBottom: 40 }}>
          {items.map(p => {
            const r = testResult[p.id!]
            const tc = r?.success ? 'var(--green)' : r?.error ? 'var(--red)' : 'var(--amber)'
            return (
              <div key={p.id} style={{
                padding: 20,
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-bright)',
                borderTop: `2px solid ${tc}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{
                      width: 36, height: 36,
                      border: '1px solid var(--border-bright)',
                      background: 'var(--bg-base)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: TYPE_COLORS[p.provider_type] || 'var(--text-muted)',
                    }}>
                      <Plug size={14} />
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>{p.name}</div>
                      <div style={{ fontSize: 9, color: tc, letterSpacing: '0.1em', marginTop: 2 }}>
                        {r?.success ? `CONNECTED · ${r.latency_ms}ms` : r?.error ? 'CONNECTION FAILED' : 'TEST PENDING'}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => { setEditing(p.id!); setForm({ ...p, models: convertLegacyModels(p.models), metadata_json: { preserve_think: !!p.metadata_json?.preserve_think } }); setFormModels(convertLegacyModels(p.models)); setShowForm(true) }}
                      style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      <Pencil size={12} />
                    </button>
                    <button onClick={async () => { if (!confirm(`Delete provider "${p.name}"?`)) return; try { await api.deleteProvider(String(p.id!)); load() } catch (e: any) { alert(e.message) } }}
                      style={{ padding: 4, color: 'var(--red)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      <Trash size={12} />
                    </button>
                  </div>
                </div>

                <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', marginBottom: 8, letterSpacing: '0.05em' }}>
                  {p.base_url || '(default endpoint)'}
                </div>

                {/* Models list */}
                {p.models && p.models.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 9, letterSpacing: '0.15em', color: 'var(--text-muted)', marginBottom: 6 }}>MODELS</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {p.models.map(m => {
                        const modelInfo = typeof m === 'string' ? { name: m, model_type: 'chat' as const } : m
                        const key = `${p.id}:${modelInfo.name}`
                        const mr = modelTestResults[key]
                        const mc = mr?.success ? 'var(--green)' : mr?.error ? 'var(--red)' : 'var(--text-muted)'
                        const typeBadgeColor = modelInfo.model_type === 'embedding' ? 'var(--cyan)' : modelInfo.model_type === 'rerank' ? 'var(--amber)' : 'var(--text-dim)'
                        return (
                          <div key={modelInfo.name} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px 6px', border: `1px solid ${mc}`, background: 'var(--bg-base)', fontSize: 9 }}>
                            <span style={{ color: typeBadgeColor, fontSize: 8, fontFamily: 'var(--font-mono)' }}>{modelInfo.model_type.toUpperCase()}</span>
                            <span style={{ color: mc, fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>{modelInfo.name}</span>
                            {mr && (
                              <span style={{ color: mc, fontSize: 8 }}>{mr.latency_ms}ms</span>
                            )}
                            <button
                              onClick={() => testModel(p, modelInfo.name)}
                              disabled={testingModelId === key}
                              style={{
                                background: 'none', border: 'none', cursor: testingModelId === key ? 'not-allowed' : 'pointer',
                                color: mc, fontSize: 8, letterSpacing: '0.1em', padding: '0 0 0 4px',
                              }}>
                              {testingModelId === key ? '...' : 'TEST'}
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
                  <div style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    border: '1px solid var(--border)',
                    fontSize: 9, letterSpacing: '0.15em', color: TYPE_COLORS[p.provider_type] || 'var(--text-muted)',
                    background: 'var(--bg-base)',
                  }}>
                    {TYPE_LABELS[p.provider_type] || p.provider_type}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => { setEditing(p.id!); setForm({ ...p, models: convertLegacyModels(p.models), metadata_json: { preserve_think: !!p.metadata_json?.preserve_think } }); setFormModels(convertLegacyModels(p.models)); setShowForm(true) }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '0 8px', height: 26,
                        border: '1px solid var(--border-bright)',
                        background: 'transparent', color: 'var(--text-muted)',
                        fontSize: 9, letterSpacing: '0.1em', cursor: 'pointer',
                        fontFamily: 'var(--font-mono)',
                      }}>
                      EDIT
                    </button>
                    <button
                      onClick={() => testConnection(p.id!)}
                      disabled={testingProviderId === p.id}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '0 10px', height: 28,
                        border: '1px solid var(--border-bright)',
                        background: testingProviderId === p.id ? 'var(--bg-elevated)' : 'transparent',
                        color: testingProviderId === p.id ? 'var(--text-dim)' : 'var(--accent)',
                        fontSize: 10, letterSpacing: '0.1em', cursor: testingProviderId === p.id ? 'not-allowed' : 'pointer',
                        fontFamily: 'var(--font-mono)', transition: 'all 0.15s',
                      }}>
                      {testingProviderId === p.id ? 'TESTING...' : 'TEST CONNECTION'}
                    </button>
                  </div>
                </div>

                {r?.error && (
                  <div style={{ marginTop: 10, padding: '8px 10px', background: 'var(--red-dim)', border: '1px solid rgba(255,59,48,0.2)', fontSize: 10, color: 'var(--red)', letterSpacing: '0.05em' }}>
                    {r.error}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Model Routing Table */}
      <div style={{ marginTop: 32 }}>
        <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 12 }}>ROUTING LOGIC</div>
        <h2 style={{ fontSize: 14, fontWeight: 600, letterSpacing: '0.1em', color: 'var(--text-primary)', marginBottom: 16 }}>MODEL ROUTING TABLE</h2>
        <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-bright)' }}>
                {['AGENT', 'CURRENT PROVIDER', 'AVAILABLE MODELS', 'ACTION'].map((h, i) => (
                  <th key={i} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[{ agent: 'MASTER AGENT', provider: 'GROK API (xAI)', models: 'grok-3, grok-3-mini' }, { agent: 'THREAT INTEL (OPENCLAW)', provider: 'QWEN TUNING', models: 'qwen-plus, qwen-turbo' }, { agent: 'LOG ANALYZER (HERMES)', provider: 'OLLAMA (LOCAL)', models: 'llama3.1, bge-m3' }].map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-primary)', letterSpacing: '0.05em' }}>{row.agent}</td>
                  <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--green)', letterSpacing: '0.05em' }}>{row.provider}</td>
                  <td style={{ padding: '14px 16px', fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{row.models}</td>
                  <td style={{ padding: '14px 16px' }}>
                    <button style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      fontSize: 9, letterSpacing: '0.1em', color: 'var(--accent)', cursor: 'pointer',
                      background: 'none', border: 'none', padding: 0,
                    }}>
                      RECONFIGURE <ArrowRight size={10} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
          onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div style={{
            width: 520, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            padding: 32,
          }}>
            <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 16, marginBottom: 24 }}>
              <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>CONFIGURATION</div>
              <h3 style={{ fontSize: 16, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{editing ? 'EDIT PROVIDER' : 'NEW PROVIDER'}</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>PROVIDER NAME</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. Grok API"
                  style={{
                    width: '100%', height: 38, padding: '0 12px',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                    fontFamily: 'var(--font-mono)',
                  }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>TYPE</label>
                  <select value={form.provider_type} onChange={e => setForm(f => ({ ...f, provider_type: e.target.value }))}
                    style={{
                      width: '100%', height: 38, padding: '0 12px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)',
                    }}>
                    <option value="openai">OPENAI COMPAT</option>
                    <option value="anthropic">ANTHROPIC COMPAT</option>
                    <option value="azure">AZURE OPENAI</option>
                    <option value="groq">GROQ</option>
                    <option value="openrouter">OPENROUTER</option>
                    <option value="ollama">OLLAMA (LOCAL)</option>
                    <option value="custom">CUSTOM PROVIDER</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>BASE URL</label>
                  <input value={form.base_url || ''} onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
                    placeholder="https://api.x.ai/v1"
                    style={{
                      width: '100%', height: 38, padding: '0 12px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                      fontFamily: 'var(--font-mono)',
                    }} />
                </div>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>API KEY</label>
                <input type="password" value={form.api_key || ''} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                  placeholder="sk-..."
                  style={{
                    width: '100%', height: 38, padding: '0 12px',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
                    fontFamily: 'var(--font-mono)',
                  }} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', border: '1px solid var(--border-bright)', background: 'var(--bg-base)' }}>
                <div>
                  <div style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>PRESERVE THINK TAGS</div>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 2 }}>Keep provider `&lt;think&gt;...&lt;/think&gt;` content in chat output</div>
                </div>
                <input
                  type="checkbox"
                  checked={!!form.metadata_json?.preserve_think}
                  onChange={e => setForm(f => ({ ...f, metadata_json: { ...(f.metadata_json || {}), preserve_think: e.target.checked } }))}
                />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>MODELS</label>
                  <button
                    onClick={() => fetchModels(form)}
                    disabled={fetchingModels || !form.base_url}
                    title="Fetch models from provider API"
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '0 8px', height: 26,
                      border: '1px solid var(--accent-border)',
                      background: fetchingModels ? 'var(--bg-elevated)' : 'var(--accent-dim)',
                      color: fetchingModels ? 'var(--text-dim)' : 'var(--accent)',
                      fontSize: 9, letterSpacing: '0.1em', cursor: fetchingModels ? 'not-allowed' : 'pointer',
                      fontFamily: 'var(--font-mono)',
                    }}>
                    {fetchingModels ? 'FETCHING...' : '⬡ FETCH MODELS'}
                  </button>
                </div>
                {/* Added models list */}
                {formModels.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                    {formModels.map(m => (
                      <div key={m.name} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '3px 8px', border: '1px solid var(--border-bright)', background: 'var(--bg-base)', fontSize: 9 }}>
                        <span style={{ color: m.model_type === 'embedding' ? 'var(--cyan)' : m.model_type === 'rerank' ? 'var(--amber)' : 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: 8 }}>{m.model_type.toUpperCase()}</span>
                        <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{m.name}</span>
                        <button onClick={() => removeModel(m.name)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: 0, display: 'flex' }}><X size={10} /></button>
                      </div>
                    ))}
                  </div>
                )}
                {/* Add model row */}
                <div style={{ display: 'flex', gap: 6 }}>
                  <input value={newModelName} onChange={e => setNewModelName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addModel()}
                    placeholder="model name"
                    style={{
                      flex: 1, height: 32, padding: '0 8px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)',
                    }} />
                  <select value={newModelType} onChange={e => setNewModelType(e.target.value as 'chat' | 'embedding' | 'rerank')}
                    style={{
                      width: 110, height: 32, padding: '0 6px',
                      background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                      color: 'var(--text-primary)', fontSize: 10, fontFamily: 'var(--font-mono)',
                    }}>
                    <option value="chat">CHAT</option>
                    <option value="embedding">EMBEDDING</option>
                    <option value="rerank">RERANK</option>
                  </select>
                  <button onClick={addModel} style={{
                    padding: '0 10px', height: 32,
                    border: '1px solid var(--accent-border)',
                    background: 'var(--accent-dim)', color: 'var(--accent)',
                    fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                  }}>+ ADD</button>
                </div>
                {modelsError && (
                  <div style={{ marginTop: 6, fontSize: 9, color: 'var(--red)', letterSpacing: '0.05em' }}>{modelsError}</div>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 28 }}>
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
                {editing ? 'SAVE CHANGES' : 'CREATE PROVIDER'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
