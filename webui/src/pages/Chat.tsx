import { useState, useRef, useEffect } from 'react'
import { api } from '../api/client'
import ReactMarkdown from 'react-markdown'
import { Send, Plus, X, Check, Edit2, Trash2, Settings, Paperclip, Image as ImageIcon, FileText } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
  attachments?: Array<{
    type: 'image' | 'doc'
    url?: string
    name: string
    size?: number
  }>
}

interface TaskResponse {
  id: string
  title?: string
  status: string
  output_data?: string | { response?: string; content?: string; text?: string; final_summary?: string }
  error_message?: string
  created_at?: string
}

interface Conversation {
  id: number
  title: string
  updated_at: string
  system_prompt_override?: string | null
  intent_parser_prompt_override?: string | null
  summarizer_prompt_override?: string | null
  model_override?: string | null
  temperature_override?: number | null
  knowledge_base_id?: number | null
}

interface KnowledgeBase {
  id: number
  name: string
}

interface ProviderModel {
  provider_id: number
  provider_name: string
  provider_type: string
  base_url: string
  model: string
}

const FALLBACK_MODELS = [
  { provider_id: 0, provider_name: 'OPENAI', provider_type: 'openai', base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  { provider_id: 0, provider_name: 'ANTHROPIC', provider_type: 'anthropic', base_url: 'https://api.anthropic.com/v1', model: 'claude-sonnet-4-7-2025' },
  { provider_id: 0, provider_name: 'GROK', provider_type: 'xai', base_url: 'https://api.x.ai/v1', model: 'grok-3' },
]

const ACCEPTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
const ACCEPTED_DOC_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
  'text/csv',
  'application/json',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
]
const MAX_FILES = 10

interface AttachmentFile {
  file: File
  previewUrl: string
}

