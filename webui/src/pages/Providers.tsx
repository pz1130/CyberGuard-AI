import { useState, useEffect, useMemo, useContext } from 'react'
import { api } from '../api/client'
import { Plus, Loader2, Search, X, RefreshCw, Zap, Settings2, Database } from 'lucide-react'
import { SearchContext } from '../context/SearchContext'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ModelInfo {
  name: string
  model_type: 'chat' | 'embedding' | 'rerank'
  capabilities?: { tools?: boolean | null; vision?: boolean | null; probed_at?: string } | null
}

interface Provider {
  id: number
  name: string
  provider_type: string
  base_url: string
  api_key?: string        // masked '******' from server, or empty
  models: ModelInfo[]
  is_active: boolean
  metadata_json?: Record<string, any>
  // derived
  _status?: 'ready' | 'partial' | 'unconfigured'
}

// ── Preset catalog (shown even before they're configured in DB) ───────────────

interface Preset {
  name: string
  provider_type: string
  base_url: string
  default_models: string[]
  key_placeholder: string
  color: string
}

const PRESETS: Preset[] = [
  { name: 'OpenAI',         provider_type: 'openai',     base_url: 'https://api.openai.com/v1',          default_models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],       key_placeholder: 'sk-...', color: '#10a37f' },
  { name: 'Anthropic',      provider_type: 'anthropic',  base_url: 'https://api.anthropic.com/v1',        default_models: ['claude-opus-4-7-2025', 'claude-sonnet-4-6'],   key_placeholder: 'sk-ant-...', color: '#d97706' },
  { name: 'Groq',           provider_type: 'openai',     base_url: 'https://api.groq.com/openai/v1',      default_models: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'], key_placeholder: 'gsk_...', color: '#f97316' },
  { name: 'OpenRouter',     provider_type: 'openai',     base_url: 'https://openrouter.ai/api/v1',        default_models: ['openai/gpt-4o', 'google/gemini-2.0-flash'],    key_placeholder: 'sk-or-...', color: '#8b5cf6' },
  { name: 'SiliconFlow',    provider_type: 'openai',     base_url: 'https://api.siliconflow.cn/v1',       default_models: ['Qwen/Qwen2.5-72B-Instruct', 'deepseek-ai/DeepSeek-V2.5'], key_placeholder: 'sk-...', color: '#06b6d4' },
  { name: 'Zhipu AI',       provider_type: 'openai',     base_url: 'https://open.bigmodel.cn/api/paas/v4', default_models: ['glm-4-plus', 'glm-4-flash'],                  key_placeholder: '...', color: '#3b82f6' },
  { name: 'Azure OpenAI',   provider_type: 'azure',      base_url: '',                                    default_models: ['gpt-4o', 'gpt-4o-mini'],                      key_placeholder: 'Azure API Key', color: '#0078d4' },
  { name: 'Ollama',         provider_type: 'openai',     base_url: 'http://localhost:11434/v1',           default_models: ['llama3.2', 'qwen2.5', 'deepseek-r1'],         key_placeholder: 'ollama', color: '#22c55e' },
  { name: 'LM Studio',      provider_type: 'openai',     base_url: 'http://localhost:1234/v1',            default_models: ['local-model'],                                key_placeholder: 'lm-studio', color: '#a855f7' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function providerStatus(p: Provider): 'ready' | 'partial' | 'unconfigured' {
  // api_key from server is '******' when set — treat that as configured
  const keyConfigured = !!(p.api_key)
  const hasModels = p.models && p.models.length > 0
  if (keyConfigured && hasModels) return 'ready'
  if (keyConfigured) return 'partial'
  return 'unconfigured'
}

const STATUS_COLOR = { ready: 'var(--accent)', partial: '#f59e0b', unconfigured: 'var(--text-dim)' }
const STATUS_LABEL = { ready: 'READY', partial: 'NO MODELS', unconfigured: 'NOT CONFIGURED' }

function Avatar({ name, color }: { name: string; color?: string }) {
  const letter = name.charAt(0).toUpperCase()
  const bg = color || '#374151'
  return (
    <div style={{
      width: 40, height: 40, borderRadius: 4, flexShrink: 0,
      background: `${bg}22`,
      border: `1.5px solid ${bg}66`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 18, fontWeight: 800, color: bg,
      fontFamily: 'var(--font-mono)',
    }}>
      {letter}
    </div>
  )
}

function StatusDot({ status }: { status: 'ready' | 'partial' | 'unconfigured' }) {
  const c = STATUS_COLOR[status]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontSize: 11, letterSpacing: '0.12em', color: c,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%', background: c,
        boxShadow: status === 'ready' ? `0 0 6px ${c}` : 'none',
      }} />
      {STATUS_LABEL[status]}
    </span>
  )
}

