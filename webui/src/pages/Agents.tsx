import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { Plus, Loader2, Cpu, Trash, Pencil, Copy, Wifi, WifiOff, Key } from 'lucide-react'

interface Agent {
  id?: string
  agent_name?: string
  name?: string
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
}

interface FormState {
  agent_name: string
  backend_type: string
  description: string
  endpoint_url: string
  system_prompt: string
  permission_level: string
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

// ── OpenClaw setup guide ───────────────────────────────────────────────────────
function OpenClawGuide({ apiKey }: { apiKey?: string }) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  const copy = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(id); setTimeout(() => setCopiedKey(null), 2000)
    })
  }

  const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host
  const key = apiKey || 'YOUR_API_KEY'

  const pythonScript = `import requests, time

CYBERGUARD = "http://${host}"   # 改成你的 CyberGuard 地址
API_KEY    = "${key}"

headers = {"X-Api-Key": API_KEY}

def poll():
    r = requests.get(f"{CYBERGUARD}/api/v1/gateway/poll", headers=headers, timeout=10)
    return r.json().get("messages", [])

def report(message_id, result):
    requests.post(f"{CYBERGUARD}/api/v1/gateway/report", headers=headers,
                  json={"message_id": message_id, "result": result}, timeout=10)

def heartbeat():
    requests.post(f"{CYBERGUARD}/api/v1/gateway/heartbeat", headers=headers, timeout=5)

print("OpenClaw worker started, polling every 10s ...")
tick = 0
while True:
    try:
        tasks = poll()
        for task in tasks:
            print(f"[TASK] {task['content']}")
            # ↓ 把这里替换成你的实际执行逻辑
            result = f"已收到任务：{task['content']}"
            report(task["id"], result)
            print(f"[DONE] message_id={task['id']}")
        if tick % 6 == 0:   # 每 60s 发一次心跳
            heartbeat()
        tick += 1
    except Exception as e:
        print(f"[ERR] {e}")
    time.sleep(10)`

  const installCmd = `pip install requests\npython openclaw_worker.py`

  const s: React.CSSProperties = {
    fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.75,
  }
  const stepLabel = (n: string, title: string) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      <div style={{
        width: 20, height: 20, borderRadius: 2, flexShrink: 0,
        background: 'rgba(0,255,65,0.12)', border: '1px solid var(--accent-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 9, color: 'var(--accent)', fontWeight: 700, fontFamily: 'var(--font-mono)',
      }}>{n}</div>
      <span style={{ fontSize: 10, color: 'var(--text-primary)', letterSpacing: '0.08em', fontWeight: 600 }}>{title}</span>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        background: 'rgba(0,255,65,0.04)',
        border: '1px solid var(--accent-border)', borderBottom: 'none',
        fontSize: 10, color: 'var(--accent)', letterSpacing: '0.12em', fontWeight: 700,
      }}>
        ◆ OPENCLAW 接入指南
      </div>

      <div style={{
        padding: '16px', background: 'var(--bg-base)',
        border: '1px solid var(--accent-border)',
        display: 'flex', flexDirection: 'column', gap: 18,
      }}>

        {/* Concept */}
        <div style={{
          ...s, padding: '10px 12px',
          background: 'var(--bg-elevated)', border: '1px solid var(--border)',
          borderLeft: '3px solid var(--accent)',
        }}>
          <strong style={{ color: 'var(--text-primary)' }}>工作原理：</strong><br />
          你在自己的服务器上运行一个 <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>openclaw_worker.py</span> 脚本。
          它每隔几秒来 CyberGuard 取任务，在<strong>本地执行</strong>后把结果汇报回来。
          <br />CyberGuard 无需知道你的服务器地址，你也不需要开放任何端口。
        </div>

        {/* Step 1 — save key */}
        <div>
          {stepLabel('1', '保存 API Key（只出现这一次）')}
          {apiKey ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                flex: 1, padding: '8px 12px',
                background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)',
                fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)',
                letterSpacing: '0.04em', wordBreak: 'break-all',
              }}>{apiKey}</div>
              <button onClick={() => copy(apiKey, 'key')} style={{
                padding: '8px 12px', border: '1px solid var(--accent-border)',
                background: copiedKey === 'key' ? 'var(--accent)' : 'transparent',
                color: copiedKey === 'key' ? '#000' : 'var(--accent)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                fontSize: 10, letterSpacing: '0.1em', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap',
              }}>
                <Copy size={11} /> {copiedKey === 'key' ? 'COPIED' : 'COPY'}
              </button>
            </div>
          ) : (
            <div style={{
              ...s, padding: '8px 12px',
              background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            }}>
              Key 将在点击「创建」后出现，<strong style={{ color: 'var(--text-primary)' }}>仅显示一次</strong>。
              若忘记保存，可用卡片上的 <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>REGEN KEY</span> 重新生成。
            </div>
          )}
        </div>

        {/* Step 2 — create file */}
        <div>
          {stepLabel('2', '在你的服务器上创建 openclaw_worker.py')}
          <div style={{ ...s, marginBottom: 8 }}>
            新建一个文件，把下面的代码全部复制进去，然后把第 2 行的地址改成你的 CyberGuard 实际地址（Key 已自动填入）：
          </div>
          <CodeBlock text={pythonScript} onCopy={(t) => copy(t, 'script')} copied={copiedKey === 'script'} />
        </div>

        {/* Step 3 — run */}
        <div>
          {stepLabel('3', '安装依赖并运行')}
          <div style={{ ...s, marginBottom: 8 }}>
            在终端里执行（需要 Python 3.7+）：
          </div>
          <CodeBlock text={installCmd} onCopy={(t) => copy(t, 'install')} copied={copiedKey === 'install'} />
          <div style={{
            ...s, marginTop: 8, padding: '8px 12px',
            background: 'var(--bg-elevated)', border: '1px solid var(--border)',
          }}>
            看到 <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>OpenClaw worker started</span> 输出后，
            回到 CyberGuard 刷新此页面，Agent 卡片右上角会变成{' '}
            <span style={{ color: 'var(--accent)' }}>● ONLINE</span>，接入完成。
          </div>
        </div>

        {/* Step 4 — customize */}
        <div>
          {stepLabel('4', '替换执行逻辑（关键）')}
          <div style={{
            ...s, padding: '10px 12px',
            background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            borderLeft: '3px solid #f59e0b',
          }}>
            脚本里标有 <span style={{ color: '#f59e0b', fontFamily: 'var(--font-mono)' }}>↓ 把这里替换成你的实际执行逻辑</span> 的地方，
            就是你需要修改的位置。<br /><br />
            <strong style={{ color: 'var(--text-primary)' }}>举例：</strong>
            <ul style={{ margin: '6px 0 0 16px', padding: 0, lineHeight: 2 }}>
              <li>调用你的 OpenClaw 扫描工具，把结果字符串赋值给 <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>result</span></li>
              <li>调用本地 AI 模型处理任务内容（<span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>task['content']</span> 就是任务文本）</li>
              <li>运行任意 shell 命令，把输出作为 result 返回</li>
            </ul>
          </div>
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
  })
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [regenLoading, setRegenLoading] = useState<string | null>(null)
  const [regenKey, setRegenKey] = useState<Record<string, string>>({})

  const load = async () => {
    try {
      const data = await api.getAgents() as any
      const list: Agent[] = Array.isArray(data) ? data : (data?.agents || [])
      setItems(list)
    } catch { setItems([]) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    setCreatedApiKey(null)
    setForm({ agent_name: '', backend_type: 'openclaw', description: '', endpoint_url: '', system_prompt: '', permission_level: 'medium' })
    setShowForm(true)
  }

  const openEdit = (a: Agent) => {
    setEditing(a.id!)
    setCreatedApiKey(null)
    setForm({
      agent_name: a.agent_name || a.name || '',
      backend_type: a.backend_type || 'openclaw',
      description: a.description || '',
      endpoint_url: a.endpoint_url || '',
      system_prompt: a.system_prompt || '',
      permission_level: a.permission_level || 'medium',
    })
    setShowForm(true)
  }

  const submit = async () => {
    if (!form.agent_name) return
    try {
      const payload: Record<string, any> = {
        agent_name: form.agent_name,
        backend_type: form.backend_type,
        description: form.description || undefined,
        system_prompt: form.system_prompt || undefined,
        permission_level: form.permission_level,
      }
      // endpoint_url 仅非 OpenClaw 后端需要
      if (form.backend_type !== 'openclaw' && form.endpoint_url) {
        payload.endpoint_url = form.endpoint_url
      }

      if (editing) {
        await api.updateAgent(editing, payload)
        setShowForm(false)
      } else {
        const res = await api.createAgent(payload) as any
        // 如果是 OpenClaw，显示一次性 API Key
        if (res?.api_key) {
          setCreatedApiKey(res.api_key)
          // 不关闭弹窗，让用户看到并复制 Key
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
        <button onClick={openCreate} style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px', height: 36,
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
          <Cpu size={24} style={{ color: 'var(--text-dim)' }} />
          <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO ACTIVE AGENTS</div>
          <button onClick={openCreate} style={{ fontSize: 10, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', letterSpacing: '0.1em' }}>
            + DEPLOY FIRST AGENT
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {items.map(a => {
            const bc = BACKEND_COLORS[a.backend_type || 'custom']
            const isOpenClaw = a.backend_type === 'openclaw'
            const online = a.is_online || false
            const thisRegenKey = regenKey[a.id!]

            return (
              <div key={a.id} style={{
                padding: 18, background: 'var(--bg-surface)',
                border: '1px solid var(--border-bright)',
                borderLeft: `3px solid ${bc}`,
              }}>
                {/* Name + badge */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em' }}>
                    {agentName(a)}
                  </div>
                  <div style={{
                    padding: '2px 7px', border: `1px solid ${bc}`,
                    fontSize: 8, letterSpacing: '0.15em', color: bc, background: 'var(--bg-base)',
                  }}>
                    {(a.backend_type || 'CUSTOM').toUpperCase()}
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
                {editing ? 'EDIT AGENT' : 'DEPLOY NEW AGENT'}
              </h3>
            </div>

            <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>

              {/* Name + Backend */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  {label('AGENT NAME *')}
                  <input value={form.agent_name}
                    onChange={e => setForm(f => ({ ...f, agent_name: e.target.value }))}
                    placeholder="e.g. Threat Intel Agent"
                    style={inputStyle} />
                </div>
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
              </div>

              {/* Description */}
              <div>
                {label('DESCRIPTION')}
                <input value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="这个 Agent 的职责..."
                  style={inputStyle} />
              </div>

              {/* Endpoint URL — 仅非 OpenClaw */}
              {form.backend_type !== 'openclaw' && (
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
                <OpenClawGuide apiKey={createdApiKey || undefined} />
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
