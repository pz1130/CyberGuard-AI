import { useEffect, useState, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import PageHeader from '../components/PageHeader'
import { Plus, Webhook as WebhookIcon, Loader2, Trash, Pencil, Copy, Key, ArrowDown, ArrowUp } from 'lucide-react'
import { SearchContext } from '../context/SearchContext'
import Modal from '../components/Modal'

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

// Legacy helpers kept only for this file's form (will be removed in future pass)
const label = (text: string) => (
  <label className="form-label">{text}</label>
)

export default function Webhooks() {
  const { t } = useTranslation()
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

  const { searchTarget, setSearchTarget } = useContext(SearchContext)
  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'webhooks') return
    const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('search-highlight')
    }
    const t = setTimeout(() => setSearchTarget(null), 2000)
    return () => clearTimeout(t)
  }, [searchTarget, setSearchTarget])

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
      <PageHeader
        eyebrow="EVENT BUS"
        title={t('webhooks.title').toUpperCase()}
        actions={
          <button onClick={openCreate} className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Plus size={13} /> NEW WEBHOOK
          </button>
        }
      />

      {/* Description hint */}
      <div className="card" style={{
        padding: '12px 16px', marginBottom: 16,
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
        <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 48, gap: 12 }}>
          <WebhookIcon size={24} style={{ color: 'var(--text-dim)' }} />
          <div style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>NO WEBHOOKS</div>
          <button onClick={openCreate} className="btn btn-ghost" style={{ fontSize: 12 }}>CREATE FIRST WEBHOOK</button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {items.map(w => (
            <div key={w.id} data-item-id={w.id} className="item-card">
              {/* Name + direction badge, with pip like Agents */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                  <span className="item-card-pip" style={{ background: dirColor(w.direction) }} />
                  <span className="item-card-title">{w.name}</span>
                </div>
                <span className="item-card-badge" style={{ color: dirColor(w.direction) }}>
                  {w.direction === 'incoming' ? <ArrowDown size={9} /> : <ArrowUp size={9} />}
                  {w.direction.toUpperCase()}
                </span>
              </div>

              {w.description && (
                <div className="item-card-desc">{w.description}</div>
              )}

              {/* URL display */}
              {w.direction === 'outgoing' && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                  → {w.outgoing_url}
                </div>
              )}
              {w.direction === 'incoming' && (
                <div style={{ fontSize: 12, color: w.has_token ? 'var(--text-muted)' : '#f59e0b' }}>
                  {w.has_token ? `← ${w.incoming_url}` : '⚠ no token (regenerate)'}
                </div>
              )}

              {/* Events / secret / disabled tags */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {w.outgoing_events?.map(e => (
                  <span key={e} className="item-card-badge" style={{ background: 'var(--accent-dim)', borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                    {e}
                  </span>
                ))}
                {w.has_secret && <span className="item-card-badge" style={{ borderColor: 'var(--cyan)', color: 'var(--cyan)' }}>HMAC</span>}
                {!w.is_active && <span className="item-card-badge" style={{ borderColor: 'var(--text-dim)', color: 'var(--text-dim)' }}>DISABLED</span>}
              </div>

              {/* Stats */}
              <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-dim)' }}>
                <span>fired {w.trigger_count}</span>
                <span style={{ color: 'var(--accent)' }}>ok {w.success_count}</span>
                <span style={{ color: w.failure_count ? '#f87171' : 'var(--text-dim)' }}>fail {w.failure_count}</span>
                {w.last_triggered_at && <span>last {new Date(w.last_triggered_at).toLocaleTimeString()}</span>}
              </div>

              {w.last_error && (
                <div style={{
                  padding: '6px 10px',
                  background: 'var(--bg-base)', border: `1px solid rgba(255,60,60,0.3)`,
                  borderRadius: 'var(--radius-md)',
                  fontSize: 12, color: '#f87171',
                }}>
                  {w.last_error.slice(0, 200)}
                </div>
              )}

              {testResult[w.id] && (
                <div style={{
                  padding: '6px 10px',
                  background: 'var(--bg-base)', border: `1px solid ${testResult[w.id].startsWith('✓') ? 'var(--accent-border)' : 'rgba(255,60,60,0.3)'}`,
                  borderRadius: 'var(--radius-md)',
                  fontSize: 12, color: testResult[w.id].startsWith('✓') ? 'var(--accent)' : '#f87171',
                }}>
                  {testResult[w.id]}
                </div>
              )}

              {/* Action row - matching Agents style */}
              <div className="item-card-actions">
                {w.direction === 'outgoing' && (
                  <button onClick={() => test(w.id)} disabled={testing === w.id}
                    className={`item-card-btn ${testing !== w.id ? 'accent' : ''}`}>
                    {testing === w.id ? '…' : 'TEST'}
                  </button>
                )}
                {w.direction === 'incoming' && (
                  <button onClick={() => regen(w.id)}
                    className="item-card-btn">
                    <Key size={11} /> REGEN
                  </button>
                )}

                <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                  <button onClick={() => openEdit(w)} className="item-card-icon-btn" title="Edit">
                    <Pencil size={13} />
                  </button>
                  <button onClick={() => del(w.id)} className="item-card-icon-btn danger" title="Delete">
                    <Trash size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form modal */}
      {showForm && (
        <Modal
          width={600}
          eyebrow="WEBHOOK CONFIGURATION"
          title={editing ? 'EDIT WEBHOOK' : 'NEW WEBHOOK'}
          closeOnOverlay={!createdToken}
          onClose={() => { if (!createdToken) setShowForm(false) }}
          footer={createdToken ? (
            <button onClick={() => { setShowForm(false); setCreatedToken(null); setCreatedUrl(null) }}
              className="btn btn-primary" style={{ flex: 1 }}>
              我已保存 TOKEN，关闭
            </button>
          ) : (
            <>
              <button onClick={() => setShowForm(false)} className="btn btn-secondary">
                CANCEL
              </button>
              <button onClick={submit} className="btn btn-primary">
                {editing ? 'SAVE' : 'CREATE'}
              </button>
            </>
          )}
        >
          {/* Created token banner — only after a successful create */}
              {createdToken && createdUrl && (
                <div style={{ padding: '12px', background: 'rgba(0,255,65,0.06)', border: '1px solid var(--accent-border)', borderLeft: '3px solid var(--accent)' }}>
                  <div style={{ fontSize: 12, color: 'var(--accent)', letterSpacing: '0.1em', marginBottom: 8 }}>⚠ TOKEN SHOWN ONLY ONCE — COPY NOW</div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
                    <div style={{ flex: 1, padding: '6px 10px', background: 'var(--bg-base)', fontSize: 12, color: 'var(--accent)', wordBreak: 'break-all', border: '1px solid var(--accent-border)' }}>
                      {createdUrl.replace('<TOKEN>', createdToken)}
                    </div>
                    <button
                      onClick={() => cp(createdUrl.replace('<TOKEN>', createdToken), 'url')}
                      className="btn btn-sm"
                      style={{
                        border: '1px solid var(--accent-border)',
                        background: copied === 'url' ? 'var(--accent)' : 'transparent',
                        color: copied === 'url' ? '#000' : 'var(--accent)',
                        paddingLeft: 10, paddingRight: 10,
                      }}
                    >
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
                        placeholder="splunk-alerts" className="form-input" />
                    </div>
                    <div>
                      {label('DIRECTION')}
                      <select value={form.direction} disabled={!!editing}
                        onChange={e => setForm(f => ({ ...f, direction: e.target.value as 'incoming' | 'outgoing' }))}
                        className="form-input" style={{ opacity: editing ? 0.5 : 1 }}>
                        <option value="incoming">INCOMING (others → us)</option>
                        <option value="outgoing">OUTGOING (us → others)</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    {label('DESCRIPTION')}
                    <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                      placeholder="What this webhook is for..." className="form-input" />
                  </div>

                  {form.direction === 'outgoing' && (
                    <>
                      <div>
                        {label('TARGET URL *')}
                        <input value={form.outgoing_url} onChange={e => setForm(f => ({ ...f, outgoing_url: e.target.value }))}
                          placeholder="https://hooks.slack.com/services/..." className="form-input" />
                      </div>
                      <div>
                        {label('SUBSCRIBE TO EVENTS')}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {SUPPORTED_EVENTS.map(ev => (
                            <label key={ev} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                              <input
                                type="checkbox"
                                checked={form.outgoing_events.includes(ev)}
                                onChange={e => setForm(f => ({
                                  ...f,
                                  outgoing_events: e.target.checked
                                    ? [...f.outgoing_events, ev]
                                    : f.outgoing_events.filter(x => x !== ev),
                                }))}
                                style={{ accentColor: 'var(--accent)' }}
                              />
                              <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>{ev}</span>
                              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>— Human-in-the-Loop 审批请求创建时</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      <div>
                        {label('HMAC SECRET（可选，启用签名）')}
                        <input value={form.outgoing_secret} onChange={e => setForm(f => ({ ...f, outgoing_secret: e.target.value }))}
                          placeholder={editing ? '留空 = 不变 / 输入 = 替换' : 'whsec_...'}
                          className="form-input" />
                        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-dim)' }}>
                          填了即会在每次请求加 <code>X-CyberGuard-Signature: sha256=&lt;hex&gt;</code> 头
                        </div>
                      </div>
                    </>
                  )}

                  {form.direction === 'incoming' && !editing && (
                    <div className="card" style={{ background: 'var(--bg-base)', borderLeft: '3px solid var(--cyan)', padding: '10px 12px', fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.7 }}>
                      创建后会生成一条 <code>POST /api/v1/webhooks/incoming/&lt;token&gt;</code> 公网端点。
                      外部服务 POST JSON 体，其中 <code>message</code> 字段会作为 Master Agent 的用户输入。
                      Token 明文**只显示一次**。
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox"
                      id="wh_active"
                      checked={form.is_active}
                      onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))}
                      style={{ accentColor: 'var(--accent)' }}
                    />
                    <label htmlFor="wh_active" style={{ fontSize: 13, color: 'var(--text-primary)', cursor: 'pointer' }}>ACTIVE</label>
                  </div>
                </>
              )}
        </Modal>
      )}
    </div>
  )
}
