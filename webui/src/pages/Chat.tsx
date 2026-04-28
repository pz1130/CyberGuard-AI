import { useState, useRef, useEffect } from 'react'
import { api } from '../api/client'
import ReactMarkdown from 'react-markdown'

interface Message { role: 'user'|'assistant'; content: string }

interface ProviderOption {
  id: number
  name: string
  provider_type: string
  base_url?: string
  models: string[]
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Provider / model selectors
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

  useEffect(() => { bottomRef.current?.scrollIntoView() }, [messages])

  const currentProvider = providers.find(p => p.id === selectedProvider)

  const send = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { role: 'user', content: input }
    setMessages(m => [...m, userMsg])
    setInput('')
    setLoading(true)
    try {
      const res = await api.chat({
        message: input,
        provider_id: selectedProvider ?? undefined,
        model: selectedModel || undefined,
      }) as { message?: string; response?: string; reply?: string; result?: string; error?: string }
      if (res.error) {
        setMessages(m => [...m, { role: 'assistant', content: `错误: ${res.error}` }])
      } else {
        const text = res.message || res.response || res.reply || res.result || JSON.stringify(res)
        setMessages(m => [...m, { role: 'assistant', content: text }])
      }
    } catch (e: any) {
      setMessages(m => [...m, { role: 'assistant', content: `错误: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Provider & Model Selector */}
      <div className="flex gap-3 mb-4 items-center">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">Provider:</span>
          <select
            value={selectedProvider ?? ''}
            onChange={e => {
              const pid = Number(e.target.value)
              setSelectedProvider(pid)
              const p = providers.find(p => p.id === pid)
              setSelectedModel(p?.models?.[0] || '')
            }}
            className="bg-gray-800 border border-gray-700 text-white text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:border-emerald-500"
          >
            {providers.length === 0 && <option value="">无可用 Provider</option>}
            {providers.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">模型:</span>
          <select
            value={selectedModel}
            onChange={e => setSelectedModel(e.target.value)}
            disabled={!currentProvider?.models?.length}
            className="bg-gray-800 border border-gray-700 text-white text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
          >
            {(currentProvider?.models || []).map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <button
          onClick={() => {
            setSelectedProvider(null)
            setSelectedModel('')
          }}
          className="text-xs text-gray-500 hover:text-gray-300 underline"
        >
          重置
        </button>
        {providers.length === 0 && (
          <a href="#/providers" className="text-xs text-emerald-400 hover:text-emerald-300 underline ml-auto">
            去配置 AI Provider →
          </a>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-lg">开始和 CyberGuard 对话</p>
            <p className="text-sm mt-1">基于 Master Agent 的智能助手</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-xl rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              m.role === 'user'
                ? 'bg-emerald-500 text-white'
                : 'bg-gray-800 text-gray-100'
            }`}>
              <ReactMarkdown>{m.content}</ReactMarkdown>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-2xl px-4 py-3 text-sm text-gray-400 animate-pulse">
              思考中...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
          placeholder="输入消息..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
        />
        <button
          onClick={send}
          disabled={loading}
          className="px-5 py-3 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-white rounded-xl text-sm font-medium transition-colors"
        >
          发送
        </button>
      </div>
    </div>
  )
}
