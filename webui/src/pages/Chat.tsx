import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, RotateCcw, Sparkles, AlertTriangle } from 'lucide-react'
import { api } from '../api/client'
import ReactMarkdown from 'react-markdown'

interface Message { role: 'user' | 'assistant'; content: string; meta?: 'plan' | 'actions' | 'risk' }

interface ProviderOption {
  id: number
  name: string
  provider_type: string
  base_url?: string
  models: string[]
}

const AGENT_TYPE_NAMES: Record<string, string> = {
  threat_intel: '威胁情报',
  log_anomaly: '日志异常',
  vuln_scanner: '漏洞扫描',
  remediation: '修复建议',
  compliance: '合规检查',
  osint: 'OSINT 侦察',
  general: '通用',
}

interface ChatResult {
  message?: string
  response?: string
  reply?: string
  result?: string
  error?: string
  intent?: string
  risk_score?: number
  agent_id?: number
  agent_name?: string
  action_items?: string[]
  task_plan?: Array<{ agent_type: string; task: string; requires_approval?: boolean }>
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const [providers, setProviders] = useState<ProviderOption[]>([])
  const [selectedProvider, setSelectedProvider] = useState<number | null>(null)
  const [selectedModel, setSelectedModel] = useState<string>('')

  useEffect(() => {
    api.getProviders().then((data: any) => {
      const list: ProviderOption[] = data?.providers || []
      setProviders(list)
      if (list.length > 0 && !selectedProvider) {
        setSelectedProvider(list[0].id)
        setSelectedModel(list[0].models?.[0] || '')
      }
    }).catch(() => {})
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  const currentProvider = providers.find(p => p.id === selectedProvider)

  const send = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { role: 'user', content: input }
    setMessages(m => [...m, userMsg])
    setInput('')
    setLoading(true)
    try {
      const res = await api.chat({
        message: userMsg.content,
        provider_id: selectedProvider ?? undefined,
        model: selectedModel || undefined,
      }) as ChatResult
      if (res.error) {
        setMessages(m => [...m, { role: 'assistant', content: `❌ ${res.error}` }])
      } else {
        const text = res.message || res.response || res.reply || res.result || ''
        if (text) setMessages(m => [...m, { role: 'assistant', content: text }])

        if (res.task_plan?.length) {
          const planLines = res.task_plan.map(t =>
            `• **[${AGENT_TYPE_NAMES[t.agent_type] || t.agent_type}]** ${t.task}`
          ).join('\n')
          setMessages(m => [...m, { role: 'assistant', meta: 'plan', content: `任务分解\n\n${planLines}` }])
        }
        if (res.action_items?.length) {
          const actions = res.action_items.map(a => `• ${a}`).join('\n')
          setMessages(m => [...m, { role: 'assistant', meta: 'actions', content: `行动建议\n\n${actions}` }])
        }
        if (res.risk_score != null) {
          const score = Math.round(res.risk_score * 100)
          const tag = score >= 70 ? '高风险' : score >= 40 ? '中等风险' : '低风险'
          setMessages(m => [...m, { role: 'assistant', meta: 'risk', content: `${tag}：${score}%` }])
        }
      }
    } catch (e: any) {
      setMessages(m => [...m, { role: 'assistant', content: `❌ ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  const reset = () => setMessages([])

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header bar */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 tracking-tight">对话</h1>
          <p className="text-xs text-slate-500 mt-0.5">与 Master Agent 交互，自动调度子 Agent 完成任务</p>
        </div>
        {messages.length > 0 && (
          <button onClick={reset}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-colors">
            <RotateCcw size={13} /> 清空对话
          </button>
        )}
      </div>

      {/* Provider toolbar */}
      <div className="flex flex-wrap items-center gap-2 mb-4 px-3 py-2 bg-slate-900/60 ring-1 ring-slate-800 rounded-xl">
        <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold pl-1">Provider</span>
        <select
          value={selectedProvider ?? ''}
          onChange={e => {
            const pid = Number(e.target.value) || null
            setSelectedProvider(pid)
            const p = providers.find(p => p.id === pid)
            setSelectedModel(p?.models?.[0] || '')
          }}
          className="bg-slate-950 ring-1 ring-slate-800 text-slate-200 text-xs rounded-md px-2 py-1.5 outline-none focus:ring-violet-500/60"
        >
          <option value="">默认</option>
          {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold pl-2">模型</span>
        <select
          value={selectedModel}
          onChange={e => setSelectedModel(e.target.value)}
          disabled={!currentProvider?.models?.length}
          className="bg-slate-950 ring-1 ring-slate-800 text-slate-200 text-xs rounded-md px-2 py-1.5 outline-none focus:ring-violet-500/60 disabled:opacity-50"
        >
          <option value="">默认</option>
          {(currentProvider?.models || []).map(m => <option key={m} value={m}>{m}</option>)}
        </select>

        {providers.length === 0 && (
          <a href="#/providers" className="ml-auto text-xs text-violet-400 hover:text-violet-300">
            去配置 Provider →
          </a>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-500/20 to-cyan-500/20 ring-1 ring-violet-500/30 mb-4">
              <Sparkles size={22} className="text-violet-300" />
            </div>
            <p className="text-base font-medium text-slate-200">开始与 CyberGuard 对话</p>
            <p className="text-sm text-slate-500 mt-1.5 max-w-md">
              描述你的安全需求，例如「分析这条防火墙日志中的可疑行为」或「扫描 192.168.1.0/24 网段」。
            </p>
          </div>
        )}

        {messages.map((m, i) => <Bubble key={i} message={m} />)}

        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 bg-slate-900/60 ring-1 ring-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-400">
              <Loader2 size={14} className="animate-spin text-violet-400" />
              思考中…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="mt-4 flex gap-2 items-end">
        <div className="flex-1 relative">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            rows={1}
            placeholder="输入消息…  ↩ 发送 · ⇧↩ 换行"
            className="w-full resize-none bg-slate-900/80 ring-1 ring-slate-800 focus:ring-violet-500/60 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition-shadow max-h-40"
            style={{ minHeight: 46 }}
          />
        </div>
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="h-[46px] px-4 bg-violet-500 hover:bg-violet-400 disabled:opacity-40 disabled:hover:bg-violet-500 text-white rounded-xl text-sm font-medium shadow-lg shadow-violet-500/20 transition-all flex items-center gap-1.5"
        >
          <Send size={14} /> 发送
        </button>
      </div>
    </div>
  )
}

function Bubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-xl bg-violet-500 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed shadow-lg shadow-violet-500/20">
          {message.content}
        </div>
      </div>
    )
  }

  // Special meta variants for plan / actions / risk
  if (message.meta === 'risk') {
    const tone = message.content.includes('高风险')
      ? 'bg-rose-500/10 text-rose-300 ring-rose-500/30'
      : message.content.includes('中等')
      ? 'bg-amber-500/10 text-amber-300 ring-amber-500/30'
      : 'bg-violet-500/10 text-violet-300 ring-violet-500/30'
    return (
      <div className="flex justify-start">
        <div className={`flex items-center gap-2 ring-1 rounded-xl px-3 py-2 text-xs font-medium ${tone}`}>
          <AlertTriangle size={13} /> {message.content}
        </div>
      </div>
    )
  }

  if (message.meta === 'plan' || message.meta === 'actions') {
    return (
      <div className="flex justify-start">
        <div className="max-w-xl bg-slate-900/60 ring-1 ring-violet-500/30 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-slate-200 prose prose-invert prose-sm prose-p:my-1 prose-strong:text-violet-300 max-w-none">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-xl bg-slate-900/60 ring-1 ring-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-slate-100 prose prose-invert prose-sm prose-p:my-1 max-w-none">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  )
}
