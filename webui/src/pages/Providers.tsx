import { useState, useEffect, useMemo, useContext, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Plus, Loader2, Search, X, RefreshCw, Zap, Settings2, Database } from 'lucide-react'
import { SearchContext } from '../context/search'
import { errorMessage } from '../lib/errorMessage'
import { unwrapList } from '../lib/unwrapList'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ModelInfo {
  name: string
  model_type: 'chat' | 'embedding' | 'rerank'
  capabilities?: { tools?: boolean | null; vision?: boolean | null; probed_at?: string } | null
  // Verification status — stamped by the backend (/providers/test,
  // /providers/{id}/models/probe) and seeded onto built-in presets.
  verified?: boolean | null
  last_tested_at?: string | null
  test_error?: string | null
  input_price_per_million?: number | null
  output_price_per_million?: number | null
}

interface Provider {
  id: number
  name: string
  provider_type: string
  base_url: string
  api_key?: string        // masked '******' from server, or empty
  models: ModelInfo[]
  is_active: boolean
  metadata_json?: Record<string, unknown>
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
  { name: 'Bailian (阿里云百炼)', provider_type: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', default_models: ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwq-plus'], key_placeholder: 'sk-...', color: '#ff6a00' },
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

// ── Settings Modal — API Key + Base URL ───────────────────────────────────────

