import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { Plus, Webhook as WebhookIcon, Loader2, Trash, Pencil, Copy, Key, ArrowDown, ArrowUp } from 'lucide-react'

interface Webhook {
  id: number
  name: string
  direction: 'incoming' | 'outgoing'
  description?: string
  is_active: boolean
  has_token?: boolean
  incoming_url?: string
  outgoing_url?: string
  outgoing_events?: string[]
  has_secret?: boolean
  last_triggered_at?: string
  trigger_count: number
  success_count: number
  failure_count: number
  last_error?: string
  plaintext_token?: string
  created_at: string
  updated_at: string
}

const SUPPORTED_EVENTS = ['approval.required'] as const
type EventName = typeof SUPPORTED_EVENTS[number]

const inputStyle: React.CSSProperties = {
  width: '100%', height: 36, padding: '0 12px',
  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
  color: 'var(--text-primary)', fontSize: 14, letterSpacing: '0.05em',
  fontFamily: 'var(--font-mono)', boxSizing: 'border-box',
}

const label = (text: string) => (
  <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6 }}>
    {text}
  </label>
)

export default function Webhooks() {
  const [items, setItems] = useState<Webhook[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [createdUrl, setCreatedUrl] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: '',
    direction: 'incoming' as 'incoming' | 'outgoing',
    description: '',
    is_active: true,
    outgoing_url: '',
    outgoing_secret: '',
    outgoing_events: [] as EventName[],
  })
  const [copied, setCopied] = useState<string | null>(null)
  const [testing, setTesting] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<Record<number, string>>({})

  const cp = (text: string, tag: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(tag); setTimeout(() => setCopied(null), 1800)
    })
  }

  const load = async () => {
    try {
      const data = await api.getWebhooks() as { webhooks: Webhook[] }
      setItems(data?.webhooks || [])
    } catch { setItems([]) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEditing(null)
    setCreatedToken(null)
    setCreatedUrl(null)
    setForm({
      name: '', direction: 'incoming', description: '', is_active: true,
      outgoing_url: '', outgoing_secret: '', outgoing_events: [],
    })
    setShowForm(true)
  }

  const openEdit = (w: Webhook) => {
    setEditing(w.id)
    setCreatedToken(null)
    setCreatedUrl(null)
    setForm({
      name: w.name,
      direction: w.direction,
      description: w.description || '',
      is_active: w.is_active,
      outgoing_url: w.outgoing_url || '',
      outgoing_secret: '',
      outgoing_events: (w.outgoing_events || []) as EventName[],
    })
    setShowForm(true)
  }

  const submit = async () => {
    if (!form.name) return alert('Name required')
    try {
      if (editing) {
        const payload: any = {
          name: form.name,
          description: form.description || undefined,
          is_active: form.is_active,
        }
        if (form.direction === 'outgoing') {
          if (form.outgoing_url) payload.outgoing_url = form.outgoing_url
          payload.outgoing_events = form.outgoing_events
          if (form.outgoing_secret) payload.outgoing_secret = form.outgoing_secret
        }
        await api.updateWebhook(editing, payload)
        setShowForm(false)
      } else {
        const payload: any = {
          name: form.name,
          direction: form.direction,
          description: form.description || undefined,
          is_active: form.is_active,
        }
        if (form.direction === 'outgoing') {
          if (!form.outgoing_url) return alert('outgoing_url required')
          if (form.outgoing_events.length === 0) return alert('Pick at least one event')
          payload.outgoing_url = form.outgoing_url
          payload.outgoing_events = form.outgoing_events
          if (form.outgoing_secret) payload.outgoing_secret = form.outgoing_secret
        }
        const res = await api.createWebhook(payload) as Webhook
        if (res?.plaintext_token && res?.incoming_url) {
          setCreatedToken(res.plaintext_token)
          setCreatedUrl(res.incoming_url)
        } else {
          setShowForm(false)
        }
      }
      load()
    } catch (e: any) { alert(e.message || String(e)) }
  }

  const del = async (id: number) => {
    if (!confirm('Delete webhook?')) return
    await api.deleteWebhook(id); load()
  }

  const regen = async (id: number) => {
    if (!confirm('Regenerate token? Old token will stop working immediately.')) return
    try {
      const res = await api.regenWebhookToken(id) as Webhook
      if (res?.plaintext_token) {
        setEditing(id)
        setCreatedToken(res.plaintext_token)
        setCreatedUrl(res.incoming_url || '')
        setShowForm(true)
        // Populate form for context
        setForm({
          name: res.name, direction: 'incoming',
          description: res.description || '', is_active: res.is_active,
          outgoing_url: '', outgoing_secret: '', outgoing_events: [],
        })
      }
      load()
    } catch (e: any) { alert(e.message) }
  }

  const test = async (id: number) => {
    setTesting(id)
    try {
      const res = await api.testWebhook(id) as any
      setTestResult(r => ({ ...r, [id]: res.success
        ? `✓ ${res.status_code} · ${res.latency_ms}ms`
        : `✗ ${res.error || res.status_code}` }))
    } catch (e: any) {
      setTestResult(r => ({ ...r, [id]: `✗ ${e.message}` }))
    } finally { setTesting(null) }
  }

  const dirColor = (d: string) => d === 'incoming' ? 'var(--cyan)' : 'var(--accent)'

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>EVENT BUS</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>WEBHOOKS</h1>
        </div>
        <button onClick={openCreate} style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px', height: 36,
          background: 'var(--accent)', border: '1px solid var(--accent-border)',
          color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em',
          cursor: 'pointer', fontFamily: 'var(--font-mono)',
        }}>
          <Plus size={13} /> NEW WEBHOOK
        </button>
      </div>

      {/* Description hint */}
      <div style={{
        padding: '10px 14px', marginBottom: 16,
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.7,
      }}>
        <span style={{ color: 'var(--cyan)' }}>◆ INCOMING</span>：外部服务通过 token URL 调用 CyberGuard（请求转给 Master Agent 处理）。
        　<span style={{ color: 'var(--accent)' }}>◆ OUTGOING</span>：订阅事件（如 <code>approval.required</code>），CyberGuard 主动 POST 到你的 URL，可选 HMAC 签名。
      </div>

      {/* List */}
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
        </div>
      ) : items.length === 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 60, gap: 12 }}>
          <WebhookIcon size={24} style={{ color: 'var(--text-dim)' }} />
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO WEBHOOKS</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 16 }}>
          {items.map(w => (
            <div key={w.id} style={{
              padding: 16, background: 'var(--bg-surface)',
              border: '1px solid var(--border-bright)',
              borderLeft: `3px solid ${dirColor(w.direction)}`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>{w.name}</div>
                  {w.description && <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>{w.description}</div>}
                </div>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '2px 7px', border: `1px solid ${dirColor(w.direction)}`,
                  fontSize: 10, letterSpacing: '0.15em', color: dirColor(w.direction),
                }}>
                  {w.direction === 'incoming' ? <ArrowDown size={9} /> : <ArrowUp size={9} />}
                  {w.direction.toUpperCase()}
                </div>
              </div>

              {/* URL display */}
              {w.direction === 'outgoing' && (
                <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: 6, wordBreak: 'break-all' }}>
                  → {w.outgoing_url}
                </div>
              )}
              {w.direction === 'incoming' && (
                <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: w.has_token ? 'var(--text-muted)' : '#f59e0b', marginBottom: 6 }}>
                  {w.has_token ? `← ${w.incoming_url}` : '⚠ no token (regenerate)'}
                </div>
              )}

              {/* Events / secret tags */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                {w.outgoing_events?.map(e => (
                  <span key={e} style={{ fontSize: 11, padding: '2px 6px', background: 'var(--accent-dim)', color: 'var(--accent)', letterSpacing: '0.05em' }}>{e}</span>
                ))}
                {w.has_secret && <span style={{ fontSize: 11, padding: '2px 6px', border: '1px solid var(--cyan)', color: 'var(--cyan)' }}>HMAC</span>}
                {!w.is_active && <span style={{ fontSize: 11, padding: '2px 6px', border: '1px solid var(--text-dim)', color: 'var(--text-dim)' }}>DISABLED</span>}
              </div>

              {/* Stats */}
              <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
                <span>fired {w.trigger_count}</span>
                <span style={{ color: 'var(--accent)' }}>ok {w.success_count}</span>
                <span style={{ color: w.failure_count ? '#f87171' : 'var(--text-dim)' }}>fail {w.failure_count}</span>
                {w.last_triggered_at && <span>last {new Date(w.last_triggered_at).toLocaleTimeString()}</span>}
              </div>

              {w.last_error && (
                <div style={{ fontSize: 11, color: '#f87171', fontFamily: 'var(--font-mono)', marginBottom: 8, padding: '4px 8px', background: 'rgba(248,113,113,0.08)' }}>
                  {w.last_error.slice(0, 200)}
                </div>
              )}

              {testResult[w.id] && (
                <div style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)', marginBottom: 8, padding: '4px 8px',
                  background: testResult[w.id].startsWith('✓') ? 'var(--accent-dim)' : 'rgba(248,113,113,0.08)',
                  color: testResult[w.id].startsWith('✓') ? 'var(--accent)' : '#f87171',
                }}>{testResult[w.id]}</div>
              )}

              {/* Actions */}
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {w.direction === 'outgoing' && (
                  <button onClick={() => test(w.id)} disabled={testing === w.id}
                    style={{ padding: '0 10px', height: 26, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--accent)', fontSize: 11, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                    {testing === w.id ? '...' : 'TEST'}
                  </button>
                )}
                {w.direction === 'incoming' && (
                  <button onClick={() => regen(w.id)}
                    style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '0 10px', height: 26, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 11, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                    <Key size={10} /> REGEN
                  </button>
                )}
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                  <button onClick={() => openEdit(w)} style={{ padding: 4, color: 'var(--text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
                    <Pencil size={11} />
                  </button>
                  <button onClick={() => del(w.id)} style={{ padding: 4, color: '#f87171', cursor: 'pointer', background: 'none', border: 'none' }}>
                    <Trash size={11} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form modal */}
      {showForm && (
        <div onClick={e => e.target === e.currentTarget && !createdToken && setShowForm(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: 40, overflowY: 'auto', zIndex: 100 }}>
          <div style={{ width: '100%', maxWidth: 600, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
            <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: 11, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 4 }}>WEBHOOK CONFIGURATION</div>
              <h3 style={{ fontSize: 18, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)', margin: 0 }}>
                {editing ? 'EDIT WEBHOOK' : 'NEW WEBHOOK'}
              </h3>
            </div>

            <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Created token banner — only after a successful create */}
              {createdToken && createdUrl && (
                <div style={{ padding: '12px', background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)', borderLeft: '3px solid var(--accent)' }}>
                  <div style={{ fontSize: 12, color: 'var(--accent)', letterSpacing: '0.1em', marginBottom: 8 }}>⚠ TOKEN SHOWN ONLY ONCE — COPY NOW</div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                    <div style={{ flex: 1, padding: '6px 10px', background: 'var(--bg-base)', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--accent)', wordBreak: 'break-all', border: '1px solid var(--accent-border)' }}>
                      {createdUrl.replace('<TOKEN>', createdToken)}
                    </div>
                    <button onClick={() => cp(createdUrl.replace('<TOKEN>', createdToken), 'url')}
                      style={{ padding: '6px 10px', border: '1px solid var(--accent-border)', background: copied === 'url' ? 'var(--accent)' : 'transparent', color: copied === 'url' ? '#000' : 'var(--accent)', fontSize: 11, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Copy size={10} /> {copied === 'url' ? 'COPIED' : 'COPY URL'}
                    </button>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.6 }}>
                    将上面这条 URL 配置到外部服务（curl/SIEM/Slack action 等），POST JSON 体例：
                    <code style={{ display: 'block', marginTop: 4, padding: 6, background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
                      {'{"message": "扫描 192.168.1.0/24"}'}
                    </code>
                  </div>
                </div>
              )}

              {!createdToken && (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                    <div>
                      {label('NAME *')}
                      <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                        placeholder="splunk-alerts" style={inputStyle} />
                    </div>
                    <div>
                      {label('DIRECTION')}
                      <select value={form.direction} disabled={!!editing}
                        onChange={e => setForm(f => ({ ...f, direction: e.target.value as 'incoming' | 'outgoing' }))}
                        style={{ ...inputStyle, opacity: editing ? 0.5 : 1 }}>
                        <option value="incoming">INCOMING (others → us)</option>
                        <option value="outgoing">OUTGOING (us → others)</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    {label('DESCRIPTION')}
                    <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                      placeholder="What this webhook is for..." style={inputStyle} />
                  </div>

                  {form.direction === 'outgoing' && (
                    <>
                      <div>
                        {label('TARGET URL *')}
                        <input value={form.outgoing_url} onChange={e => setForm(f => ({ ...f, outgoing_url: e.target.value }))}
                          placeholder="https://hooks.slack.com/services/..." style={inputStyle} />
                      </div>
                      <div>
                        {label('SUBSCRIBE TO EVENTS')}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {SUPPORTED_EVENTS.map(ev => (
                            <label key={ev} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                              <input type="checkbox" checked={form.outgoing_events.includes(ev)}
                                onChange={e => setForm(f => ({
                                  ...f,
                                  outgoing_events: e.target.checked
                                    ? [...f.outgoing_events, ev]
                                    : f.outgoing_events.filter(x => x !== ev),
                                }))}
                                style={{ accentColor: 'var(--accent)' }} />
                              <span style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{ev}</span>
                              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>— Human-in-the-Loop 审批请求创建时</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      <div>
                        {label('HMAC SECRET（可选，启用签名）')}
                        <input value={form.outgoing_secret} onChange={e => setForm(f => ({ ...f, outgoing_secret: e.target.value }))}
                          placeholder={editing ? '留空 = 不变 / 输入 = 替换' : 'whsec_...'}
                          style={inputStyle} />
                        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-dim)' }}>
                          填了即会在每次请求加 <code>X-CyberGuard-Signature: sha256=&lt;hex&gt;</code> 头
                        </div>
                      </div>
                    </>
                  )}

                  {form.direction === 'incoming' && !editing && (
                    <div style={{ padding: '10px 12px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderLeft: '3px solid var(--cyan)', fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.7 }}>
                      创建后会生成一条 <code>POST /api/v1/webhooks/incoming/&lt;token&gt;</code> 公网端点。
                      外部服务 POST JSON 体，其中 <code>message</code> 字段会作为 Master Agent 的用户输入。
                      Token 明文**只显示一次**。
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" id="wh_active" checked={form.is_active}
                      onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))}
                      style={{ accentColor: 'var(--accent)' }} />
                    <label htmlFor="wh_active" style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', cursor: 'pointer' }}>ACTIVE</label>
                  </div>
                </>
              )}
            </div>

            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', display: 'flex', gap: 12 }}>
              {createdToken ? (
                <button onClick={() => { setShowForm(false); setCreatedToken(null); setCreatedUrl(null) }}
                  style={{ flex: 1, height: 40, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                  我已保存 TOKEN，关闭
                </button>
              ) : (
                <>
                  <button onClick={() => setShowForm(false)}
                    style={{ flex: 1, height: 40, border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                    CANCEL
                  </button>
                  <button onClick={submit}
                    style={{ flex: 1, height: 40, border: '1px solid var(--accent-border)', background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.15em', cursor: 'pointer', fontFamily: 'var(--font-mono)' }}>
                    {editing ? 'SAVE' : 'CREATE'}
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
