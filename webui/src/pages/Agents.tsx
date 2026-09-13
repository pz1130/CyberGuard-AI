import { useState, useEffect, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Plus, Loader2, Cpu, Trash, Pencil, Copy, Wifi, WifiOff, Key } from 'lucide-react'
import { SearchContext } from '../context/search'
import { errorMessage } from '../lib/errorMessage'
import { unwrapList } from '../lib/unwrapList'
import Modal from '../components/Modal'
import PageHeader from '../components/PageHeader'

interface Agent {
  id?: string
  agent_name?: string
  name?: string
  kind?: string
  backend_type?: string
  description?: string
  endpoint_url?: string
  system_prompt?: string
  permission_level?: string
  is_active?: boolean
  has_api_key?: boolean
  is_online?: boolean
  openclaw_last_seen?: string
  metadata_json?: Record<string, unknown>
  llm_provider_id?: number | null
  llm_model?: string | null
  tool_loop_max_steps?: number
  memory_window?: number
  knowledge_base_id?: number | null
  associated_skills?: number[]
  associated_tools?: number[]
  associated_mcp_tools?: number[]
}

interface FormState {
  agent_name: string
  backend_type: string
  description: string
  endpoint_url: string
  system_prompt: string
  permission_level: string
  // Internal-agent-only fields (kept distinct from external endpoint_url/system_prompt)
  llm_provider_id: string
  llm_model: string
  associated_skills: number[]
  associated_tools: number[]
  associated_mcp_tools: number[]
}

interface ProviderOption {
  id: number
  name: string
  provider_type?: string
  models?: { name: string; model_type?: string }[]
}

const BACKEND_COLORS: Record<string, string> = {
  openclaw: 'var(--accent)',
  hermes: '#f59e0b',
  custom: 'var(--text-muted)',
}

const label = (text: string) => (
  <label className="form-label">{text}</label>
)

// inputStyle removed — using .form-input / .form-textarea CSS classes