function SettingsModal({
  provider, preset, onClose, onSaved,
}: {
  provider?: Provider
  preset?: Preset
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const isNew = !provider
  const [name, setName] = useState(provider?.name || preset?.name || '')
  const [type, setType] = useState(provider?.provider_type || preset?.provider_type || 'openai')
  const [baseUrl, setBaseUrl] = useState(provider?.base_url || preset?.base_url || '')
  const [apiKey, setApiKey] = useState('')
  const [preserveThink, setPreserveThink] = useState(!!provider?.metadata_json?.preserve_think)
  const [groupId, setGroupId] = useState(String(provider?.metadata_json?.group_id || provider?.metadata_json?.GroupId || ''))
  const [testing, setTesting] = useState(false)
  const [testMsg, setTestMsg] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const keyPlaceholder = preset?.key_placeholder || 'sk-...'
  const isMinimax = /minimax/i.test(baseUrl) || /minimax/i.test(name)

  const testConn = async () => {
    setTesting(true); setTestMsg(null)
    try {
      if (provider?.id) {
        const r = await api.testProvider(provider.id) as { success?: boolean; error?: string; latency_ms?: number }
        setTestMsg({ ok: !!r.success, msg: r.error || (r.latency_ms ? `${r.latency_ms}ms` : 'Connected') })
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
        } catch (e: unknown) {
          setTestMsg({ ok: false, msg: errorMessage(e) })
        }
      }
    } finally { setTesting(false) }
  }

  const save = async () => {
    if (!name) return
    setSaving(true)
    try {
      const metadata_json: Record<string, unknown> = {
        ...(provider?.metadata_json || {}),
        preserve_think: preserveThink,
      }
      if (isMinimax) {
        if (groupId.trim()) metadata_json.group_id = groupId.trim()
        else delete metadata_json.group_id
      }
      const payload: Record<string, unknown> = {
        name, provider_type: type, base_url: baseUrl,
        metadata_json,
      }
      if (apiKey && apiKey !== '******') payload.api_key = apiKey
      if (provider?.id) {
        await api.updateProvider(String(provider.id), payload)
      } else {
        // New provider: pre-fill default models from preset. MiniMax chat
        // models are OpenAI-compatible; embo-01 is the native embedding model.
        const chatModels = (preset?.default_models || []).map(m => ({ name: m, model_type: 'chat' as const }))
        const embeddingModels = isMinimax ? [{ name: 'embo-01', model_type: 'embedding' as const }] : []
        payload.models = [...chatModels, ...embeddingModels]
        await api.createProvider(payload)
      }
      onSaved()
    } catch (e: unknown) { alert(errorMessage(e)) }
    finally { setSaving(false) }
  }

  return (
    <Modal
      title={isNew ? (preset ? `ADD ${preset.name.toUpperCase()}` : 'NEW PROVIDER') : `SETTINGS · ${provider!.name.toUpperCase()}`}
      eyebrow={isNew ? 'Configure API credentials' : 'Update provider credentials'}
      onClose={onClose}
      width={460}
      footer={
        <>
          <button
            onClick={testConn}
            disabled={testing || (!baseUrl && !provider)}
            className="btn btn-secondary"
            style={{ height: 36, fontSize: 12, letterSpacing: '0.12em' }}
          >
            {testing ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : 'TEST'}
          </button>
          <div style={{ flex: 1 }} />
          <button
            onClick={onClose}
            className="btn btn-secondary"
            style={{ height: 36, fontSize: 12, letterSpacing: '0.12em' }}
          >
            CANCEL
          </button>
          <button
            onClick={save}
            disabled={saving || !name}
            className="btn btn-primary"
            style={{ height: 36, fontSize: 12, letterSpacing: '0.12em', paddingLeft: 20, paddingRight: 20 }}
          >
            {saving ? '...' : 'SAVE'}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {isNew && !preset && (
          <>
            <div>
              <label className="form-label">PROVIDER NAME</label>
              <input className="form-input" value={name} onChange={e => setName(e.target.value)} placeholder="My Provider" />
            </div>
            <div>
              <label className="form-label">PROTOCOL TYPE</label>
              <select className="form-input" value={type} onChange={e => setType(e.target.value)} style={{ height: 38 }}>
                <option value="openai">OpenAI-Compatible</option>
                <option value="anthropic">Anthropic</option>
                <option value="azure">Azure OpenAI</option>
                <option value="openrouter">OpenRouter</option>
                <option value="custom">Custom</option>
              </select>
            </div>
          </>
        )}

        <div>
          <label className="form-label">
            BASE URL
            {type === 'ollama' && <span style={{ marginLeft: 8, color: 'var(--text-dim)' }}>{t('providers.localOllama')}</span>}
          </label>
          <input
            className="form-input"
            value={baseUrl}
            onChange={e => setBaseUrl(e.target.value)}
            placeholder={preset?.base_url || 'https://api.example.com/v1'}
          />
        </div>

        <div>
          <label className="form-label">
            API KEY
            {provider?.api_key && <span style={{ marginLeft: 8, color: 'var(--text-dim)' }}>{t('providers.configuredUpdate')}</span>}
          </label>
          <input
            className="form-input"
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder={provider?.api_key ? t('providers.leaveBlank') : keyPlaceholder}
          />
        </div>

        {isMinimax && (
          <div>
            <label className="form-label">{t('providers.groupId')}</label>
            <input
              className="form-input"
              value={groupId}
              onChange={e => setGroupId(e.target.value)}
              placeholder="1234567890"
            />
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>{t('providers.groupIdHint')}</div>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', border: '1px solid var(--border-bright)', background: 'var(--bg-base)', borderRadius: 'var(--radius-md)' }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>{t('providers.keepThink')}</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{t('providers.forThinkingModels')}</div>
          </div>
          <input type="checkbox" checked={preserveThink} onChange={e => setPreserveThink(e.target.checked)} style={{ width: 16, height: 16, accentColor: 'var(--accent)' }} />
        </div>

        {testMsg && (
          <div style={{
            padding: '8px 12px',
            border: `1px solid ${testMsg.ok ? 'var(--accent-border)' : 'rgba(248,113,113,0.3)'}`,
            background: 'var(--bg-base)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 12,
            color: testMsg.ok ? 'var(--accent)' : '#f87171',
          }}>
            {testMsg.ok ? '✓ ' : '✗ '}{testMsg.msg}
          </div>
        )}
      </div>
    </Modal>
  )
}

// ── Models Modal — manage per-provider models ─────────────────────────────────

function ModelsModal({ provider, onClose, onSaved }: { provider: Provider; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation()
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
      let discovered: ModelInfo[] = []
      if (provider.id) {
        // Saved provider: discover server-side with the stored (real) key. The key
        // is masked in the form, so a browser-side fetch would 401; the backend also
        // sidesteps provider CORS. The backend classifies embedding names and
        // backfills MiniMax embo-01.
        const data = await api.discoverProviderModels(provider.id) as {
          models?: Array<{ name?: string; id?: string; model_type?: ModelInfo['model_type'] }>
        }
        discovered = (data.models || [])
          .map(m => ({
            name: m.name || m.id || '',
            model_type: (m.model_type || 'chat') as ModelInfo['model_type'],
          }))
          .filter((m: ModelInfo) => m.name)
      } else {
        // New provider not yet saved: use the key just typed into the form.
        const base = provider.base_url.replace(/\/$/, '')
        const resp = await fetch(`${base}/models`, {
          headers: provider.api_key ? { Authorization: `Bearer ${provider.api_key}` } : {},
        })
        if (!resp.ok) { setFetchErr(`HTTP ${resp.status}`); return }
        const data: unknown = await resp.json()
        let ids: string[] = []
        if (data && typeof data === 'object') {
          const rec = data as Record<string, unknown>
          if (Array.isArray(rec.data)) {
            ids = rec.data.map(m => (m && typeof m === 'object' && 'id' in m ? String((m as { id?: string }).id || '') : '')).filter(Boolean)
          } else if (Array.isArray(rec.models)) {
            ids = rec.models.map(m => {
              if (!m || typeof m !== 'object') return ''
              const row = m as { name?: string; id?: string }
              return row.name || row.id || ''
            }).filter(Boolean)
          }
        }
        discovered = ids.map(name => ({ name, model_type: 'chat' as const }))
      }
      if (!discovered.length) { setFetchErr('No models returned by provider'); return }
      const existing = Object.fromEntries(models.map(m => [m.name, m]))
      const merged = discovered.map(m => existing[m.name] ? { ...m, ...existing[m.name], name: m.name, model_type: existing[m.name].model_type || m.model_type } : m)
      const preserved = models.filter(m => m.model_type !== 'chat' && !merged.some(x => x.name === m.name))
      setModels([...merged, ...preserved])
    } catch (e: unknown) { setFetchErr(errorMessage(e)) }
    finally { setFetching(false) }
  }

  const probe = async () => {
    if (!provider.id) { setFetchErr(t('providers.saveToProbe')); return }
    setProbing(true); setFetchErr('')
    try {
      const data = await api.probeProviderModels(provider.id) as {
        models?: Array<{ name: string; capabilities?: ModelInfo['capabilities'] }>
      }
      const caps = Object.fromEntries((data.models || []).map(m => [m.name, m.capabilities]))
      setModels(prev => prev.map(m => ({ ...m, capabilities: caps[m.name] ?? m.capabilities })))
    } catch (e: unknown) { setFetchErr(errorMessage(e)) }
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
  // for legacy providers → "UNTESTED"). Companion to the verified-only filter in
  // Chat.tsx (Task 5) — same data, opposite consumer: this page shows *why* a model
  // is or isn't verified, the chat dropdown only consumes the verified ones.
  const modelStatusBadge = (m: ModelInfo) => {
    if (m.verified === true) {
      return <span style={{ fontSize: 10, padding: '1px 6px', border: '1px solid var(--accent-border)', color: 'var(--accent)', letterSpacing: '0.05em', flexShrink: 0 }}>✓ VERIFIED</span>
    }
    if (m.verified === false) {
      return <span title={m.test_error || 'test failed'} style={{ fontSize: 10, padding: '1px 6px', border: '1px solid rgba(248,113,113,0.4)', color: '#f87171', letterSpacing: '0.05em', flexShrink: 0 }}>✗ FAILED</span>
    }
    return <span style={{ fontSize: 10, padding: '1px 6px', border: '1px solid var(--border)', color: 'var(--text-dim)', letterSpacing: '0.05em', flexShrink: 0 }}>· UNTESTED</span>
  }

  const testModel = async (name: string) => {
    setTesting(name)
    const t0 = Date.now()
    try {
      // Route through the backend so it uses the stored (real) key — the form only
      // has the masked '******' key, and a browser-direct call also hits provider CORS.
      const r = await api.testProvider(provider.id, name) as { success?: boolean; error?: string }
      const ok = !!r.success
      const err = r.error || null
      setTestRes(res => ({ ...res, [name]: { ok, ms: Date.now() - t0, err } }))
      // Mirror the backend stamp locally so the per-model badge updates
      // without waiting for a full reload (the modal is otherwise a stale
      // snapshot of provider.models). The next onSaved() will reconcile
      // any drift with the server's authoritative state.
      setModels(prev => prev.map(m => m.name === name ? {
        ...m,
        verified: ok,
        last_tested_at: new Date().toISOString(),
        test_error: ok ? null : (err || 'test failed'),
      } : m))
    } catch (e: unknown) {
      setTestRes(res => ({ ...res, [name]: { ok: false, ms: Date.now() - t0, err: errorMessage(e) || 'request failed' } }))
      setModels(prev => prev.map(m => m.name === name ? {
        ...m,
        verified: false,
        last_tested_at: new Date().toISOString(),
        test_error: errorMessage(e) || 'request failed',
      } : m))
    } finally { setTesting(null) }
  }

  const save = async () => {
    const isMinimax = /minimax/i.test(provider.base_url || '') || /minimax/i.test(provider.name)
    if (isMinimax) {
      const bad = models.filter(m => m.model_type === 'embedding' && !/embed|embo/i.test(m.name))
      if (bad.length) {
        alert(t('providers.minimaxChatNotEmbed', { name: bad[0].name }))
        return
      }
    }
    setSaving(true)
    try {
      await api.updateProvider(String(provider.id), { ...provider, models, api_key: undefined })
      onSaved()
    } catch (e: unknown) { alert(errorMessage(e)) }
    finally { setSaving(false) }
  }

  const typeColor = { chat: 'var(--accent)', embedding: '#06b6d4', rerank: '#f59e0b' }

  return (
    <Modal
      title={`MODELS · ${provider.name.toUpperCase()}`}
      eyebrow={`${models.length} model${models.length !== 1 ? 's' : ''} configured`}
      onClose={onClose}
      width={720}
      footer={
        <>
          <button
            onClick={onClose}
            className="btn btn-secondary"
            style={{ height: 36, fontSize: 12, letterSpacing: '0.12em' }}
          >
            CANCEL
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="btn btn-primary"
            style={{ height: 36, fontSize: 12, letterSpacing: '0.12em', paddingLeft: 20, paddingRight: 20 }}
          >
            {saving ? '...' : 'SAVE MODELS'}
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Discover / Probe toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={discover}
            disabled={fetching}
            className="btn"
            style={{
              height: 34,
              border: '1px solid var(--accent-border)',
              background: 'var(--accent-dim)',
              color: fetching ? 'var(--text-dim)' : 'var(--accent)',
              fontSize: 12,
              letterSpacing: '0.12em',
            }}
          >
            {fetching ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap size={11} />}
            {fetching ? t('providers.fetching') : t('providers.autoDiscover')}
          </button>
          <button
            onClick={probe}
            disabled={probing || !models.length}
            title={t('providers.probeHelp')}
            className="btn btn-secondary"
            style={{ height: 34, fontSize: 12, letterSpacing: '0.12em' }}
          >
            {probing ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Settings2 size={11} />}
            {probing ? t('providers.probing') : t('providers.probeBtn')}
          </button>
        </div>
        {fetchErr && <div style={{ fontSize: 11, color: '#f87171' }}>{fetchErr}</div>}
        {(/minimax/i.test(provider.base_url || '') || /minimax/i.test(provider.name)) && (
          <div style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.02em' }}>
            {t('providers.minimaxEmbedHint')}
          </div>
        )}

        {/* Model list */}
        <div style={{ border: '1px solid var(--border-bright)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
          {models.length === 0 ? (
            <div style={{ padding: '24px 0', textAlign: 'center', fontSize: 12, color: 'var(--text-dim)' }}>
              {t('providers.noModels')}
            </div>
          ) : (
            models.map(m => {
              const r = testRes[m.name]
              return (
                <div key={m.name} style={{ display: 'flex', flexDirection: 'column', padding: '9px 14px', borderBottom: '1px solid var(--border)', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
                  {/* Type badge */}
                  <span style={{ fontSize: 10, padding: '2px 5px', border: `1px solid ${typeColor[m.model_type]}`, color: typeColor[m.model_type], letterSpacing: '0.1em', whiteSpace: 'nowrap', flexShrink: 0 }}>
                    {m.model_type.toUpperCase()}
                  </span>
                  {/* Model name + verification badge */}
                  <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {m.name}
                  </span>
                  {/* Verification status (✓ VERIFIED / ✗ FAILED / · UNTESTED) */}
                  {modelStatusBadge(m)}
                  {/* Capability badges (after probe) */}
                  {m.capabilities?.tools && (
                    <span title={t('providers.toolsCap')} style={{ fontSize: 10, padding: '2px 5px', border: '1px solid #10b981', color: '#10b981', letterSpacing: '0.05em', flexShrink: 0 }}>🔧 TOOLS</span>
                  )}
                  {m.capabilities?.vision && (
                    <span title={t('providers.visionCap')} style={{ fontSize: 10, padding: '2px 5px', border: '1px solid #8b5cf6', color: '#8b5cf6', letterSpacing: '0.05em', flexShrink: 0 }}>👁 VISION</span>
                  )}
                  {/* Test result */}
                  {r && (
                    <span style={{ fontSize: 11, color: r.ok ? 'var(--accent)' : '#f87171', flexShrink: 0 }}>
                      {r.ok ? `✓ ${r.ms}ms` : '✗ FAILED'}
                    </span>
                  )}
                  {/* Type selector */}
                  <select
                    value={m.model_type}
                    onChange={e => setModels(prev => prev.map(x => x.name === m.name ? { ...x, model_type: e.target.value as ModelInfo['model_type'] } : x))}
                    style={{ height: 24, padding: '0 4px', background: 'var(--bg-base)', border: '1px solid var(--border)', color: 'var(--text-muted)', fontSize: 11, flexShrink: 0 }}
                  >
                    <option value="chat">chat</option>
                    <option value="embedding">embed</option>
                    <option value="rerank">rerank</option>
                  </select>
                  {/* Test button */}
                  <button onClick={() => testModel(m.name)} disabled={testing === m.name}
                    style={{ fontSize: 11, letterSpacing: '0.1em', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px', flexShrink: 0 }}>
                    {testing === m.name ? '…' : 'TEST'}
                  </button>
                  {/* Remove */}
                  <button onClick={() => remove(m.name)} style={{ color: '#f87171', background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', flexShrink: 0 }}>
                    <X size={11} />
                  </button>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 64 }}>
                    <span style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.08em' }}>{t('providers.pricingUsdPerMillion')}</span>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, color: 'var(--text-muted)' }}>
                      {t('providers.inputPrice')}
                      <input
                        className="form-input"
                        type="number"
                        min="0"
                        step="0.01"
                        value={m.input_price_per_million ?? ''}
                        onChange={e => setModels(prev => prev.map(x => x.name === m.name ? { ...x, input_price_per_million: e.target.value === '' ? null : Number(e.target.value) } : x))}
                        placeholder="—"
                        style={{ width: 82, height: 26, fontSize: 11 }}
                      />
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, color: 'var(--text-muted)' }}>
                      {t('providers.outputPrice')}
                      <input
                        className="form-input"
                        type="number"
                        min="0"
                        step="0.01"
                        value={m.output_price_per_million ?? ''}
                        onChange={e => setModels(prev => prev.map(x => x.name === m.name ? { ...x, output_price_per_million: e.target.value === '' ? null : Number(e.target.value) } : x))}
                        placeholder="—"
                        style={{ width: 82, height: 26, fontSize: 11 }}
                      />
                    </label>
                    <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{t('providers.pricingOptional')}</span>
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Add model row */}
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            className="form-input"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && add()}
            placeholder={t('providers.modelNamePh')}
            style={{ flex: 1, height: 34, fontSize: 13 }}
          />
          <select
            className="form-input"
            value={newType}
            onChange={e => setNewType(e.target.value as ModelInfo['model_type'])}
            style={{ width: 90, height: 34, fontSize: 12 }}
          >
            <option value="chat">chat</option>
            <option value="embedding">embed</option>
            <option value="rerank">rerank</option>
          </select>
          <button
            onClick={add}
            className="btn"
            style={{ height: 34, border: '1px solid var(--accent-border)', background: 'var(--accent-dim)', color: 'var(--accent)', fontSize: 12, letterSpacing: '0.1em' }}
          >
            {t('providers.addCustom')}
          </button>
        </div>
      </div>
    </Modal>
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
  const { t } = useTranslation()
  const status = providerStatus(provider)
  const sc = STATUS_COLOR[status]
  const preset = PRESETS.find(p => p.name.toLowerCase() === provider.name.toLowerCase() || p.provider_type === provider.provider_type)
  const color = preset?.color || '#6b7280'
  const modelCount = provider.models?.length || 0

  return (
    <div data-item-id={provider.id} className="item-card">
      {/* Top row: avatar + name + status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Avatar name={provider.name} color={color} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="item-card-pip" style={{ background: sc }} />
            <span className="item-card-title">{provider.name}</span>
          </div>
          <div style={{ marginTop: 4 }}>
            <StatusDot status={status} />
          </div>
        </div>
      </div>

      {/* Meta row */}
      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-dim)', alignItems: 'center' }}>
        <span style={{ color: sc, fontWeight: 500, letterSpacing: '0.06em' }}>{modelCount} MODEL{modelCount !== 1 ? 'S' : ''}</span>
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {provider.base_url || '(default endpoint)'}
        </span>
      </div>

      {/* Action buttons */}
      <div className="item-card-actions">
        <button onClick={onSettings} className="item-card-btn">
          <Settings2 size={12} /> SETTINGS
        </button>
        <button onClick={onModels}
          className={`item-card-btn ${status !== 'unconfigured' ? 'accent' : ''}`}
          disabled={status === 'unconfigured'} title={status === 'unconfigured' ? t('providers.unconfiguredTip') : ''}>
          <Database size={12} /> MODELS
        </button>
        <button onClick={onDelete} className="item-card-icon-btn danger" style={{ marginLeft: 'auto' }}>
          <X size={13} />
        </button>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Providers() {
  const { t } = useTranslation()
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

  const load = useCallback(async () => {
    try {
      const list = unwrapList<Provider>(await api.getProviders(), 'providers')
      setProviders(list.map(p => ({
        ...p,
        models: (p.models || []).map(m => typeof m === 'string' ? { name: m, model_type: 'chat' as const } : m),
      })))
    } catch { setProviders([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => { void Promise.resolve().then(() => load()) }, [load])

  const del = async (p: Provider) => {
    if (!confirm(t('providers.confirmDeleteName', { name: p.name }))) return
    try { await api.deleteProvider(String(p.id)); load() } catch (e: unknown) { alert(errorMessage(e)) }
  }

  // Presets not yet in DB — no longer used (the "可添加的 Provider" card grid
  // was hidden per user request; the backend _seed_presets already creates
  // the canonical 14 built-in presets on startup). If the quick-add path is
  // ever restored, recompute:
  //   const configuredNames = new Set(providers.map(p => p.name.toLowerCase()))
  //   const unconfiguredPresets = PRESETS.filter(p => !configuredNames.has(p.name.toLowerCase()))
  //   const filteredPresets = unconfiguredPresets.filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))

  // Sort configured: ready > partial > unconfigured, then filter by search
  const sortedProviders = useMemo(() => {
    const order = { ready: 0, partial: 1, unconfigured: 2 }
    return [...providers]
      .map(p => ({ ...p, _status: providerStatus(p) as 'ready' | 'partial' | 'unconfigured' }))
      .sort((a, b) => order[a._status!] - order[b._status!])
      .filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))
  }, [providers, search])

  return (
    <div>
      <PageHeader
        eyebrow="AI INFRASTRUCTURE"
        title={t('providers.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={load}
              title={t('providers.refresh')}
              className="btn btn-secondary"
              style={{ width: 36, height: 36, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <RefreshCw size={13} />
            </button>
            <button
              onClick={() => setSettingsTarget({})}
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <Plus size={13} /> {t('providers.customProvider')}
            </button>
          </div>
        }
      />

      {/* Search */}
      <div style={{ position: 'relative', marginBottom: 20 }}>
        <Search size={13} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-dim)', pointerEvents: 'none' }} />
        <input
          className="form-input"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={t('providers.searchPh')}
          style={{ paddingLeft: 36 }}
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
              <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 12 }}>{t('providers.configuredCount', { count: sortedProviders.length })}</div>
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

          {/* "可添加的 Provider" card grid removed per user request. The
              backend _seed_presets already creates the canonical 14 built-in
              presets on startup (visible in the main list above), so the
              quick-add cards were a duplicate path. To restore: see the
              PRESETS array at the top of this file and the unconfigured-
              presets filter recipe in the comment above. */}

          {sortedProviders.length === 0 && (
            <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-dim)', fontSize: 13 }}>
              {t('providers.noMatch')}
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