export default function Chat() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [providerModel, setProviderModel] = useState(() => localStorage.getItem('lastProviderModel') || 'auto')
  const [pollingStatus, setPollingStatus] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [availableModels, setAvailableModels] = useState<ProviderModel[]>(FALLBACK_MODELS)
  const isMountedRef = useRef(true)
  const activeTaskIdRef = useRef<string | null>(null)
  const pollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Conversation state
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConvId, setActiveConvId] = useState<number | null>(null)
  const [editingConvId, setEditingConvId] = useState<number | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [showConvPanel, setShowConvPanel] = useState(true)

  // Per-conversation settings
  const [showConvSettings, setShowConvSettings] = useState(false)
  const [convSettings, setConvSettings] = useState({
    system_prompt_override: '',
    intent_parser_prompt_override: '',
    summarizer_prompt_override: '',
    model_override: '',
    temperature_override: 0.7,
    knowledge_base_id: null as number | null,
  })
  const [availableKBs, setAvailableKBs] = useState<KnowledgeBase[]>([])

  const [attachments, setAttachments] = useState<AttachmentFile[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pollingStatus])

  // Track component mount state
  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  // Load conversations on mount
  useEffect(() => {
    loadConversations()
    loadKnowledgeBases()
  }, [])

  // Load knowledge bases
  const loadKnowledgeBases = async () => {
    try {
      const data = await api.getKnowledgeBases() as { bases: any[] }
      setAvailableKBs(data?.bases || [])
    } catch { setAvailableKBs([]) }
  }

  // Load conversations
  const loadConversations = async () => {
    try {
      const data = await api.getConversations() as Conversation[]
      setConversations(data || [])
    } catch { setConversations([]) }
  }

  // Load messages for active conversation
  const loadConversationMessages = async (convId: number) => {
    try {
      const data = await api.getConversationMessages(convId) as { messages: Message[] }
      setMessages(data.messages || [])
    } catch { setMessages([]) }
  }

  // Create new conversation
  const createConversation = async () => {
    try {
      const conv = await api.createConversation({ title: '新对话' }) as Conversation
      setConversations(prev => [conv, ...prev])
      setActiveConvId(conv.id)
      setMessages([])
      setPollingStatus('')
      setShowConvSettings(false)
      setConvSettings({
        system_prompt_override: '',
        intent_parser_prompt_override: '',
        summarizer_prompt_override: '',
        model_override: '',
        temperature_override: 0.7,
        knowledge_base_id: null,
      })
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    } catch (e: any) { alert(e.message) }
  }

  // Select conversation
  const selectConversation = async (convId: number) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    pollIntervalRef.current = null
    activeTaskIdRef.current = null
    localStorage.removeItem('activeChatTaskId')
    setActiveConvId(convId)
    setShowConvSettings(false)
    await loadConversationMessages(convId)
    // Load conversation settings
    try {
      const conv = await api.getConversation(convId) as Conversation
      setConvSettings({
        system_prompt_override: conv.system_prompt_override || '',
        intent_parser_prompt_override: conv.intent_parser_prompt_override || '',
        summarizer_prompt_override: conv.summarizer_prompt_override || '',
        model_override: conv.model_override || '',
        temperature_override: conv.temperature_override ?? 0.7,
        knowledge_base_id: conv.knowledge_base_id ?? null,
      })
    } catch { /* ignore */ }
    localStorage.removeItem('activeChatTaskId')
  }

  // Delete conversation
  const deleteConversation = async (convId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete conversation?')) return
    try {
      await api.deleteConversation(convId)
      setConversations(prev => prev.filter(c => c.id !== convId))
      if (activeConvId === convId) {
        setActiveConvId(null)
        setMessages([])
        localStorage.removeItem('activeChatTaskId')
      }
    } catch (e: any) { alert(e.message) }
  }

  // Start editing title
  const startEditTitle = (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingConvId(conv.id)
    setEditingTitle(conv.title)
  }

  // Save edited title
  const saveEditTitle = async () => {
    if (!editingConvId) return
    try {
      await api.updateConversation(editingConvId, { title: editingTitle })
      setConversations(prev => prev.map(c => c.id === editingConvId ? { ...c, title: editingTitle } : c))
    } catch (e: any) { alert(e.message) }
    setEditingConvId(null)
  }

  // Cancel edit
  const cancelEditTitle = () => {
    setEditingConvId(null)
  }

  // Load available models from providers on mount
  useEffect(() => {
    const loadModels = async () => {
      try {
        const data = await api.getProviders() as { total: number; providers: any[] }
        if (!data?.providers) return
        const models: ProviderModel[] = []
        for (const p of data.providers) {
          if (!p.is_active) continue
          for (const m of (p.models || [])) {
            models.push({
              provider_id: p.id,
              provider_name: p.name.toUpperCase(),
              provider_type: p.provider_type,
              base_url: (p.base_url || '').replace(/\/$/, ''),
              model: typeof m === 'string' ? m : (m as any).name || m,
            })
          }
        }
        if (models.length > 0) setAvailableModels(models)
      } catch { /* use fallback */ }
    }
    loadModels()
  }, [])

  // Parse selected value: "provider_id:model" or "auto"
  const getModelOverride = () => {
    if (providerModel === 'auto') return {}
    const colonIdx = providerModel.indexOf(':')
    if (colonIdx < 0) return {}
    return {
      provider_id: parseInt(providerModel.slice(0, colonIdx)),
      model: providerModel.slice(colonIdx + 1),
    }
  }

  // Poll for task result
  const pollForResult = async (taskId: string): Promise<TaskResponse | null> => {
    try {
      return await api.getTask(taskId) as TaskResponse
    } catch { return null }
  }

  // Handle task completion
  const handleTaskResult = (task: TaskResponse) => {
    if (task?.status === 'completed') {
      const raw = task.output_data
      let output = ''
      if (typeof raw === 'string') output = raw
      else if (raw?.response) output = raw.response
      else if (raw?.final_summary) output = raw.final_summary
      else if (raw?.content) output = raw.content
      else if (raw?.text) output = raw.text
      else output = JSON.stringify(raw, null, 2)
      output = output.replace(/<think>[\s\S]*?<\/think>/gi, '').trim()
      const assistantMsg = { role: 'assistant' as const, content: output, created_at: new Date().toISOString() }
      setMessages(prev => [...prev, assistantMsg])
      // Save to conversation
      if (activeConvId) {
        api.appendConversationMessage(activeConvId, { role: 'user', content: input.trim() }).catch(() => {})
        api.appendConversationMessage(activeConvId, { role: 'assistant', content: output }).catch(() => {})
        // Update conversation title based on first user message
        if (messages.filter(m => m.role === 'user').length === 1) {
          const shortTitle = input.trim().slice(0, 30) + (input.trim().length > 30 ? '...' : '')
          api.updateConversation(activeConvId, { title: shortTitle }).catch(() => {})
        }
      }
    } else if (task?.status === 'failed') {
      const errMsg = `⚠ TASK FAILED — ${task.error_message || 'UNKNOWN ERROR'}`
      setMessages(prev => [...prev, { role: 'assistant', content: errMsg, created_at: new Date().toISOString() }])
      if (activeConvId) {
        api.appendConversationMessage(activeConvId, { role: 'assistant', content: errMsg }).catch(() => {})
      }
    } else {
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠ TASK TIMED OUT', created_at: new Date().toISOString() }])
    }
    localStorage.removeItem('activeChatTaskId')
  }

  // Resume polling
  const resumePolling = (taskId: string) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    let seconds = 0
    pollIntervalRef.current = setInterval(async () => {
      seconds += 2
      if (!isMountedRef.current) return
      setPollingStatus(`RESUMING... (${seconds}s)`)
      const task = await pollForResult(taskId)
      if (!isMountedRef.current) return
      if (task?.status === 'completed' || task?.status === 'failed') {
        clearInterval(pollIntervalRef.current!)
        pollIntervalRef.current = null
        handleTaskResult(task)
        setLoading(false)
        setPollingStatus('')
      }
    }, 2000)
  }

  // Resume polling on mount if there's an active task from a previous session
  useEffect(() => {
    const stored = localStorage.getItem('activeChatTaskId')
    if (stored) {
      setLoading(true)
      setPollingStatus('RESUMING...')
      resumePolling(stored)
    }
  }, [])

  // Send message
  const send = async () => {
    if ((!input.trim() && attachments.length === 0) || loading) return
    if (!activeConvId) {
      alert('请先创建或选择一个会话')
      return
    }

    const modelOverride = getModelOverride()

    const userMsg: Message = {
      role: 'user',
      content: input.trim() || (attachments.length > 0 ? `[${attachments.length} 个附件]` : ''),
      created_at: new Date().toISOString(),
      attachments: attachments.map(att => ({
        type: (ACCEPTED_IMAGE_TYPES.includes(att.file.type) ? 'image' : 'doc') as 'image' | 'doc',
        url: att.previewUrl,
        name: att.file.name,
        size: att.file.size,
      })),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setPollingStatus(attachments.length > 0 ? 'UPLOADING ATTACHMENTS...' : 'DISPATCHING TASK...')

    try {
      const files = attachments.map(a => a.file)

      const chatResp = files.length > 0
        ? await api.uploadChatAttachments(
            files,
            input.trim(),
            activeConvId,
            Object.keys(modelOverride).length > 0 ? modelOverride : undefined,
          ) as { task_id: string; status: string; message: string }
        : await api.chat({ message: input.trim(), conversation_id: activeConvId, ...modelOverride }) as { task_id: string; status: string; message: string }

      // Clean up object URLs
      attachments.forEach(att => {
        if (att.previewUrl) URL.revokeObjectURL(att.previewUrl)
      })
      setAttachments([])

      const taskId = chatResp.task_id
      activeTaskIdRef.current = taskId
      localStorage.setItem('activeChatTaskId', taskId)

      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
      let seconds = 0
      pollIntervalRef.current = setInterval(async () => {
        seconds += 2
        if (!isMountedRef.current) return
        setPollingStatus(`PROCESSING... (${seconds}s)`)
        const task = await pollForResult(taskId)
        if (!isMountedRef.current) return
        if (task?.status === 'completed' || task?.status === 'failed') {
          clearInterval(pollIntervalRef.current!)
          pollIntervalRef.current = null
          activeTaskIdRef.current = null
          localStorage.removeItem('activeChatTaskId')
          handleTaskResult(task)
          setLoading(false)
          setPollingStatus('')
        }
      }, 2000)
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠ SYSTEM ERROR — ${e?.message || 'TRANSMISSION FAILURE'}`, created_at: new Date().toISOString() }])
      setLoading(false)
      setPollingStatus('')
    }
  }

  const clearChat = () => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    pollIntervalRef.current = null
    activeTaskIdRef.current = null
    localStorage.removeItem('activeChatTaskId')
    setMessages([])
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const formatTime = (ts?: string) => {
    if (!ts) return ''
    try {
      const d = new Date(ts)
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } catch { return '' }
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - var(--header-height) - 48px)', gap: 0 }}>
      {/* Conversation sidebar */}
      {showConvPanel && (
        <div style={{
          width: 220, flexShrink: 0, borderRight: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', background: 'var(--bg-surface)',
        }}>
          <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)' }}>CONVERSATIONS</span>
            <button onClick={createConversation} style={{ padding: 4, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none' }}>
              <Plus size={13} />
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {conversations.map(conv => (
              <div key={conv.id} onClick={() => selectConversation(conv.id)}
                style={{
                  padding: '10px 12px', cursor: 'pointer', borderBottom: '1px solid var(--border)',
                  background: activeConvId === conv.id ? 'var(--accent-dim)' : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4,
                }}>
                {editingConvId === conv.id ? (
                  <div style={{ flex: 1, display: 'flex', gap: 4 }}>
                    <input
                      value={editingTitle}
                      onChange={e => setEditingTitle(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') saveEditTitle(); if (e.key === 'Escape') cancelEditTitle() }}
                      autoFocus
                      style={{ flex: 1, height: 24, padding: '0 6px', background: 'var(--bg-base)', border: '1px solid var(--accent)', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
                      onClick={e => e.stopPropagation()}
                    />
                    <button onClick={(e) => { e.stopPropagation(); saveEditTitle() }} style={{ padding: 2, color: 'var(--accent)', background: 'none', border: 'none' }}><Check size={10} /></button>
                    <button onClick={(e) => { e.stopPropagation(); cancelEditTitle() }} style={{ padding: 2, color: 'var(--text-dim)', background: 'none', border: 'none' }}><X size={10} /></button>
                  </div>
                ) : (
                  <>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11, color: activeConvId === conv.id ? 'var(--accent)' : 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{conv.title}</div>
                      {conv.updated_at && <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 2 }}>{formatTime(conv.updated_at)}</div>}
                    </div>
                    <button onClick={(e) => startEditTitle(conv, e)} style={{ padding: 2, color: 'var(--text-dim)', background: 'none', border: 'none', flexShrink: 0 }}><Edit2 size={10} /></button>
                    <button onClick={(e) => deleteConversation(conv.id, e)} style={{ padding: 2, color: 'var(--red)', background: 'none', border: 'none', flexShrink: 0 }}><Trash2 size={10} /></button>
                  </>
                )}
              </div>
            ))}
            {conversations.length === 0 && (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-dim)', fontSize: 10, letterSpacing: '0.1em' }}>
                NO CONVERSATIONS
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Toolbar */}
        <div style={{
          padding: '8px 16px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 12,
          background: 'var(--bg-surface)',
        }}>
          <button onClick={() => setShowConvPanel(p => !p)} style={{
            padding: 4, color: showConvPanel ? 'var(--accent)' : 'var(--text-dim)', background: 'none', border: 'none', cursor: 'pointer',
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
          </button>
          <span style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)' }}>MODEL</span>
          <select value={providerModel} onChange={e => { localStorage.setItem('lastProviderModel', e.target.value); setProviderModel(e.target.value) }}
            style={{
              height: 26, padding: '0 8px',
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 10, letterSpacing: '0.05em',
              fontFamily: 'var(--font-mono)',
            }}>
            <option value="auto">AUTO</option>
            {availableModels.map(m => <option key={`${m.provider_id}:${m.model}`} value={`${m.provider_id}:${m.model}`}>{m.provider_name} / {m.model}</option>)}
          </select>
          <div style={{ flex: 1 }} />
          {activeConvId && (
            <>
              <button onClick={() => setShowConvSettings(s => !s)} style={{
                padding: '4px 10px', fontSize: 10, letterSpacing: '0.1em',
                border: '1px solid var(--border-bright)', background: showConvSettings ? 'var(--accent-dim)' : 'transparent',
                color: showConvSettings ? 'var(--accent)' : 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                display: 'flex', alignItems: 'center', gap: 4,
              }}>
                <Settings size={10} /> SESSION
              </button>
              <button onClick={clearChat} style={{
                padding: '4px 12px', fontSize: 10, letterSpacing: '0.1em',
                border: '1px solid var(--border-bright)', background: 'transparent',
                color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-mono)',
              }}>
                CLEAR
              </button>
            </>
          )}
        </div>

        {/* Session Settings Panel */}
        {showConvSettings && activeConvId && (
          <div style={{
            borderBottom: '1px solid var(--border)',
            background: 'var(--bg-surface)',
            padding: '16px 20px',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 16,
          }}>
            <div>
              <div style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 8 }}>KNOWLEDGE BASE</div>
              <select
                value={convSettings.knowledge_base_id ?? ''}
                onChange={e => setConvSettings(s => ({ ...s, knowledge_base_id: e.target.value ? Number(e.target.value) : null }))}
                style={{
                  width: '100%', height: 32, padding: '0 8px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)',
                }}>
                <option value="">— None —</option>
                {availableKBs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
              </select>
            </div>
            <div>
              <div style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 8 }}>MODEL OVERRIDE</div>
              <select
                value={convSettings.model_override}
                onChange={e => setConvSettings(s => ({ ...s, model_override: e.target.value }))}
                style={{
                  width: '100%', height: 32, padding: '0 8px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)',
                }}>
                <option value="">— Global Default —</option>
                {availableModels.map(m => <option key={`${m.provider_id}:${m.model}`} value={m.model}>{m.provider_name} / {m.model}</option>)}
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <div style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 8 }}>CUSTOM SYSTEM PROMPT</div>
              <textarea
                value={convSettings.system_prompt_override}
                onChange={e => setConvSettings(s => ({ ...s, system_prompt_override: e.target.value }))}
                rows={3}
                placeholder="Leave empty to use global default"
                style={{
                  width: '100%', padding: '8px 10px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 11, lineHeight: 1.5,
                  fontFamily: 'var(--font-mono)', resize: 'vertical',
                }}
              />
            </div>
            <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => setShowConvSettings(false)}
                style={{
                  padding: '6px 14px', fontSize: 10, letterSpacing: '0.1em',
                  border: '1px solid var(--border-bright)', background: 'transparent',
                  color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}>
                CANCEL
              </button>
              <button
                onClick={async () => {
                  try {
                    const update = {
                      system_prompt_override: convSettings.system_prompt_override || null,
                      intent_parser_prompt_override: convSettings.intent_parser_prompt_override || null,
                      summarizer_prompt_override: convSettings.summarizer_prompt_override || null,
                      model_override: convSettings.model_override || null,
                      temperature_override: convSettings.temperature_override,
                      knowledge_base_id: convSettings.knowledge_base_id,
                    }
                    await api.updateConversation(activeConvId, update)
                    setConversations(prev => prev.map(c =>
                      c.id === activeConvId ? { ...c, ...update } : c
                    ))
                    setShowConvSettings(false)
                  } catch (e: any) { alert(e.message) }
                }}
                style={{
                  padding: '6px 14px', fontSize: 10, letterSpacing: '0.1em',
                  background: 'var(--accent)', border: '1px solid var(--accent-border)',
                  color: '#000', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontWeight: 700,
                }}>
                SAVE SETTINGS
              </button>
            </div>
          </div>
        )}

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!activeConvId ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, color: 'var(--text-dim)' }}>
              <div style={{ fontSize: 32, color: 'var(--accent)', opacity: 0.5 }}>⬡</div>
              <div style={{ fontSize: 11, letterSpacing: '0.2em' }}>SELECT OR CREATE A CONVERSATION</div>
              <button onClick={createConversation} style={{
                padding: '8px 20px', fontSize: 10, letterSpacing: '0.15em',
                background: 'var(--accent)', border: 'none', color: '#000',
                cursor: 'pointer', fontFamily: 'var(--font-mono)', fontWeight: 700,
              }}>+ NEW CONVERSATION</button>
            </div>
          ) : messages.length === 0 ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, color: 'var(--text-dim)' }}>
              <div style={{ fontSize: 24, opacity: 0.3 }}>⬡</div>
              <div style={{ fontSize: 10, letterSpacing: '0.15em' }}>READY — SEND A MESSAGE</div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} style={{
                display: 'flex', flexDirection: 'column',
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div style={{ fontSize: 9, letterSpacing: '0.15em', color: 'var(--text-dim)', marginBottom: 4 }}>
                  {msg.role === 'user' ? '◆ OPERATOR' : msg.role === 'assistant' ? '◆ CYBERGUARD' : '◆ SYSTEM'}
                </div>
                <div style={{
                  maxWidth: '80%', padding: '10px 14px',
                  background: msg.role === 'user' ? 'var(--accent)' : msg.role === 'system' ? 'var(--amber-dim)' : 'var(--bg-elevated)',
                  border: `1px solid ${msg.role === 'user' ? 'var(--accent-border)' : 'var(--border)'}`,
                  color: msg.role === 'user' ? '#000' : 'var(--text-primary)',
                  fontSize: 13, lineHeight: 1.6,
                  fontFamily: 'var(--font-mono)',
                }}>
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  ) : msg.content}
                </div>
                {/* Render attachment previews for user messages */}
{msg.role === 'user' && msg.attachments && msg.attachments.length > 0 && (
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
    {msg.attachments.map((att, i) =>
      att.type === 'image' ? (
        <div key={`${att.name}-${att.size}-${i}`} style={{ position: 'relative' }}>
          <img
            src={att.url}
            onClick={() => setLightboxUrl(att.url || null)}
            style={{
              width: 64, height: 64, objectFit: 'cover',
              border: '1px solid var(--accent-border)',
              cursor: 'pointer',
            }}
          />
        </div>
      ) : (
        <div key={`${att.name}-${att.size}-${i}`} style={{
          display: 'flex', alignItems: 'center', gap: 4,
          padding: '4px 8px',
          border: '1px solid var(--accent-border)',
          fontSize: 10, fontFamily: 'var(--font-mono)',
          color: 'var(--text-muted)',
        }}>
          <FileText size={10} />
          <span>{att.name}</span>
        </div>
      )
    )}
  </div>
)}
{msg.created_at && <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 3 }}>{formatTime(msg.created_at)}</div>}
              </div>
            ))
          )}
          {pollingStatus && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', color: 'var(--text-muted)', fontSize: 11, letterSpacing: '0.1em' }}>
              <div style={{ width: 12, height: 12, border: '1px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              {pollingStatus}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={[...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_DOC_TYPES].join(',')}
            onChange={(e) => {
              const files = Array.from(e.target.files || [])
              if (files.length + attachments.length > MAX_FILES) {
                alert(`最多上传 ${MAX_FILES} 个文件`)
                return
              }
              const newAttachments = files.map(f => ({
                file: f,
                previewUrl: ACCEPTED_IMAGE_TYPES.includes(f.type)
                  ? URL.createObjectURL(f)
                  : '',
              }))
              setAttachments(prev => [...prev, ...newAttachments])
              e.target.value = ''
            }}
            style={{ display: 'none' }}
          />
          {attachments.length > 0 && (
            <div style={{
              padding: '8px 16px',
              display: 'flex',
              flexWrap: 'wrap',
              gap: 8,
              borderTop: '1px solid var(--border)',
              background: 'var(--bg-base)',
            }}>
              {attachments.map((att, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '4px 8px',
                  border: '1px solid var(--accent-border)',
                  background: 'var(--accent-dim)',
                  fontSize: 10,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-primary)',
                }}>
                  {ACCEPTED_IMAGE_TYPES.includes(att.file.type) ? (
                    <ImageIcon size={10} style={{ color: 'var(--accent)' }} />
                  ) : (
                    <FileText size={10} style={{ color: 'var(--accent)' }} />
                  )}
                  <span style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {att.file.name}
                  </span>
                  <button
                    onClick={() => {
                      if (att.previewUrl) URL.revokeObjectURL(att.previewUrl)
                      setAttachments(prev => prev.filter((_, idx) => idx !== i))
                    }}
                    style={{
                      padding: 0, background: 'none', border: 'none',
                      color: 'var(--text-dim)', cursor: 'pointer', display: 'flex',
                    }}>
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={!activeConvId || loading}
            style={{
              width: 36, height: 36, flexShrink: 0,
              border: '1px solid var(--border-bright)',
              background: 'transparent',
              color: activeConvId && !loading ? 'var(--text-muted)' : 'var(--text-dim)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: activeConvId && !loading ? 'pointer' : 'not-allowed',
              opacity: activeConvId && !loading ? 1 : 0.5,
            }}>
            <Paperclip size={14} />
          </button>
          <textarea
            ref={textareaRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKey}
            placeholder={activeConvId ? 'Type your message...' : 'Select a conversation first...'}
            disabled={!activeConvId || loading}
            rows={1}
            style={{
              flex: 1, padding: '10px 12px',
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 13,
              fontFamily: 'var(--font-mono)', resize: 'none', maxHeight: 120,
              opacity: activeConvId ? 1 : 0.5,
            }}
          />
          <button
            onClick={() => {
              if (loading && activeTaskIdRef.current) {
                // Cancel the running task
                api.cancelTask(activeTaskIdRef.current).catch(console.error)
                if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
                pollIntervalRef.current = null
                activeTaskIdRef.current = null
                localStorage.removeItem('activeChatTaskId')
                setLoading(false)
                setPollingStatus('')
                setMessages(prev => [...prev, { role: 'assistant', content: '⚠ TASK CANCELLED BY OPERATOR', created_at: new Date().toISOString() }])
              } else {
                send()
              }
            }}
            disabled={!activeConvId || (!loading && !input.trim() && attachments.length === 0)}
            style={{
              width: 40, height: 40, flexShrink: 0,
              background: loading ? 'var(--red)' : 'var(--accent)',
              border: `1px solid ${loading ? 'var(--red)' : 'var(--accent-border)'}`,
              color: loading ? '#fff' : '#000',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: (!activeConvId || (!loading && !input.trim() && attachments.length === 0)) ? 'not-allowed' : 'pointer',
              opacity: (!activeConvId || (!loading && !input.trim() && attachments.length === 0)) ? 0.5 : 1,
            }}>
            {loading ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
            ) : <Send size={14} />}
          </button>
        </div>
        {lightboxUrl && (
          <div
            onClick={() => setLightboxUrl(null)}
            style={{
              position: 'fixed', inset: 0, zIndex: 9999,
              background: 'rgba(0,0,0,0.9)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer',
            }}>
            <img
              src={lightboxUrl}
              style={{ maxWidth: '90vw', maxHeight: '90vh', objectFit: 'contain' }}
              onClick={e => e.stopPropagation()}
            />
            <button
              onClick={() => setLightboxUrl(null)}
              style={{
                position: 'absolute', top: 16, right: 16,
                padding: 8, background: 'var(--bg-elevated)',
                border: '1px solid var(--border-bright)',
                color: 'var(--text-primary)', cursor: 'pointer',
                fontSize: 11, fontFamily: 'var(--font-mono)',
              }}>
              CLOSE
            </button>
          </div>
        )}
      </div>
    </div>
  )
}