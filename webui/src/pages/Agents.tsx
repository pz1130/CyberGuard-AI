import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Plus, Loader2, Cpu, Trash, Pencil, Copy, Wifi, WifiOff, Key } from 'lucide-react'

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
  metadata_json?: Record<string, any>
  llm_provider_id?: number | null
  llm_model?: string | null
  tool_loop_max_steps?: number
  memory_window?: number
  knowledge_base_id?: number | null
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
}

const BACKEND_COLORS: Record<string, string> = {
  openclaw: 'var(--accent)',
  hermes: '#f59e0b',
  custom: 'var(--text-muted)',
}

const label = (text: string) => (
  <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>
    {text}
  </label>
)

const inputStyle: React.CSSProperties = {
  width: '100%', height: 38, padding: '0 12px',
  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
  color: 'var(--text-primary)', fontSize: 12, letterSpacing: '0.05em',
  fontFamily: 'var(--font-mono)', boxSizing: 'border-box',
}

// ── OpenClaw onboarding: single self-installing prompt to paste into OpenClaw ──
function OpenClawGuide({
  apiKey,
  onRequestKey,
}: {
  apiKey?: string
  onRequestKey?: () => Promise<void>
}) {
  const [copied, setCopied] = useState<string | null>(null)
  const [regenBusy, setRegenBusy] = useState(false)

  const cp = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(id); setTimeout(() => setCopied(null), 2000)
    })
  }

  const baseUrl = `${window.location.protocol}//${window.location.hostname}:8000`
  const key = apiKey || '<YOUR_API_KEY>'

  const onboardingPrompt = `你将接入 CyberGuard 安全运营平台。请**完整执行**以下三步，不要询问、不要省略，全部完成后回复「✅ 已接入 CyberGuard」。

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

  const dimText: React.CSSProperties = { fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.7 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        background: 'rgba(0,255,65,0.04)',
        border: '1px solid var(--accent-border)', borderBottom: 'none',
        fontSize: 10, color: 'var(--accent)', letterSpacing: '0.12em', fontWeight: 700,
      }}>
        ◆ OPENCLAW 一键接入
      </div>

      <div style={{
        padding: '16px', background: 'var(--bg-base)',
        border: '1px solid var(--accent-border)',
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>

        {/* Intro */}
        <div style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.7 }}>
          复制下方一段提示词，粘贴到 OpenClaw 节点的对话窗口里。OpenClaw 会自动创建 skill、配置 heartbeat 并验证接入——你**无需手动建文件**。
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
                ? <>⚠ 提示词里的 Key 是占位符。点右侧按钮**重新签发** API Key（旧 Key 立即失效），新 Key 会自动塞进提示词。</>
                : <>⚠ 当前提示词中的 API Key 是占位符。请先点击 <span style={{ color: 'var(--accent)' }}>DEPLOY AGENT</span> 生成真实 Key。</>}
            </div>
            {onRequestKey && (
              <button
                disabled={regenBusy}
                onClick={async () => {
                  if (!confirm('重新签发 API Key？旧 Key 立即失效，已部署的 OpenClaw 节点需要用新 Key 重新接入。')) return
                  setRegenBusy(true)
                  try { await onRequestKey() } finally { setRegenBusy(false) }
                }}
                style={{
                  padding: '6px 12px', border: '1px solid var(--accent-border)',
                  background: regenBusy ? 'var(--bg-base)' : 'var(--accent)',
                  color: regenBusy ? 'var(--text-dim)' : '#000',
                  cursor: regenBusy ? 'wait' : 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontSize: 10, letterSpacing: '0.1em', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap',
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
              › 只需要 API Key（手动接入）
            </summary>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
              <div style={{
                flex: 1, padding: '6px 10px',
                background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)',
                fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)',
                wordBreak: 'break-all',
              }}>{apiKey}</div>
              <button onClick={() => cp(apiKey, 'key')} style={{
                padding: '6px 12px', border: '1px solid var(--accent-border)',
                background: copied === 'key' ? 'var(--accent)' : 'transparent',
                color: copied === 'key' ? '#000' : 'var(--accent)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                fontSize: 10, letterSpacing: '0.1em', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap',
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
          粘贴后 OpenClaw 会回复 <span style={{ color: 'var(--accent)' }}>✅ 已接入 CyberGuard</span>。回到此页面刷新，Agent 卡片右上角出现 <span style={{ color: 'var(--accent)' }}>● ONLINE</span> 即接入成功。
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
        fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-primary)',
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
          fontSize: 9, cursor: 'pointer', fontFamily: 'var(--font-mono)',
          letterSpacing: '0.1em', transition: 'all 0.15s',
        }}>
        {copied ? 'COPIED' : 'COPY'}
      </button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Agents() {
  const [items, setItems] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>({
    agent_name: '', backend_type: 'openclaw', description: '',
    endpoint_url: '', system_prompt: '', permission_level: 'medium',
    llm_provider_id: '', llm_model: '',
  })
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [regenLoading, setRegenLoading] = useState<string | null>(null)
  const [regenKey, setRegenKey] = useState<Record<string, string>>({})
  const [kindFilter, setKindFilter] = useState<string>('all')
  const [showKindPicker, setShowKindPicker] = useState(false)

  const load = async () => {
    try {
      const data = await api.getAgents() as any
      const list: Agent[] = Array.isArray(data) ? data : (data?.agents || [])
      setItems(list)
    } catch { setItems([]) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openCreate = (isInternal = false) => {
    setEditing(null)
    setCreatedApiKey(null)
    setForm({
      agent_name: '', backend_type: isInternal ? '__internal__' : 'openclaw',
      description: '', endpoint_url: '', system_prompt: '', permission_level: 'medium',
      llm_provider_id: '', llm_model: '',
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
    })
    setShowForm(true)
  }

  const submit = async () => {
    if (!form.agent_name) return
    try {
      const isInternal = form.backend_type === '__internal__'
      const payload: Record<string, any> = {
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
        const res = await api.createAgent(payload) as any
        if (!isInternal && res?.api_key) {
          setCreatedApiKey(res.api_key)
        } else {
          setShowForm(false)
        }
      }
      load()
    } catch (e: any) { alert(e.message || String(e)) }
  }

  const del = async (id: string) => {
    if (!confirm('确认删除此 Agent？')) return
    await api.deleteAgent(id); load()
  }

  const test = async (id: string) => {
    setTesting(id)
    try {
      const res = await api.testAgent(id, {}) as any
      setTestResult(r => ({ ...r, [id]: { ok: res.success, msg: res.error || (res.success ? '连接正常' : '连接失败') } }))
    } catch (e: any) {
      setTestResult(r => ({ ...r, [id]: { ok: false, msg: e.message } }))
    } finally { setTesting(null) }
  }

  const regenApiKey = async (id: string) => {
    if (!confirm('重新生成 API Key？旧 Key 将立即失效。')) return
    setRegenLoading(id)
    try {
      const res = await (api as any).regenAgentApiKey(id) as any
      if (res?.api_key) setRegenKey(k => ({ ...k, [id]: res.api_key }))
    } catch (e: any) { alert(e.message) }
    finally { setRegenLoading(null) }
  }

  const agentName = (a: Agent) => a.agent_name || a.name || '—'

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>AGENT INFRASTRUCTURE</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SUB-AGENTS</h1>
        </div>
        <button onClick={() => setShowKindPicker(true)} style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px', height: 36,
          background: 'var(--accent)', border: '1px solid var(--accent-border)',
          color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: '0.15em',
          cursor: 'pointer', fontFamily: 'var(--font-mono)',
          boxShadow: '0 0 16px rgba(0,255,65,0.15)',
        }}>
          <Plus size={13} /> NEW AGENT
        </button>
      </div>

      {/* Kind filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['all', 'external', 'internal'].map(k => (
          <button key={k} onClick={() => setKindFilter(k)}
            style={{
              padding: '4px 12px', border: `1px solid ${kindFilter === k ? 'var(--accent)' : 'var(--border)'}`,
              background: kindFilter === k ? 'var(--accent)' : 'transparent',
              color: kindFilter === k ? '#000' : 'var(--text-muted)',
              fontSize: 9, letterSpacing: '0.1em', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontWeight: 700,
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
          <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO ACTIVE AGENTS</div>
          <button onClick={() => setShowKindPicker(true)} style={{ fontSize: 10, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + DEPLOY FIRST AGENT
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {items.filter(a => kindFilter === 'all' || (a.kind || 'external') === kindFilter).map(a => {
            const bc = BACKEND_COLORS[a.backend_type || 'custom']
            const isOpenClaw = a.backend_type === 'openclaw'
            const isInternal = (a.kind || 'external') === 'internal'
            const online = a.is_online || false
            const thisRegenKey = regenKey[a.id!]

            return (
              <div key={a.id} style={{
                padding: 18, background: 'var(--bg-surface)',
                border: '1px solid var(--border-bright)',
                borderLeft: `3px solid ${bc}`,
              }}>
                {/* Name + kind badge */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>
                    {agentName(a)}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <div style={{
                      padding: '2px 7px', border: `1px solid ${isInternal ? '#60a5fa' : bc}`,
                      fontSize: 8, letterSpacing: '0.15em', color: isInternal ? '#60a5fa' : bc, background: 'var(--bg-base)',
                    }}>
                      {isInternal ? 'INTERNAL' : (a.backend_type || 'CUSTOM').toUpperCase()}
                    </div>
                  </div>
                </div>

                {/* Online status (OpenClaw only) */}
                {isOpenClaw && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                    {online
                      ? <Wifi size={11} style={{ color: 'var(--accent)' }} />
                      : <WifiOff size={11} style={{ color: 'var(--text-dim)' }} />}
                    <span style={{ fontSize: 9, letterSpacing: '0.1em', color: online ? 'var(--accent)' : 'var(--text-dim)' }}>
                      {online ? 'ONLINE' : 'OFFLINE'}
                    </span>
                    {a.openclaw_last_seen && (
                      <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 4 }}>
                        · 最近: {new Date(a.openclaw_last_seen).toLocaleTimeString()}
                      </span>
                    )}
                    {!a.has_api_key && (
                      <span style={{ marginLeft: 'auto', fontSize: 9, color: '#f59e0b', letterSpacing: '0.08em' }}>
                        ⚠ NO KEY
                      </span>
                    )}
                  </div>
                )}

                {a.description && (
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 10 }}>
                    {a.description}
                  </div>
                )}

                {/* Regenerated key display */}
                {isOpenClaw && thisRegenKey && (
                  <div style={{
                    padding: '8px 10px', marginBottom: 10,
                    background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)',
                    fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--accent)',
                    wordBreak: 'break-all', lineHeight: 1.7,
                  }}>
                    <div style={{ marginBottom: 4, letterSpacing: '0.1em' }}>⚠ NEW KEY — COPY NOW:</div>
                    {thisRegenKey}
                  </div>
                )}

                {/* Test result */}
                {testResult[a.id!] && (
                  <div style={{
                    padding: '6px 10px', marginBottom: 10,
                    background: 'var(--bg-base)', border: `1px solid ${testResult[a.id!].ok ? 'var(--accent-border)' : 'rgba(255,60,60,0.3)'}`,
                    fontSize: 10, color: testResult[a.id!].ok ? 'var(--accent)' : '#f87171',
                    fontFamily: 'var(--font-mono)', letterSpacing: '0.03em',
                  }}>
                    {testResult[a.id!].ok ? '✓' : '✗'} {testResult[a.id!].msg}
                  </div>
                )}

                {/* Action row */}
                <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button onClick={() => test(a.id!)} disabled={testing === a.id}
                    style={{
                      padding: '0 10px', height: 28, border: '1px solid var(--border-bright)',
                      background: 'transparent', color: testing === a.id ? 'var(--text-dim)' : 'var(--accent)',
                      fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer',
                      fontFamily: 'var(--font-mono)',
                    }}>
                    {testing === a.id ? '…' : 'TEST'}
                  </button>

                  {isOpenClaw && (
                    <button onClick={() => regenApiKey(a.id!)} disabled={regenLoading === a.id}
                      title="重新生成 API Key"
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '0 10px', height: 28, border: '1px solid var(--border-bright)',
                        background: 'transparent', color: 'var(--text-muted)',
                        fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer',
                        fontFamily: 'var(--font-mono)',
                      }}>
                      {regenLoading === a.id
                        ? <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} />
                        : <><Key size={10} /> REGEN KEY</>}
                    </button>
                  )}

                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                    <button onClick={() => openEdit(a)} style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
                      <Pencil size={12} />
                    </button>
                    <button onClick={() => del(a.id!)} style={{ padding: 4, color: '#f87171', cursor: 'pointer', background: 'none', border: 'none' }}>
                      <Trash size={12} />
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
        <div
          onClick={e => e.target === e.currentTarget && setShowKindPicker(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', zIndex: 101, overflowY: 'auto', padding: '40px 20px' }}>
          <div style={{
            width: '100%', maxWidth: 480, background: 'var(--bg-surface)',
            border: '1px solid var(--border-bright)',
          }}>
            <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 4 }}>NEW AGENT</div>
              <h3 style={{ fontSize: 16, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)', margin: 0 }}>
                CHOOSE AGENT KIND
              </h3>
            </div>
            <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
              <button
                onClick={() => { setShowKindPicker(false); openCreate(false) }}
                style={{
                  padding: '18px 20px', border: '1px solid var(--border-bright)',
                  background: 'var(--bg-base)', cursor: 'pointer', textAlign: 'left',
                }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 6 }}>EXTERNAL AGENT</div>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.6 }}>
                  OpenClaw, Hermes, or Custom HTTP endpoint. Deploy a separate process and connect via protocol.
                </div>
              </button>
              <button
                onClick={() => {
                  setShowKindPicker(false)
                  openCreate(true)
                }}
                style={{
                  padding: '18px 20px', border: '1px solid rgba(96,165,250,0.4)',
                  background: 'rgba(96,165,250,0.04)', cursor: 'pointer', textAlign: 'left',
                }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#60a5fa', letterSpacing: '0.1em', marginBottom: 6 }}>INTERNAL AGENT</div>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.6 }}>
                  Configured fully in-app. Select system prompt, LLM provider, skills, MCP tools, and optional knowledge base.
                </div>
              </button>
            </div>
            <div style={{ padding: '12px 24px', borderTop: '1px solid var(--border)' }}>
              <button onClick={() => setShowKindPicker(false)} style={{
                padding: '0 16px', height: 32, border: '1px solid var(--border-bright)',
                background: 'transparent', color: 'var(--text-muted)',
                fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
              }}>
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Form Modal */}
      {showForm && (
        <div
          onClick={e => e.target === e.currentTarget && !createdApiKey && setShowForm(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', zIndex: 100, overflowY: 'auto', padding: '40px 20px' }}>
          <div style={{
            width: '100%', maxWidth: 620, background: 'var(--bg-surface)',
            border: '1px solid var(--border-bright)',
          }}>
            {/* Modal header */}
            <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 4 }}>AGENT CONFIGURATION</div>
              <h3 style={{ fontSize: 16, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)', margin: 0 }}>
                {editing ? 'EDIT AGENT' : form.backend_type === '__internal__' ? 'DEPLOY INTERNAL AGENT' : 'DEPLOY EXTERNAL AGENT'}
              </h3>
            </div>

            <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

              {/* Name + Kind/Backend */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  {label('AGENT NAME *')}
                  <input value={form.agent_name}
                    onChange={e => setForm(f => ({ ...f, agent_name: e.target.value }))}
                    placeholder="e.g. Threat Intel Agent"
                    style={inputStyle} />
                </div>
                <div>
                  {label('AGENT KIND')}
                  <div style={{
                    height: 38, padding: '0 12px', display: 'flex', alignItems: 'center',
                    background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                    fontSize: 12, fontFamily: 'var(--font-mono)', letterSpacing: '0.05em',
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
                      {label('LLM PROVIDER ID *')}
                      <input value={form.llm_provider_id || ''}
                        onChange={e => setForm(f => ({ ...f, llm_provider_id: e.target.value }))}
                        placeholder="Provider ID (e.g. 1)"
                        style={inputStyle} />
                    </div>
                    <div>
                      {label('LLM MODEL')}
                      <input value={form.llm_model || ''}
                        onChange={e => setForm(f => ({ ...f, llm_model: e.target.value }))}
                        placeholder="auto / gpt-4o / etc."
                        style={inputStyle} />
                    </div>
                  </div>

                  {/* Tool loop settings */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div>
                      {label('TOOL LOOP MAX STEPS')}
                      <input type="number" value="8"
                        readOnly
                        style={{ ...inputStyle, color: 'var(--text-dim)' }} />
                    </div>
                    <div>
                      {label('MEMORY WINDOW')}
                      <input type="number" value="20"
                        readOnly
                        style={{ ...inputStyle, color: 'var(--text-dim)' }} />
                    </div>
                  </div>
                </>
              )}

              {/* Backend Type (external only) */}
              {form.backend_type !== '__internal__' && (
                <div>
                  {label('BACKEND TYPE')}
                  <select value={form.backend_type}
                    onChange={e => setForm(f => ({ ...f, backend_type: e.target.value }))}
                    style={{ ...inputStyle, height: 38 }}>
                    <option value="openclaw">OPENCLAW (推荐)</option>
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
                  placeholder="这个 Agent 的职责..."
                  style={inputStyle} />
              </div>

              {/* Endpoint URL — 仅非 OpenClaw */}
              {form.backend_type !== 'openclaw' && form.backend_type !== '__internal__' && (
                <div>
                  {label('ENDPOINT URL *')}
                  <input value={form.endpoint_url}
                    onChange={e => setForm(f => ({ ...f, endpoint_url: e.target.value }))}
                    placeholder="http://your-agent-host:8001"
                    style={inputStyle} />
                  <div style={{ marginTop: 4, fontSize: 9, color: 'var(--text-dim)' }}>
                    需要暴露 POST /execute 和 GET /health 端点
                  </div>
                </div>
              )}

              {/* Permission */}
              <div>
                {label('PERMISSION LEVEL')}
                <select value={form.permission_level}
                  onChange={e => setForm(f => ({ ...f, permission_level: e.target.value }))}
                  style={{ ...inputStyle, height: 38 }}>
                  <option value="low">LOW — 无需审批</option>
                  <option value="medium">MEDIUM — 可能触发审批</option>
                  <option value="high">HIGH — 始终需要 Admin 审批</option>
                </select>
              </div>

              {/* System Prompt */}
              <div>
                {label('SYSTEM PROMPT（可选，覆盖 Agent 默认提示词）')}
                <textarea value={form.system_prompt}
                  onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                  placeholder="你是 CyberGuard 的威胁情报专家，负责..."
                  rows={3}
                  style={{ ...inputStyle, height: 'auto', padding: '8px 12px', resize: 'vertical' }} />
              </div>

              {/* OpenClaw Guide */}
              {form.backend_type === 'openclaw' && (
                <OpenClawGuide
                  apiKey={createdApiKey || undefined}
                  onRequestKey={editing ? async () => {
                    try {
                      const res = await (api as any).regenAgentApiKey(editing) as { api_key?: string }
                      if (res?.api_key) setCreatedApiKey(res.api_key)
                    } catch (e: any) {
                      alert(e?.message || '生成 Key 失败')
                    }
                  } : undefined}
                />
              )}

            </div>

            {/* Footer buttons */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', display: 'flex', gap: 12 }}>
              {createdApiKey ? (
                <button onClick={() => { setShowForm(false); setCreatedApiKey(null) }}
                  style={{
                    flex: 1, height: 40, border: '1px solid var(--accent-border)',
                    background: 'var(--accent)', color: '#000',
                    fontWeight: 700, fontSize: 11, letterSpacing: '0.15em', cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                  }}>
                  我已保存 KEY，关闭
                </button>
              ) : (
                <>
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
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