// ── OpenClaw onboarding: single self-installing prompt to paste into OpenClaw ──
function OpenClawGuide({
  apiKey,
  onRequestKey,
}: {
  apiKey?: string
  onRequestKey?: () => Promise<void>
}) {
  const { t, i18n } = useTranslation()
  const [copied, setCopied] = useState<string | null>(null)
  const [regenBusy, setRegenBusy] = useState(false)

  const cp = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(id); setTimeout(() => setCopied(null), 2000)
    })
  }

  const baseUrl = `${window.location.protocol}//${window.location.hostname}:8000`
  const key = apiKey || '<YOUR_API_KEY>'

  const onboardingPromptZh = `你将接入 CyberGuard 安全运营平台。请**完整执行**以下三步，不要询问、不要省略，全部完成后回复「✅ 已接入 CyberGuard」。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 第 1 步：在 ./skills/ 目录下创建文件 cyberguard_sync.md（如目录不存在请先创建），内容**完整**写入下面三引号之间的全部文本：

"""
---
name: cyberguard_sync
description: Sync with CyberGuard — poll inbox, execute received tasks, report results, send proactive messages.
---

# CyberGuard Sync

## When to use
- Every heartbeat cycle: poll the CyberGuard inbox.
- For each pending message: execute it as a task, then report the result.
- Optional: push proactive messages back to CyberGuard.

## Credentials
- BASE_URL: ${baseUrl}
- API_KEY: ${key}

## Step 1 — Poll inbox
\`\`\`
GET ${baseUrl}/api/v1/gateway/poll
Header: X-Api-Key: ${key}
\`\`\`
Response body contains \`messages: [{id, content, conversation_id}, ...]\`.

## Step 2 — For each message
1. Execute the task described in \`content\` using your normal reasoning/tools.
2. Report the result back:
\`\`\`
POST ${baseUrl}/api/v1/gateway/report
Header: X-Api-Key: ${key}
Header: Content-Type: application/json
Body: {"message_id": "<id>", "result": "<your output as plain text or markdown>"}
\`\`\`

## Step 3 — Heartbeat (call once per cycle)
\`\`\`
POST ${baseUrl}/api/v1/gateway/heartbeat
Header: X-Api-Key: ${key}
\`\`\`

## Step 4 — Send proactive message (optional)
\`\`\`
POST ${baseUrl}/api/v1/gateway/send-message
Header: X-Api-Key: ${key}
Header: Content-Type: application/json
Body: {"content": "<your message>"}
\`\`\`
"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 第 2 步：编辑 ./HEARTBEAT.md（如不存在请新建），在文件**末尾追加**一行：

Check CyberGuard inbox using the cyberguard_sync skill and process any pending tasks. Always call /heartbeat once per cycle.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 第 3 步：立即验证接入。执行一次 cyberguard_sync 技能：
1. 发送 POST 到 ${baseUrl}/api/v1/gateway/heartbeat（带 X-Api-Key: ${key}），期望 HTTP 200。
2. 发送 GET 到 ${baseUrl}/api/v1/gateway/poll（带 X-Api-Key），期望返回 200 + JSON \`{"messages": [...]}\`。
3. 如返回 401 或 403，立刻报告错误并停止；否则继续。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
完成全部三步后，回复：
✅ 已接入 CyberGuard（skill 已创建、heartbeat 已配置、连通性已验证）
`

  const onboardingPromptEn = `You are connecting to the CyberGuard security operations platform. Complete all three steps below, then reply "✅ Connected to CyberGuard".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ Step 1: Create ./skills/cyberguard_sync.md (create the directory if needed) with the complete content between the triple quotes:

"""
---
name: cyberguard_sync
description: Sync with CyberGuard — poll inbox, execute received tasks, report results, send proactive messages.
---

# CyberGuard Sync

## When to use
- Every heartbeat cycle: poll the CyberGuard inbox.
- For each pending message: execute it as a task, then report the result.
- Optional: push proactive messages back to CyberGuard.

## Credentials
- BASE_URL: ${baseUrl}
- API_KEY: ${key}

## Step 1 — Poll inbox
\`\`\`
GET ${baseUrl}/api/v1/gateway/poll
Header: X-Api-Key: ${key}
\`\`\`
Response body contains \`messages: [{id, content, conversation_id}, ...]\`.

## Step 2 — For each message
1. Execute the task described in \`content\` using your normal reasoning/tools.
2. Report the result back:
\`\`\`
POST ${baseUrl}/api/v1/gateway/report
Header: X-Api-Key: ${key}
Header: Content-Type: application/json
Body: {"message_id": "<id>", "result": "<your output as plain text or markdown>"}
\`\`\`

## Step 3 — Heartbeat (call once per cycle)
\`\`\`
POST ${baseUrl}/api/v1/gateway/heartbeat
Header: X-Api-Key: ${key}
\`\`\`

## Step 4 — Send proactive message (optional)
\`\`\`
POST ${baseUrl}/api/v1/gateway/send-message
Header: X-Api-Key: ${key}
Header: Content-Type: application/json
Body: {"content": "<your message>"}
\`\`\`
"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ Step 2: Append this line to ./HEARTBEAT.md (create it if needed):

Check CyberGuard inbox using the cyberguard_sync skill and process any pending tasks. Always call /heartbeat once per cycle.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ Step 3: Verify the connection immediately by running cyberguard_sync once:
1. POST ${baseUrl}/api/v1/gateway/heartbeat with X-Api-Key: ${key}; expect HTTP 200.
2. GET ${baseUrl}/api/v1/gateway/poll with X-Api-Key; expect HTTP 200 and JSON \`{"messages": [...]}\`.
3. If either request returns 401 or 403, report the error and stop.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After completing all steps, reply:
✅ Connected to CyberGuard (skill created, heartbeat configured, connectivity verified)
`

  const onboardingPrompt = i18n.language.startsWith('zh') ? onboardingPromptZh : onboardingPromptEn

  const dimText: React.CSSProperties = { fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.7 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        background: 'rgba(0,255,65,0.04)',
        border: '1px solid var(--accent-border)', borderBottom: 'none',
        fontSize: 12, color: 'var(--accent)', letterSpacing: '0.12em', fontWeight: 700,
      }}>
        {t('agents.openClawOneClick')}
      </div>

      <div style={{
        padding: '16px', background: 'var(--bg-base)',
        border: '1px solid var(--accent-border)',
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>

        {/* Intro */}
        <div style={{ fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.7 }}>
          {t('agents.openClawPasteNote')}
        </div>

        {!apiKey && (
          <div style={{
            padding: '10px 12px',
            background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            borderLeft: '3px solid #f59e0b',
            display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          }}>
            <div style={{ ...dimText, flex: 1, minWidth: 200 }}>
              {onRequestKey
                ? <>⚠ {t('agents.keyPlaceholderWarning')}</>
                : <>⚠ {t('agents.keyPlaceholderWarning2')}</>}
            </div>
            {onRequestKey && (
              <button
                disabled={regenBusy}
                onClick={async () => {
                  if (!confirm(t('agents.reissueKey'))) return
                  setRegenBusy(true)
                  try { await onRequestKey() } finally { setRegenBusy(false) }
                }}
                style={{
                  padding: '6px 12px', border: '1px solid var(--accent-border)',
                  background: regenBusy ? 'var(--bg-base)' : 'var(--accent)',
                  color: regenBusy ? 'var(--text-dim)' : '#000',
                  cursor: regenBusy ? 'wait' : 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontSize: 12, letterSpacing: '0.1em', whiteSpace: 'nowrap',
                  fontWeight: 700,
                }}>
                {regenBusy ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Key size={11} />}
                {regenBusy ? 'GENERATING…' : 'GENERATE NEW KEY'}
              </button>
            )}
          </div>
        )}

        {/* The single onboarding prompt */}
        <CodeBlock
          text={onboardingPrompt}
          onCopy={(t) => cp(t, 'prompt')}
          copied={copied === 'prompt'}
        />

        {/* Quick-copy bare key for users who only need the token */}
        {apiKey && (
          <details style={{ marginTop: 2 }}>
            <summary style={{
              ...dimText, cursor: 'pointer', userSelect: 'none',
              listStyle: 'none', letterSpacing: '0.05em',
            }}>
              {t('agents.manualAccess')}
            </summary>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
              <div style={{
                flex: 1, padding: '6px 10px',
                background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)',
                fontSize: 13, color: 'var(--accent)',
                wordBreak: 'break-all',
              }}>{apiKey}</div>
              <button onClick={() => cp(apiKey, 'key')} style={{
                padding: '6px 12px', border: '1px solid var(--accent-border)',
                background: copied === 'key' ? 'var(--accent)' : 'transparent',
                color: copied === 'key' ? '#000' : 'var(--accent)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                fontSize: 12, letterSpacing: '0.1em', whiteSpace: 'nowrap',
              }}>
                <Copy size={11} /> {copied === 'key' ? 'COPIED' : 'COPY KEY'}
              </button>
            </div>
          </details>
        )}

        {/* Online hint */}
        <div style={{
          ...dimText, padding: '8px 12px',
          background: 'var(--bg-elevated)', border: '1px solid var(--border)',
          borderLeft: '3px solid var(--accent)',
        }}>
          {t('agents.pasteSuccessNote')}
        </div>

      </div>
    </div>
  )
}