const inp: React.CSSProperties = {
  width: '100%', height: 38, padding: '0 12px',
  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.04em',
  fontFamily: 'var(--font-mono)', boxSizing: 'border-box',
}
const lbl = (text: string, sub?: string) => (
  <div style={{ marginBottom: 6 }}>
    <label style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)' }}>{text}</label>
    {sub && <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 8 }}>{sub}</span>}
  </div>
)

// ── Settings Modal — API Key + Base URL ───────────────────────────────────────

function SettingsModal({
  provider, preset, onClose, onSaved,
}: {
  provider?: Provider
  preset?: Preset
  onClose: () => void
  onSaved: () => void
}) {
  const isNew = !provider
  const [name, setName] = useState(provider?.name || preset?.name || '')
  const [type, setType] = useState(provider?.provider_type || preset?.provider_type || 'openai')
  const [baseUrl, setBaseUrl] = useState(provider?.base_url || preset?.base_url || '')
  const [apiKey, setApiKey] = useState('')
  const [preserveThink, setPreserveThink] = useState(!!provider?.metadata_json?.preserve_think)
  const [testing, setTesting] = useState(false)
  const [testMsg, setTestMsg] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const keyPlaceholder = preset?.key_placeholder || 'sk-...'

  const testConn = async () => {
    setTesting(true); setTestMsg(null)
    try {
      if (provider?.id) {
        const r = await api.testProvider(provider.id) as any
        setTestMsg({ ok: r.success, msg: r.error || (r.latency_ms ? `${r.latency_ms}ms` : 'Connected') })
      } else {
        // Live test before saving — directly hit the API
        const base = baseUrl.replace(/\/$/, '')
        const t0 = Date.now()
        try {
          const resp = await fetch(`${base}/models`, {
            headers: { Authorization: `Bearer ${apiKey}` },
          })
          const ms = Date.now() - t0
          setTestMsg({ ok: resp.ok, msg: resp.ok ? `Connected · ${ms}ms` : `HTTP ${resp.status}` })
        } catch (e: any) {
          setTestMsg({ ok: false, msg: e.message })
        }
      }
    } finally { setTesting(false) }
  }

  const save = async () => {
    if (!name) return
    setSaving(true)
    try {
      const payload: any = {
        name, provider_type: type, base_url: baseUrl,
        metadata_json: { preserve_think: preserveThink },
      }
      if (apiKey && apiKey !== '******') payload.api_key = apiKey
      if (provider?.id) {
        await api.updateProvider(String(provider.id), payload)
      } else {
        // New provider: pre-fill default models from preset
        payload.models = preset?.default_models?.map(m => ({ name: m, model_type: 'chat' })) || []
        await api.createProvider(payload)
      }
      onSaved()
    } catch (e: any) { alert(e.message) }
    finally { setSaving(false) }
  }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 460 }}>
        <ModalHeader
          icon={<Settings2 size={14} />}
          title={isNew ? (preset ? `ADD ${preset.name.toUpperCase()}` : 'NEW PROVIDER') : `SETTINGS · ${provider!.name.toUpperCase()}`}
          sub={isNew ? 'Configure API credentials' : 'Update provider credentials'}
          onClose={onClose}
        />
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {isNew && !preset && (
            <>
              {lbl('PROVIDER NAME')}
              <input value={name} onChange={e => setName(e.target.value)} placeholder="My Provider" style={inp} />
              {lbl('PROTOCOL TYPE')}
              <select value={type} onChange={e => setType(e.target.value)} style={{ ...inp, height: 38 }}>
                <option value="openai">OpenAI-Compatible</option>
                <option value="anthropic">Anthropic</option>
                <option value="azure">Azure OpenAI</option>
                <option value="openrouter">OpenRouter</option>
                <option value="custom">Custom</option>
              </select>
            </>
          )}
          {lbl('BASE URL', type === 'ollama' ? '本地 Ollama 服务地址' : '')}
          <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
            placeholder={preset?.base_url || 'https://api.example.com/v1'} style={inp} />

          {lbl('API KEY', provider?.api_key ? '已配置（输入新值以更新）' : '')}
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder={provider?.api_key ? '留空保持不变' : keyPlaceholder}
            style={inp}
          />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', border: '1px solid var(--border-bright)', background: 'var(--bg-base)' }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>保留 &lt;think&gt; 标签</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>适用于 DeepSeek-R1 / QwQ 等思维链模型</div>
            </div>
            <input type="checkbox" checked={preserveThink} onChange={e => setPreserveThink(e.target.checked)}
              style={{ width: 16, height: 16, accentColor: 'var(--accent)' }} />
          </div>

          {testMsg && (
            <div style={{
              padding: '8px 12px', border: `1px solid ${testMsg.ok ? 'var(--accent-border)' : 'rgba(248,113,113,0.3)'}`,
              background: 'var(--bg-base)', fontSize: 12,
              color: testMsg.ok ? 'var(--accent)' : '#f87171', fontFamily: 'var(--font-mono)',
            }}>
              {testMsg.ok ? '✓ ' : '✗ '}{testMsg.msg}
            </div>
          )}
        </div>
        <ModalFooter>
          <button onClick={testConn} disabled={testing || (!baseUrl && !provider)}
            style={{ padding: '0 14px', height: 38, border: '1px solid var(--border-bright)', background: 'transparent', color: testing ? 'var(--text-dim)' : 'var(--text-muted)', fontSize: 12, letterSpacing: '0.12em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
            {testing ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : 'TEST'}
          </button>
          <Spacer />
          <button onClick={onClose} style={{ padding: '0 14px', height: 38, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.12em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
            CANCEL
          </button>
          <button onClick={save} disabled={saving || !name}
            style={{ padding: '0 20px', height: 38, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 12, letterSpacing: '0.12em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
            {saving ? '...' : 'SAVE'}
          </button>
        </ModalFooter>
      </div>
    </Overlay>
  )
}

// ── Models Modal — manage per-provider models ─────────────────────────────────

function ModelsModal({ provider, onClose, onSaved }: { provider: Provider; onClose: () => void; onSaved: () => void }) {
  const [models, setModels] = useState<ModelInfo[]>(() => {
    if (!provider.models?.length) return []
    return provider.models.map(m => typeof m === 'string' ? { name: m, model_type: 'chat' as const } : m)
  })
  const [newName, setNewName] = useState('')
  const [newType, setNewType] = useState<'chat' | 'embedding' | 'rerank'>('chat')
  const [fetching, setFetching] = useState(false)
  const [fetchErr, setFetchErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testRes, setTestRes] = useState<Record<string, { ok: boolean; ms: number }>>({})
  const [probing, setProbing] = useState(false)

  const discover = async () => {
    if (!provider.base_url) { setFetchErr('No base URL configured'); return }
    setFetching(true); setFetchErr('')
    try {
      let ids: string[] = []
      if (provider.id) {
        // Saved provider: discover server-side with the stored (real) key. The key
        // is masked in the form, so a browser-side fetch would 401; the backend also
        // sidesteps provider CORS.
        const data = await api.discoverProviderModels(provider.id) as any
        ids = (data.models || []).map((m: any) => m.name || m.id).filter(Boolean)
      } else {
        // New provider not yet saved: use the key just typed into the form.
        const base = provider.base_url.replace(/\/$/, '')
        const resp = await fetch(`${base}/models`, {
          headers: provider.api_key ? { Authorization: `Bearer ${provider.api_key}` } : {},
        })
        if (!resp.ok) { setFetchErr(`HTTP ${resp.status}`); return }
        const data = await resp.json()
        if (Array.isArray(data.data)) ids = data.data.map((m: any) => m.id).filter(Boolean)
        else if (Array.isArray(data.models)) ids = data.models.map((m: any) => m.name || m.id).filter(Boolean)
      }
      if (!ids.length) { setFetchErr('No models returned by provider'); return }
      const discovered = ids.map(name => ({ name, model_type: 'chat' as const }))
      // Merge: keep existing type tags, add new ones
      const existing = Object.fromEntries(models.map(m => [m.name, m.model_type]))
      setModels(discovered.map(m => ({ name: m.name, model_type: existing[m.name] || 'chat' })))
    } catch (e: any) { setFetchErr(e.message) }
    finally { setFetching(false) }
  }

  const probe = async () => {
    if (!provider.id) { setFetchErr('保存 Provider 后才能探测能力'); return }
    setProbing(true); setFetchErr('')
    try {
      const data = await api.probeProviderModels(provider.id) as any
      const caps = Object.fromEntries((data.models || []).map((m: any) => [m.name, m.capabilities]))
      setModels(prev => prev.map(m => ({ ...m, capabilities: caps[m.name] ?? m.capabilities })))
    } catch (e: any) { setFetchErr(e.message) }
    finally { setProbing(false) }
  }

  const add = () => {
    if (!newName.trim() || models.some(m => m.name === newName.trim())) return
    setModels(prev => [...prev, { name: newName.trim(), model_type: newType }])
    setNewName('')
  }

  const remove = (name: string) => setModels(prev => prev.filter(m => m.name !== name))

  // Per-model verification status badge. Reads the verified/test_error fields that
  // the backend stamps onto ModelInfo (verified=true on successful test/probe or for
  // built-in presets; verified=false on test failure with error in test_error; missing
  // for legacy providers → "UNTESTED"). Mirrors the badge added in Chat.tsx (Task 5).
  const modelStatusBadge = (m: { verified?: boolean | null; test_error?: string | null }) => {
    if (m.verified === true) {
      return <span style={{ fontSize: 10, padding: '1px 6px', border: '1px solid var(--accent-border)', color: 'var(--accent)', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em', flexShrink: 0 }}>✓ VERIFIED</span>
    }
    if (m.verified === false) {
      return <span title={m.test_error || 'test failed'} style={{ fontSize: 10, padding: '1px 6px', border: '1px solid rgba(248,113,113,0.4)', color: '#f87171', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em', flexShrink: 0 }}>✗ FAILED</span>
    }
    return <span style={{ fontSize: 10, padding: '1px 6px', border: '1px solid var(--border)', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em', flexShrink: 0 }}>· UNTESTED</span>
  }

  const testModel = async (name: string) => {
    setTesting(name)
    const t0 = Date.now()
    try {
      // Route through the backend so it uses the stored (real) key — the form only
      // has the masked '******' key, and a browser-direct call also hits provider CORS.
      const r = await api.testProvider(provider.id, name) as any
      setTestRes(res => ({ ...res, [name]: { ok: !!r.success, ms: Date.now() - t0 } }))
    } catch {
      setTestRes(res => ({ ...res, [name]: { ok: false, ms: Date.now() - t0 } }))
    } finally { setTesting(null) }
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.updateProvider(String(provider.id), { ...provider, models, api_key: undefined })
      onSaved()
    } catch (e: any) { alert(e.message) }
    finally { setSaving(false) }
  }

  const typeColor = { chat: 'var(--accent)', embedding: '#06b6d4', rerank: '#f59e0b' }

  return (
    <Overlay onClose={onClose}>
      <div style={{ width: 520 }}>
        <ModalHeader
          icon={<Database size={14} />}
          title={`MODELS · ${provider.name.toUpperCase()}`}
          sub={`${models.length} model${models.length !== 1 ? 's' : ''} configured`}
          onClose={onClose}
        />
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Discover button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={discover} disabled={fetching}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 34, border: '1px solid var(--accent-border)', background: 'var(--accent-dim)', color: fetching ? 'var(--text-dim)' : 'var(--accent)', fontSize: 12, letterSpacing: '0.12em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
              {fetching ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap size={11} />}
              {fetching ? 'FETCHING...' : '自动发现模型'}
            </button>
            <button onClick={probe} disabled={probing || !models.length}
              title="对每个模型发极小请求，探测是否支持 tools / vision"
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 34, border: '1px solid var(--border-bright)', background: 'var(--bg-base)', color: (probing || !models.length) ? 'var(--text-dim)' : 'var(--text-muted)', fontSize: 12, letterSpacing: '0.12em', cursor: (probing || !models.length) ? 'default' : 'pointer', fontFamily: 'var(--font-mono)' }}>
              {probing ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Settings2 size={11} />}
              {probing ? 'PROBING...' : '探测能力'}
            </button>
          </div>
          {fetchErr && <div style={{ fontSize: 11, color: '#f87171' }}>{fetchErr}</div>}

          {/* Model list */}
          <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
            {models.length === 0 ? (
              <div style={{ padding: '24px 0', textAlign: 'center', fontSize: 12, color: 'var(--text-dim)' }}>
                暂无模型 — 点击"自动发现"或手动添加
              </div>
            ) : (
              models.map(m => {
                const r = testRes[m.name]
                return (
                  <div key={m.name} style={{ display: 'flex', alignItems: 'center', padding: '9px 14px', borderBottom: '1px solid var(--border)', gap: 10 }}>
                    {/* Type badge */}
                    <span style={{ fontSize: 10, padding: '2px 5px', border: `1px solid ${typeColor[m.model_type]}`, color: typeColor[m.model_type], fontFamily: 'var(--font-mono)', letterSpacing: '0.1em', whiteSpace: 'nowrap', flexShrink: 0 }}>
                      {m.model_type.toUpperCase()}
                    </span>
                    {/* Model name + verification badge */}
                    <span style={{ flex: 1, fontSize: 13, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {m.name}
                    </span>
                    {/* Verification status (✓ VERIFIED / ✗ FAILED / · UNTESTED) */}
                    {modelStatusBadge(m)}
                    {/* Capability badges (after probe) */}
                    {m.capabilities?.tools && (
                      <span title="支持 function-calling / tools" style={{ fontSize: 10, padding: '2px 5px', border: '1px solid #10b981', color: '#10b981', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em', flexShrink: 0 }}>🔧 TOOLS</span>
                    )}
                    {m.capabilities?.vision && (
                      <span title="支持图像输入 / vision" style={{ fontSize: 10, padding: '2px 5px', border: '1px solid #8b5cf6', color: '#8b5cf6', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em', flexShrink: 0 }}>👁 VISION</span>
                    )}
                    {/* Test result */}
                    {r && (
                      <span style={{ fontSize: 11, color: r.ok ? 'var(--accent)' : '#f87171', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                        {r.ok ? `✓ ${r.ms}ms` : '✗ FAILED'}
                      </span>
                    )}
                    {/* Type selector */}
                    <select
                      value={m.model_type}
                      onChange={e => setModels(prev => prev.map(x => x.name === m.name ? { ...x, model_type: e.target.value as any } : x))}
                      style={{ height: 24, padding: '0 4px', background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                      <option value="chat">chat</option>
                      <option value="embedding">embed</option>
                      <option value="rerank">rerank</option>
                    </select>
                    {/* Test button */}
                    <button onClick={() => testModel(m.name)} disabled={testing === m.name}
                      style={{ fontSize: 11, letterSpacing: '0.1em', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-mono)', padding: '0 4px', flexShrink: 0 }}>
                      {testing === m.name ? '…' : 'TEST'}
                    </button>
                    {/* Remove */}
                    <button onClick={() => remove(m.name)} style={{ color: '#f87171', background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', flexShrink: 0 }}>
                      <X size={11} />
                    </button>
                  </div>
                )
              })
            )}
          </div>

          {/* Add model row */}
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              value={newName} onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && add()}
              placeholder="模型名称，如 gpt-4o"
              style={{ flex: 1, height: 34, padding: '0 10px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)' }}
            />
            <select value={newType} onChange={e => setNewType(e.target.value as any)}
              style={{ width: 90, height: 34, padding: '0 6px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
              <option value="chat">chat</option>
              <option value="embedding">embed</option>
              <option value="rerank">rerank</option>
            </select>
            <button onClick={add} style={{ padding: '0 14px', height: 34, border: '1px solid var(--accent-border)', background: 'var(--accent-dim)', color: 'var(--accent)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
              + 添加
            </button>
          </div>
        </div>
        <ModalFooter>
          <button onClick={onClose} style={{ padding: '0 14px', height: 38, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.12em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>CANCEL</button>
          <button onClick={save} disabled={saving}
            style={{ padding: '0 20px', height: 38, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 12, letterSpacing: '0.12em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
            {saving ? '...' : 'SAVE MODELS'}
          </button>
        </ModalFooter>
      </div>
    </Overlay>
  )
}

// ── Provider Card ─────────────────────────────────────────────────────────────

function ProviderCard({
  provider,
  onSettings,
  onModels,
  onDelete,
}: {
  provider: Provider
  onSettings: () => void
  onModels: () => void
  onDelete: () => void
}) {
  const status = providerStatus(provider)
  const sc = STATUS_COLOR[status]
  const preset = PRESETS.find(p => p.name.toLowerCase() === provider.name.toLowerCase() || p.provider_type === provider.provider_type)
  const color = preset?.color || '#6b7280'
  const modelCount = provider.models?.length || 0

  return (
    <div data-item-id={provider.id} style={{
      padding: 18, background: 'var(--bg-surface)',
      border: '1px solid var(--border-bright)',
      borderLeft: `3px solid ${sc}`,
      display: 'flex', flexDirection: 'column', gap: 12,
    }}>
      {/* Top row: avatar + name + status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Avatar name={provider.name} color={color} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.06em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {provider.name}
          </div>
          <div style={{ marginTop: 3 }}>
            <StatusDot status={status} />
          </div>
        </div>
      </div>

      {/* Meta row */}
      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
        <span style={{ color: sc }}>{modelCount} MODEL{modelCount !== 1 ? 'S' : ''}</span>
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {provider.base_url || '(default endpoint)'}
        </span>
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
        <button onClick={onSettings}
          style={{ flex: 1, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
          <Settings2 size={11} /> SETTINGS
        </button>
        <button onClick={onModels}
          style={{ flex: 1, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, border: `1px solid ${status === 'unconfigured' ? 'var(--border)' : 'var(--accent-border)'}`, background: status === 'unconfigured' ? 'transparent' : 'var(--accent-dim)', color: status === 'unconfigured' ? 'var(--text-dim)' : 'var(--accent)', fontSize: 12, letterSpacing: '0.1em', cursor: status === 'unconfigured' ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-mono)' }}
          disabled={status === 'unconfigured'} title={status === 'unconfigured' ? '请先配置 API Key' : ''}>
          <Database size={11} /> MODELS
        </button>
        <button onClick={onDelete} style={{ width: 32, height: 32, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-dim)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <X size={11} />
        </button>
      </div>
    </div>
  )
}

// ── Unconfigured preset card ───────────────────────────────────────────────────

function PresetCard({ preset, onAdd }: { preset: Preset; onAdd: () => void }) {
  return (
    <div style={{
      padding: 18, background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderLeft: '3px solid var(--border)',
      display: 'flex', flexDirection: 'column', gap: 12,
      opacity: 0.7,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Avatar name={preset.name} color={preset.color} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>{preset.name}</div>
          <div style={{ marginTop: 3 }}><StatusDot status="unconfigured" /></div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {preset.base_url || 'Custom endpoint'}
      </div>
      <button onClick={onAdd}
        style={{ height: 32, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
        + 配置
      </button>
    </div>
  )
}

// ── Modal shell components ────────────────────────────────────────────────────

function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div onClick={e => e.target === e.currentTarget && onClose()} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 20 }}>
      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', width: '100%', maxWidth: 540, maxHeight: '90vh', overflow: 'auto' }}>
        {children}
      </div>
    </div>
  )
}

function ModalHeader({ icon, title, sub, onClose }: { icon: React.ReactNode; title: string; sub: string; onClose: () => void }) {
  return (
    <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ color: 'var(--accent)' }}>{icon}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{title}</div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{sub}</div>
      </div>
      <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: 4 }}>
        <X size={14} />
      </button>
    </div>
  )
}

function ModalFooter({ children }: { children: React.ReactNode }) {
  return <div style={{ padding: '14px 24px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>{children}</div>
}

function Spacer() { return <div style={{ flex: 1 }} /> }

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Providers() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [settingsTarget, setSettingsTarget] = useState<{ provider?: Provider; preset?: Preset } | null>(null)
  const [modelsTarget, setModelsTarget] = useState<Provider | null>(null)

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

  const load = async () => {
    try {
      const data = await api.getProviders() as any
      const list: any[] = data?.providers || data || []
      setProviders(list.map(p => ({
        ...p,
        models: (p.models || []).map((m: any) => typeof m === 'string' ? { name: m, model_type: 'chat' } : m),
      })))
    } catch { setProviders([]) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const del = async (p: Provider) => {
    if (!confirm(`删除 "${p.name}"？`)) return
    try { await api.deleteProvider(String(p.id)); load() } catch (e: any) { alert(e.message) }
  }

  // Presets not yet in DB
  const configuredNames = new Set(providers.map(p => p.name.toLowerCase()))
  const unconfiguredPresets = PRESETS.filter(p => !configuredNames.has(p.name.toLowerCase()))

  // Sort configured: ready > partial > unconfigured, then filter by search
  const sortedProviders = useMemo(() => {
    const order = { ready: 0, partial: 1, unconfigured: 2 }
    return [...providers]
      .map(p => ({ ...p, _status: providerStatus(p) as 'ready' | 'partial' | 'unconfigured' }))
      .sort((a, b) => order[a._status!] - order[b._status!])
      .filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))
  }, [providers, search])

  const filteredPresets = unconfiguredPresets.filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>AI INFRASTRUCTURE</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>AI PROVIDERS</h1>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={load} title="刷新" style={{ width: 36, height: 36, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <RefreshCw size={13} />
          </button>
          <button onClick={() => setSettingsTarget({})}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px', height: 36, background: 'var(--accent)', border: '1px solid var(--accent-border)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: 'pointer', fontFamily: 'var(--font-mono)', boxShadow: '0 0 16px rgba(0,255,65,0.15)' }}>
            <Plus size={13} /> 自定义 PROVIDER
          </button>
        </div>
      </div>

      {/* Search */}
      <div style={{ position: 'relative', marginBottom: 20 }}>
        <Search size={13} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-dim)' }} />
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="搜索 Provider…"
          style={{ width: '100%', height: 38, paddingLeft: 36, paddingRight: 12, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)', boxSizing: 'border-box' }}
        />
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '80px 0' }}>
          <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
        </div>
      ) : (
        <>
          {/* Configured providers */}
          {sortedProviders.length > 0 && (
            <div style={{ marginBottom: 28 }}>
              <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 12 }}>已配置 · {sortedProviders.length}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
                {sortedProviders.map(p => (
                  <ProviderCard
                    key={p.id}
                    provider={p}
                    onSettings={() => setSettingsTarget({ provider: p })}
                    onModels={() => setModelsTarget(p)}
                    onDelete={() => del(p)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Preset (unconfigured) providers */}
          {filteredPresets.length > 0 && (
            <div>
              <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 12 }}>可添加的 Provider · {filteredPresets.length}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
                {filteredPresets.map(preset => (
                  <PresetCard
                    key={preset.name}
                    preset={preset}
                    onAdd={() => setSettingsTarget({ preset })}
                  />
                ))}
              </div>
            </div>
          )}

          {sortedProviders.length === 0 && filteredPresets.length === 0 && (
            <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-dim)', fontSize: 13 }}>
              未找到匹配的 Provider
            </div>
          )}
        </>
      )}

      {/* Settings Modal */}
      {settingsTarget !== null && (
        <SettingsModal
          provider={settingsTarget.provider}
          preset={settingsTarget.preset}
          onClose={() => setSettingsTarget(null)}
          onSaved={() => { setSettingsTarget(null); load() }}
        />
      )}

      {/* Models Modal */}
      {modelsTarget && (
        <ModelsModal
          provider={modelsTarget}
          onClose={() => setModelsTarget(null)}
          onSaved={() => { setModelsTarget(null); load() }}
        />
      )}
    </div>
  )
}