function CodeBlock({ text, onCopy, copied }: { text: string; onCopy: (t: string) => void; copied?: boolean }) {
  return (
    <div style={{ position: 'relative' }}>
      <pre style={{
        margin: 0, padding: '10px 40px 10px 12px',
        background: 'var(--bg-elevated)', border: '1px solid var(--border)',
        fontSize: 12, color: 'var(--text-primary)',
        whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.7,
        maxHeight: 300, overflowY: 'auto',
      }}>
        {text}
      </pre>
      <button
        onClick={() => onCopy(text)}
        style={{
          position: 'absolute', top: 6, right: 6,
          padding: '3px 8px', border: '1px solid var(--border)',
          background: copied ? 'var(--accent)' : 'var(--bg-base)',
          color: copied ? '#000' : 'var(--text-dim)',
          fontSize: 11, cursor: 'pointer',           letterSpacing: '0.1em', transition: 'all 0.15s',
        }}>
        {copied ? 'COPIED' : 'COPY'}
      </button>
    </div>
  )
}

// ── PoolPicker: reusable checkbox list for skills / tools / mcp-tools ────────
type PoolItem = { id: number; name?: string; tool_name?: string; tags?: string[]; version?: string }

function PoolPicker({ label: lbl, options, selected, onToggle }: {
  label: string
  options: PoolItem[]
  selected: number[]
  onToggle: (id: number) => void
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>{lbl}</label>
      <div style={{ maxHeight: 140, overflowY: 'auto', border: '1px solid var(--border-bright)', background: 'var(--bg-base)', padding: 8 }}>
        {options.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>— none —</div>}
        {options.map(o => {
          const name = o.name || o.tool_name || `#${o.id}`
          return (
            <label key={o.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0', fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={selected.includes(o.id)} onChange={() => onToggle(o.id)} />
              <span style={{ color: 'var(--text-primary)' }}>{name}</span>
              {o.version && <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>v{o.version}</span>}
              {o.tags && o.tags.length > 0 && <span style={{ fontSize: 11, color: '#60a5fa' }}>{o.tags.join(', ')}</span>}
            </label>
          )
        })}
      </div>
    </div>
  )
}

type RunEvent =
  | { type: 'start'; agent_name?: string }
  | { type: 'tool_call_start'; name: string; arguments?: string; call_id: string }
  | { type: 'tool_call_end'; name: string; call_id: string; result_preview?: string; error?: boolean }
  | { type: 'text'; content: string }
  | { type: 'done'; output?: string; execution_time?: number }
  | { type: 'error'; content: string }

function AgentRunPanel({ agentId, agentName, onClose }: {
  agentId: string | number; agentName: string; onClose: () => void
}) {
  const { t } = useTranslation()
  const [task, setTask] = useState('')
  const [running, setRunning] = useState(false)
  const [answer, setAnswer] = useState('')
  const [steps, setSteps] = useState<RunEvent[]>([])
  const [err, setErr] = useState<string | null>(null)

  const run = async () => {
    if (!task.trim() || running) return
    setRunning(true); setAnswer(''); setSteps([]); setErr(null)
    try {
      for await (const ev of api.executeAgentStream(agentId, task) as AsyncIterable<RunEvent>) {
        if (ev.type === 'text') setAnswer(a => a + ev.content)
        else if (ev.type === 'error') { setErr(ev.content); break }
        else if (ev.type === 'tool_call_start' || ev.type === 'tool_call_end') {
          setSteps(s => [...s, ev])
        }
      }
    } catch (e: unknown) {
      setErr(errorMessage(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <Modal width={640} title={t('agents.runAgent', { name: agentName })} onClose={onClose}>
      <textarea value={task} onChange={e => setTask(e.target.value)} rows={3}
        placeholder={t('agents.inputTask')} disabled={running}
        className="form-textarea" />

      <button onClick={run} disabled={running || !task.trim()}
        className="btn btn-primary" style={{ alignSelf: 'flex-start', opacity: running ? 0.6 : 1 }}>
        {running ? t('agents.running') : t('agents.run')}
      </button>

      {steps.length > 0 && (
        <div style={{ fontSize: 13, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {steps.map((s, i) => s.type === 'tool_call_start' ? (
            <div key={`s${i}`} style={{ color: 'var(--text-muted)' }}>{t('agents.stepCall', { name: s.name })}</div>
          ) : s.type === 'tool_call_end' ? (
            <div key={`e${i}`} style={{ color: s.error ? 'var(--red)' : 'var(--accent)' }}>
              {s.error ? '✗' : '✓'} {s.name} — {s.result_preview}
            </div>
          ) : null)}
        </div>
      )}

      {answer && (
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5,
          borderTop: '1px solid var(--border)', paddingTop: 12 }}>{answer}</div>
      )}

      {err && <div style={{ color: 'var(--red)' }}>{t('agents.errorPrefix')}{err}</div>}
    </Modal>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Agents() {
  const { t } = useTranslation()
  const [items, setItems] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>({
    agent_name: '', backend_type: 'openclaw', description: '',
    endpoint_url: '', system_prompt: '', permission_level: 'medium',
    llm_provider_id: '', llm_model: '',
    associated_skills: [], associated_tools: [], associated_mcp_tools: [],
  })
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [regenLoading, setRegenLoading] = useState<string | null>(null)
  const [regenKey, setRegenKey] = useState<Record<string, string>>({})
  const [kindFilter, setKindFilter] = useState<string>('all')
  const [showKindPicker, setShowKindPicker] = useState(false)
  const [providers, setProviders] = useState<ProviderOption[]>([])
  const [skillsPool, setSkillsPool] = useState<PoolItem[]>([])
  const [toolsPool, setToolsPool] = useState<PoolItem[]>([])
  const [mcpToolsPool, setMcpToolsPool] = useState<PoolItem[]>([])
  const [runningAgent, setRunningAgent] = useState<{ id: string | number; name: string } | null>(null)

  const { searchTarget, setSearchTarget } = useContext(SearchContext)

  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'agents') return
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
      setItems(unwrapList<Agent>(await api.getAgents(), 'agents'))
    } catch { setItems([]) } finally { setLoading(false) }
  }

  const loadProviders = async () => {
    try {
      setProviders(unwrapList<ProviderOption>(await api.getProviders(), 'providers'))
    } catch { setProviders([]) }
  }

  const loadPools = async () => {
    try {
      setSkillsPool(unwrapList<PoolItem>(await api.getSkills(), 'skills'))
      setToolsPool(unwrapList<PoolItem>(await api.getTools(), 'tools'))
      setMcpToolsPool(unwrapList<PoolItem>(await api.getAllMcpTools(), 'tools'))
    } catch { /* leave pools empty */ }
  }

  useEffect(() => { load(); loadProviders(); loadPools() }, [])

  const selectedProvider = providers.find(p => String(p.id) === form.llm_provider_id)

  const toggleId = (key: 'associated_skills' | 'associated_tools' | 'associated_mcp_tools', id: number) =>
    setForm(f => ({ ...f, [key]: f[key].includes(id) ? f[key].filter(x => x !== id) : [...f[key], id] }))

  const openCreate = (isInternal = false) => {
    setEditing(null)
    setCreatedApiKey(null)
    setForm({
      agent_name: '', backend_type: isInternal ? '__internal__' : 'openclaw',
      description: '', endpoint_url: '', system_prompt: '', permission_level: 'medium',
      llm_provider_id: '', llm_model: '',
      associated_skills: [], associated_tools: [], associated_mcp_tools: [],
    })
    setShowForm(true)
  }

  const openEdit = (a: Agent) => {
    setEditing(a.id!)
    setCreatedApiKey(null)
    const isInternal = (a.kind || 'external') === 'internal'
    setForm({
      agent_name: a.agent_name || a.name || '',
      backend_type: isInternal ? '__internal__' : (a.backend_type || 'openclaw'),
      description: a.description || '',
      endpoint_url: a.endpoint_url || '',
      system_prompt: a.system_prompt || '',
      permission_level: a.permission_level || 'medium',
      llm_provider_id: isInternal ? String(a.llm_provider_id || '') : '',
      llm_model: isInternal ? (a.llm_model || '') : '',
      associated_skills: a.associated_skills || [],
      associated_tools: a.associated_tools || [],
      associated_mcp_tools: a.associated_mcp_tools || [],
    })
    setShowForm(true)
  }

  const submit = async () => {
    if (!form.agent_name) return
    try {
      const isInternal = form.backend_type === '__internal__'
      const payload: Record<string, unknown> = {
        agent_name: form.agent_name,
        kind: isInternal ? 'internal' : 'external',
        description: form.description || undefined,
        permission_level: form.permission_level,
      }

      if (isInternal) {
        // Internal agent fields — runs in-app, no external endpoint
        const llmProviderId = parseInt(form.llm_provider_id || '0', 10)
        if (llmProviderId) payload.llm_provider_id = llmProviderId
        const model = form.llm_model?.trim()
        if (model) payload.llm_model = model
        const sysPrompt = form.system_prompt?.trim()
        if (sysPrompt) payload.system_prompt = sysPrompt
        payload.tool_loop_max_steps = 8
        payload.memory_window = 20
        payload.backend_type = 'openclaw'  // required but unused for internal
        payload.associated_skills = form.associated_skills
        payload.associated_tools = form.associated_tools
        payload.associated_mcp_tools = form.associated_mcp_tools
      } else {
        // External agent fields
        payload.backend_type = form.backend_type
        payload.system_prompt = form.system_prompt || undefined
        if (form.backend_type !== 'openclaw' && form.endpoint_url) {
          payload.endpoint_url = form.endpoint_url
        }
      }

      if (editing) {
        await api.updateAgent(editing, payload)
        setShowForm(false)
      } else {
        const res = await api.createAgent(payload) as { api_key?: string }
        if (!isInternal && res?.api_key) {
          setCreatedApiKey(res.api_key)
        } else {
          setShowForm(false)
        }
      }
      load()
    } catch (e: unknown) { alert(errorMessage(e)) }
  }

  const del = async (id: string) => {
    if (!confirm(t('agents.confirmDelete'))) return
    await api.deleteAgent(id); load()
  }

  const test = async (id: string) => {
    setTesting(id)
    try {
      const res = await api.testAgent(id, {}) as { success?: boolean; error?: string }
      setTestResult(r => ({ ...r, [id]: { ok: !!res.success, msg: res.error || (res.success ? t('agents.connectionOk') : t('agents.connectionFail')) } }))
    } catch (e: unknown) {
      setTestResult(r => ({ ...r, [id]: { ok: false, msg: errorMessage(e) } }))
    } finally { setTesting(null) }
  }

  const regenApiKey = async (id: string) => {
    if (!confirm(t('agents.reissueKeyShort'))) return
    setRegenLoading(id)
    try {
      const res = await api.regenAgentApiKey(id) as { api_key?: string }
      const key = res?.api_key
      if (key) setRegenKey(k => ({ ...k, [id]: key }))
    } catch (e: unknown) { alert(errorMessage(e)) }
    finally { setRegenLoading(null) }
  }

  const agentName = (a: Agent) => a.agent_name || a.name || '—'

  return (
    <div>
      <PageHeader
        eyebrow="AGENT INFRASTRUCTURE"
        title={t('agents.title').toUpperCase()}
        actions={
          <button onClick={() => setShowKindPicker(true)} className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Plus size={13} /> NEW AGENT
          </button>
        }
      />

      {/* Kind filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['all', 'external', 'internal'].map(k => (
          <button key={k} onClick={() => setKindFilter(k)}
            style={{
              padding: '4px 12px', border: `1px solid ${kindFilter === k ? 'var(--accent)' : 'var(--border)'}`,
              background: kindFilter === k ? 'var(--accent)' : 'transparent',
              color: kindFilter === k ? '#000' : 'var(--text-muted)',
              fontSize: 11, letterSpacing: '0.1em', cursor: 'pointer',
              fontWeight: 700,
            }}>
            {k === 'all' ? 'ALL' : k.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Grid */}
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 0' }}>
          <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '60px 0', gap: 12 }}>
          <Cpu size={24} style={{ color: 'var(--text-dim)' }} />
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO ACTIVE AGENTS</div>
          <button onClick={() => setShowKindPicker(true)} style={{ fontSize: 12, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + DEPLOY FIRST AGENT
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {items.filter(a => kindFilter === 'all' || (a.kind || 'external') === kindFilter).map(a => {
            const isInternal = (a.kind || 'external') === 'internal'
            const bc = isInternal ? '#60a5fa' : BACKEND_COLORS[a.backend_type || 'custom']
            // Internal agents run in-process; the OpenClaw online/offline +
            // poll concept never applies to them (even though their stored
            // backend_type is 'openclaw' as an unused placeholder).
            const isOpenClaw = !isInternal && a.backend_type === 'openclaw'
            const online = a.is_online || false
            const thisRegenKey = regenKey[a.id!]

            return (
              <div key={a.id} data-item-id={a.id} className="item-card">
                {/* Name + kind badge */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                    <span className="item-card-pip" style={{ background: bc }} />
                    <span className="item-card-title">{agentName(a)}</span>
                  </div>
                  <span className="item-card-badge" style={{ color: isInternal ? '#60a5fa' : bc }}>
                    {isInternal ? 'INTERNAL' : (a.backend_type || 'CUSTOM').toUpperCase()}
                  </span>
                </div>

                {/* Internal agents run in-process — always ready, no poll */}
                {isInternal && (
                  <div className="item-card-status" style={{ color: '#60a5fa' }}>
                    <Cpu size={13} />
                    <span>{t('agents.readyProcess')}</span>
                  </div>
                )}

                {/* Online status (OpenClaw only) */}
                {isOpenClaw && (
                  <div className="item-card-status" style={{ color: online ? 'var(--accent)' : 'var(--text-dim)' }}>
                    {online ? <Wifi size={12} /> : <WifiOff size={12} />}
                    <span>{online ? 'ONLINE' : 'OFFLINE'}</span>
                    {a.openclaw_last_seen && (
                      <span style={{ color: 'var(--text-dim)' }}>
                        · {t('agents.lastSeen')}{new Date(a.openclaw_last_seen).toLocaleTimeString()}
                      </span>
                    )}
                    {!a.has_api_key && (
                      <span style={{ marginLeft: 'auto', color: '#f59e0b' }}>
                        ⚠ NO KEY
                      </span>
                    )}
                  </div>
                )}

                {a.description && (
                  <div className="item-card-desc">{a.description}</div>
                )}

                {/* Regenerated key display */}
                {!isInternal && thisRegenKey && (
                  <div style={{
                    padding: '8px 10px',
                    background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)',
                    borderRadius: 'var(--radius-md)',
                    fontSize: 11, color: 'var(--accent)',
                    wordBreak: 'break-all', lineHeight: 1.7,
                  }}>
                    <div style={{ marginBottom: 4, letterSpacing: '0.1em' }}>⚠ NEW KEY — COPY NOW:</div>
                    {thisRegenKey}
                  </div>
                )}

                {/* Test result */}
                {testResult[a.id!] && (
                  <div style={{
                    padding: '6px 10px',
                    background: 'var(--bg-base)', border: `1px solid ${testResult[a.id!].ok ? 'var(--accent-border)' : 'rgba(255,60,60,0.3)'}`,
                    borderRadius: 'var(--radius-md)',
                    fontSize: 12, color: testResult[a.id!].ok ? 'var(--accent)' : '#f87171',
                  }}>
                    {testResult[a.id!].ok ? '✓' : '✗'} {testResult[a.id!].msg}
                  </div>
                )}

                {/* Action row */}
                <div className="item-card-actions">
                  <button onClick={() => test(a.id!)} disabled={testing === a.id}
                    className={`item-card-btn ${testing !== a.id ? 'accent' : ''}`}>
                    {testing === a.id ? '…' : 'TEST'}
                  </button>

                  <button onClick={() => setRunningAgent({ id: a.id!, name: a.agent_name || a.id! })}
                    className="item-card-btn accent">
                    RUN
                  </button>

                  {!isInternal && (
                    <button onClick={() => regenApiKey(a.id!)} disabled={regenLoading === a.id}
                      title={t('agents.reissueTitle')}
                      className="item-card-btn">
                      {regenLoading === a.id
                        ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} />
                        : <><Key size={11} /> REGEN KEY</>}
                    </button>
                  )}

                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                    <button onClick={() => openEdit(a)} className="item-card-icon-btn">
                      <Pencil size={13} />
                    </button>
                    <button onClick={() => del(a.id!)} className="item-card-icon-btn danger">
                      <Trash size={13} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Kind chooser modal */}
      {showKindPicker && (
        <Modal
          width={480}
          eyebrow="NEW AGENT"
          title="CHOOSE AGENT KIND"
          onClose={() => setShowKindPicker(false)}
          footer={(
            <button onClick={() => setShowKindPicker(false)} className="btn btn-secondary">
              CANCEL
            </button>
          )}
        >
          <button
            onClick={() => { setShowKindPicker(false); openCreate(false) }}
            style={{
              padding: '18px 20px', border: '1px solid var(--border-bright)', borderRadius: 'var(--radius-md)',
              background: 'var(--bg-base)', cursor: 'pointer', textAlign: 'left',
            }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 6 }}>EXTERNAL AGENT</div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              OpenClaw, Hermes, or Custom HTTP endpoint. Deploy a separate process and connect via protocol.
            </div>
          </button>
          <button
            onClick={() => {
              setShowKindPicker(false)
              openCreate(true)
            }}
            style={{
              padding: '18px 20px', border: '1px solid rgba(96,165,250,0.4)', borderRadius: 'var(--radius-md)',
              background: 'rgba(96,165,250,0.04)', cursor: 'pointer', textAlign: 'left',
            }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#60a5fa', letterSpacing: '0.1em', marginBottom: 6 }}>INTERNAL AGENT</div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              Configured fully in-app. Select system prompt, LLM provider, skills, MCP tools, and optional knowledge base.
            </div>
          </button>
        </Modal>
      )}

      {/* Form Modal */}
      {showForm && (
        <Modal
          width={620}
          eyebrow="AGENT CONFIGURATION"
          title={editing ? 'EDIT AGENT' : form.backend_type === '__internal__' ? 'DEPLOY INTERNAL AGENT' : 'DEPLOY EXTERNAL AGENT'}
          closeOnOverlay={!createdApiKey}
          onClose={() => { if (!createdApiKey) setShowForm(false) }}
          footer={createdApiKey ? (
            <button onClick={() => { setShowForm(false); setCreatedApiKey(null) }} className="btn btn-primary" style={{ flex: 1 }}>
              {t('agents.savedKeyClose')}
            </button>
          ) : (
            <>
              <button onClick={() => setShowForm(false)} className="btn btn-secondary">CANCEL</button>
              <button onClick={submit} className="btn btn-primary">{editing ? 'SAVE CHANGES' : 'DEPLOY AGENT'}</button>
            </>
          )}
        >

              {/* Name + Kind/Backend */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  {label('AGENT NAME *')}
                  <input value={form.agent_name}
                    onChange={e => setForm(f => ({ ...f, agent_name: e.target.value }))}
                    placeholder="e.g. Threat Intel Agent"
                    className="form-input" />
                </div>
                <div>
                  {label('AGENT KIND')}
                  <div style={{
                    height: 38, padding: '0 12px', display: 'flex', alignItems: 'center',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    fontSize: 14, letterSpacing: '0.05em',
                    color: form.backend_type === '__internal__' ? '#60a5fa' : 'var(--accent)',
                  }}>
                    {form.backend_type === '__internal__' ? 'INTERNAL' : 'EXTERNAL'}
                  </div>
                </div>
              </div>

              {/* Internal agent fields */}
              {form.backend_type === '__internal__' && (
                <>
                  {/* LLM Provider + Model */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div>
                      {label('LLM PROVIDER *')}
                      <select value={form.llm_provider_id || ''}
                        onChange={e => setForm(f => ({ ...f, llm_provider_id: e.target.value, llm_model: '' }))}
                        className="form-input">
                        <option value="">— {t('agents.selectProvider').replace('— ', '')} —</option>
                        {providers.map(p => (
                          <option key={p.id} value={String(p.id)}>
                            {p.name}{p.provider_type ? ` (${p.provider_type})` : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      {label('LLM MODEL')}
                      {selectedProvider?.models?.length ? (
                        <select value={form.llm_model || ''}
                          onChange={e => setForm(f => ({ ...f, llm_model: e.target.value }))}
                          className="form-input">
                          <option value="">{t('agents.autoProvider')}</option>
                          {selectedProvider.models.map(m => (
                            <option key={m.name} value={m.name}>{m.name}</option>
                          ))}
                        </select>
                      ) : (
                        <input value={form.llm_model || ''}
                          onChange={e => setForm(f => ({ ...f, llm_model: e.target.value }))}
                          placeholder="auto / gpt-4o / etc."
                          className="form-input" />
                      )}
                    </div>
                  </div>

                  {/* Tool loop settings */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div>
                      {label('TOOL LOOP MAX STEPS')}
                      <input type="number" value="8"
                        readOnly
                        style={{ color: 'var(--text-dim)' }} className="form-input" />
                    </div>
                    <div>
                      {label('MEMORY WINDOW')}
                      <input type="number" value="20"
                        readOnly
                        style={{ color: 'var(--text-dim)' }} className="form-input" />
                    </div>
                  </div>

                  {/* Skill / Tool / MCP-tool assignment */}
                  <div>
                    <PoolPicker label="SKILLS" options={skillsPool} selected={form.associated_skills} onToggle={id => toggleId('associated_skills', id)} />
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 6, lineHeight: 1.5 }}>
                      Internal agents: catalog only in system prompt (name + description). Full SOP body via{' '}
                      <code style={{ color: 'var(--cyan)' }}>load_skill</code> at runtime. Prefer short, action-oriented skill descriptions.
                    </div>
                  </div>
                  <PoolPicker label="TOOLS" options={toolsPool} selected={form.associated_tools} onToggle={id => toggleId('associated_tools', id)} />
                  <PoolPicker label="MCP TOOLS" options={mcpToolsPool} selected={form.associated_mcp_tools} onToggle={id => toggleId('associated_mcp_tools', id)} />
                </>
              )}

              {/* Backend Type (external only) */}
              {form.backend_type !== '__internal__' && (
                <div>
                  {label('BACKEND TYPE')}
                  <select value={form.backend_type}
                    onChange={e => setForm(f => ({ ...f, backend_type: e.target.value }))}
                    className="form-input">
                    <option value="openclaw">{t('agents.openClawType')}</option>
                    <option value="hermes">HERMES</option>
                    <option value="custom">CUSTOM</option>
                  </select>
                </div>
              )}

              {/* Description */}
              <div>
                {label('DESCRIPTION')}
                <input value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder={t('agents.systemPromptPh')}
                  className="form-input" />
              </div>

              {/* Endpoint URL — 仅非 OpenClaw */}
              {form.backend_type !== 'openclaw' && form.backend_type !== '__internal__' && (
                <div>
                  {label('ENDPOINT URL *')}
                  <input value={form.endpoint_url}
                    onChange={e => setForm(f => ({ ...f, endpoint_url: e.target.value }))}
                    placeholder="http://your-agent-host:8001"
                    className="form-input" />
                  <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-dim)' }}>
                    {t('agents.exposeEndpointNote')}
                  </div>
                </div>
              )}

              {/* Permission */}
              <div>
                {label('PERMISSION LEVEL')}
                <select value={form.permission_level}
                  onChange={e => setForm(f => ({ ...f, permission_level: e.target.value }))}
                  className="form-input">
                  <option value="low">{t('agents.permissionLow')}</option>
                  <option value="medium">{t('agents.permissionMedium')}</option>
                  <option value="high">{t('agents.permissionHigh')}</option>
                </select>
              </div>

              {/* System Prompt */}
              <div>
                {label(t('agents.systemPromptLabel'))}
                <textarea value={form.system_prompt}
                  onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                  placeholder={t('agents.systemPromptPh')}
                  rows={3}
                  className="form-textarea" />
              </div>

              {/* OpenClaw Guide */}
              {form.backend_type === 'openclaw' && (
                <OpenClawGuide
                  apiKey={createdApiKey || undefined}
                  onRequestKey={editing ? async () => {
                    try {
                      const res = await api.regenAgentApiKey(editing) as { api_key?: string }
                      if (res?.api_key) setCreatedApiKey(res.api_key)
                    } catch (e: unknown) {
                      alert(errorMessage(e) || t('agents.genKeyFail'))
                    }
                  } : undefined}
                />
              )}

              {/* Hermes / Custom — key panel: shown after creation (key visible) or when editing (regen only) */}
              {form.backend_type !== '__internal__' && form.backend_type !== 'openclaw' && (createdApiKey || editing) && (
                <div style={{
                  padding: '14px 16px',
                  background: 'rgba(0,255,65,0.04)',
                  border: '1px solid var(--accent-border)',
                  display: 'flex', flexDirection: 'column', gap: 10,
                }}>
                  <div style={{ fontSize: 12, color: 'var(--accent)', letterSpacing: '0.12em', fontWeight: 700 }}>
                    ◆ GATEWAY API KEY
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.7 }} dangerouslySetInnerHTML={{ __html: t('agents.externalKeyNote') }} />
                  {createdApiKey ? (
                    <>
                      <div style={{ fontSize: 11, color: '#f59e0b', letterSpacing: '0.08em' }}>{t('agents.showOnceWarning')}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{
                          flex: 1, padding: '6px 10px',
                          background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)',
                          fontSize: 13, color: 'var(--accent)',
                          wordBreak: 'break-all',
                        }}>{createdApiKey}</div>
                        <button
                          onClick={() => navigator.clipboard.writeText(createdApiKey)}
                          style={{
                            padding: '6px 12px', border: '1px solid var(--accent-border)',
                            background: 'transparent', color: 'var(--accent)',
                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                            fontSize: 12, letterSpacing: '0.1em', whiteSpace: 'nowrap',
                          }}>
                          <Copy size={11} /> COPY KEY
                        </button>
                      </div>
                    </>
                  ) : (
                    <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                      {t('agents.keyExistsNote')}
                    </div>
                  )}
                  {editing && (
                    <button
                      onClick={async () => {
                        if (!confirm(t('agents.reissueKeyShort'))) return
                        try {
                          const res = await api.regenAgentApiKey(editing) as { api_key?: string }
                          if (res?.api_key) setCreatedApiKey(res.api_key)
                        } catch (e: unknown) { alert(errorMessage(e) || t('agents.genKeyFail')) }
                      }}
                      style={{
                        alignSelf: 'flex-start', padding: '6px 12px',
                        border: '1px solid var(--accent-border)', background: 'transparent',
                        color: 'var(--accent)', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: 6,
                        fontSize: 12, letterSpacing: '0.1em',                       }}>
                      <Key size={11} /> GENERATE NEW KEY
                    </button>
                  )}
                </div>
              )}

        </Modal>
      )}

      {runningAgent && (
        <AgentRunPanel agentId={runningAgent.id} agentName={runningAgent.name}
          onClose={() => setRunningAgent(null)} />
      )}
    </div>
  )
}
