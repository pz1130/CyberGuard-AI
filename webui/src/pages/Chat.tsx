import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import ReactMarkdown from 'react-markdown'
import { Send, Plus, X, Check, Edit2, Trash2, Settings, Paperclip, Image as ImageIcon, FileText } from 'lucide-react'
import { useSearch } from '../context/SearchContext'

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

interface PromptTemplate {
  id: number
  name: string
  description: string | null
  content: string
  category: 'system' | 'intent_parser' | 'summarizer' | 'general'
  is_active: boolean
}

interface ProviderModel {
  provider_id: number
  provider_name: string
  provider_type: string
  base_url: string
  model: string
  // optional verification status (gates Chat dropdown visibility)
  verified?: boolean | null
  last_tested_at?: string | null
  test_error?: string | null
}

interface AgentOption {
  id: string
  agent_name: string
  backend_type?: string
  is_active?: boolean
}

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
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [providerModel, setProviderModel] = useState(() => localStorage.getItem('lastProviderModel') || 'auto')
  const [selectedAgentId, setSelectedAgentId] = useState(() => localStorage.getItem('lastSelectedAgentId') || '')
  const [availableAgents, setAvailableAgents] = useState<AgentOption[]>([])
  // Chat mode: 'normal' (LLM decides) | 'fast' (master only) | 'expert' (fan out to all agents)
  const [chatMode, setChatMode] = useState<'normal' | 'fast' | 'expert'>(() => {
    const v = localStorage.getItem('lastChatMode')
    return v === 'fast' || v === 'expert' ? v : 'normal'
  })
  const [pollingStatus, setPollingStatus] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [availableModels, setAvailableModels] = useState<ProviderModel[]>([])
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
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplate[]>([])
  const autoCreateGuardRef = useRef(false)

  const [attachments, setAttachments] = useState<AttachmentFile[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)

  // React to search target — open conversation when selected from GlobalSearch
  const { searchTarget, setSearchTarget } = useSearch()
  useEffect(() => {
    if (searchTarget && searchTarget.tab === 'chat' && searchTarget.id) {
      const convId = Number(searchTarget.id)
      if (convId && convId !== activeConvId) {
        selectConversation(convId)
      }
      setSearchTarget(null)
    }
  }, [searchTarget])

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
    loadAvailableAgents()
    loadPromptTemplates()
  }, [])

  // (Active-conversation selection is handled in loadConversations once the
  // list is known, so refreshing reuses the latest conversation instead of
  // creating a new empty one each time.)

  const loadPromptTemplates = async () => {
    try {
      const data = await api.getPromptTemplates() as PromptTemplate[]
      setPromptTemplates((data || []).filter(t => t.is_active))
    } catch { setPromptTemplates([]) }
  }

  // Load registered sub-agents for the selector
  const loadAvailableAgents = async () => {
    try {
      const data = await api.getAgents() as any
      const list: AgentOption[] = Array.isArray(data) ? data : (data?.agents || [])
      setAvailableAgents(list.filter(a => a.is_active !== false))
    } catch { setAvailableAgents([]) }
  }

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
      const list = data || []
      setConversations(list)
      // On first load, decide the active conversation exactly once: resume
      // nothing if a task is pending, keep an already-active one, otherwise
      // select the most recent existing conversation — and only create a new
      // one when the user has none at all. This stops every page refresh from
      // spawning an empty "新对话".
      if (autoCreateGuardRef.current) return
      autoCreateGuardRef.current = true
      if (localStorage.getItem('activeChatTaskId')) return
      if (activeConvId != null) return
      if (list.length > 0) {
        const newest = list.reduce((a, b) => (b.id > a.id ? b : a))
        selectConversation(newest.id)
      } else {
        createConversation()
      }
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
    } catch (e) { console.error('Failed to load conversation:', e) }
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
            // Only show models that the user has explicitly verified.
            // A model dict's `verified` is set to true by /providers/test and
            // /providers/{id}/models/probe on a successful call. Built-in presets
            // are seeded with verified=true (see _seed_presets). Legacy rows may
            // still hold plain strings instead of dicts — those have no
            // `verified` field and are filtered out.
            const entry = (typeof m === 'object' && m !== null) ? m as { name?: string; verified?: boolean | null } : null
            if (!entry || entry.verified !== true) continue
            models.push({
              provider_id: p.id,
              provider_name: p.name.toUpperCase(),
              provider_type: p.provider_type,
              base_url: (p.base_url || '').replace(/\/$/, ''),
              model: entry.name || '',
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
      // Backend handles conversation persistence + auto-title
    } else if (task?.status === 'failed') {
      const errMsg = `⚠ TASK FAILED — ${task.error_message || 'UNKNOWN ERROR'}`
      setMessages(prev => [...prev, { role: 'assistant', content: errMsg, created_at: new Date().toISOString() }])
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
    const userText = input.trim()
    const files = attachments.map(a => a.file)
    const agentIdParam = selectedAgentId || undefined
    const modeParam = chatMode !== 'normal' ? chatMode : undefined

    // Simple text-only chat → streaming path (SSE)
    const isSimpleChat = files.length === 0 && !agentIdParam && !modeParam

    const userMsg: Message = {
      role: 'user',
      content: userText || (files.length > 0 ? `[${files.length} 个附件]` : ''),
      created_at: new Date().toISOString(),
      attachments: attachments.map(att => ({
        type: (ACCEPTED_IMAGE_TYPES.includes(att.file.type) ? 'image' : 'doc') as 'image' | 'doc',
        url: att.previewUrl,
        name: att.file.name,
        size: att.file.size,
      })),
    }

    if (isSimpleChat) {
      // ── Streaming path ───────────────────────────────────────────
      setMessages(prev => [...prev, userMsg, { role: 'assistant', content: '', created_at: new Date().toISOString() }])
      setInput('')
      setLoading(true)
      setPollingStatus('STREAMING...')

      try {
        const streamBody: any = { message: userText, conversation_id: activeConvId }
        if (modelOverride.provider_id) streamBody.provider_id = modelOverride.provider_id
        if (modelOverride.model) streamBody.model = modelOverride.model

        for await (const evt of api.chatStream(streamBody)) {
          if (!isMountedRef.current) return
          if (evt.type === 'chunk') {
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last?.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: last.content + evt.content }
              }
              return updated
            })
          } else if (evt.type === 'error') {
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last?.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: `⚠ ${evt.content}` }
              }
              return updated
            })
          }
          // 'done' — stream finished, backend persists + auto-titles automatically
        }
      } catch (e: any) {
        setMessages(prev => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last?.role === 'assistant' && !last.content) {
            updated[updated.length - 1] = { ...last, content: `⚠ STREAM ERROR — ${e?.message || 'CONNECTION FAILED'}` }
          } else {
            updated.push({ role: 'assistant', content: `⚠ STREAM ERROR — ${e?.message || 'CONNECTION FAILED'}`, created_at: new Date().toISOString() })
          }
          return updated
        })
      } finally {
        if (isMountedRef.current) {
          setLoading(false)
          setPollingStatus('')
        }
      }
    } else {
      // ── Celery path (attachments / agent / expert mode) ──────────
      setMessages(prev => [...prev, userMsg])
      setInput('')
      setLoading(true)
      setPollingStatus(files.length > 0 ? 'UPLOADING ATTACHMENTS...' : 'DISPATCHING TASK...')

      try {
        const chatResp = files.length > 0
          ? await api.uploadChatAttachments(
              files, userText, activeConvId,
              Object.keys(modelOverride).length > 0 ? modelOverride : undefined,
              agentIdParam, modeParam,
            ) as { task_id: string; status: string; message: string }
          : await api.chat({ message: userText, conversation_id: activeConvId, agent_id: agentIdParam, mode: modeParam, ...modelOverride }) as { task_id: string; status: string; message: string }

        // Clean up object URLs
        attachments.forEach(att => { if (att.previewUrl) URL.revokeObjectURL(att.previewUrl) })
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
  }

  const clearChat = () => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    pollIntervalRef.current = null
    activeTaskIdRef.current = null
    localStorage.removeItem('activeChatTaskId')
    setMessages([])
  }

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // IME composition (中文/日文/韩文输入法 etc.): don't send while user is still
    // composing. `isComposing` is the modern check; `keyCode === 229` is a
    // legacy fallback for browsers (and some IME states) where isComposing isn't set.
    if (e.nativeEvent.isComposing || e.keyCode === 229) return
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
    <div className="chat-page" style={{ display: 'flex', height: 'calc(100vh - var(--header-height) - 48px)', gap: 0 }}>
      {/* Conversation sidebar */}
      {showConvPanel && (
        <div style={{
          width: 240, flexShrink: 0, borderRight: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', background: 'var(--bg-surface)',
        }}>
          <div style={{ padding: '0 14px', height: 44, flexShrink: 0, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', fontFamily: 'var(--font-sans)', fontWeight: 600, textTransform: 'uppercase' }}>{t('chat.history').toUpperCase()}</span>
            <button onClick={createConversation} style={{ padding: 4, color: 'var(--accent)', cursor: 'pointer', background: 'none', border: 'none', display: 'flex', alignItems: 'center', borderRadius: 'var(--radius-sm)' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--accent-dim)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'none')}
            >
              <Plus size={14} />
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
            {conversations.map(conv => (
              <div key={conv.id} onClick={() => selectConversation(conv.id)}
                style={{
                  padding: '10px 12px', cursor: 'pointer', marginBottom: 2,
                  background: activeConvId === conv.id ? 'var(--accent-dim)' : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4,
                  borderRadius: 'var(--radius-md)',
                  borderLeft: activeConvId === conv.id ? '2px solid var(--accent)' : '2px solid transparent',
                  transition: 'background 0.1s ease',
                }}
                onMouseEnter={e => { if (activeConvId !== conv.id) e.currentTarget.style.background = 'var(--bg-hover)' }}
                onMouseLeave={e => { if (activeConvId !== conv.id) e.currentTarget.style.background = 'transparent' }}
              >
                {editingConvId === conv.id ? (
                  <div style={{ flex: 1, display: 'flex', gap: 4 }}>
                    <input
                      value={editingTitle}
                      onChange={e => setEditingTitle(e.target.value)}
                      onKeyDown={e => {
                        if (e.nativeEvent.isComposing || e.keyCode === 229) return
                        if (e.key === 'Enter') saveEditTitle()
                        else if (e.key === 'Escape') cancelEditTitle()
                      }}
                      autoFocus
                      style={{ flex: 1, height: 24, padding: '0 6px', background: 'var(--bg-base)', border: '1px solid var(--accent)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-sans)', borderRadius: 'var(--radius-sm)' }}
                      onClick={e => e.stopPropagation()}
                    />
                    <button onClick={(e) => { e.stopPropagation(); saveEditTitle() }} style={{ padding: 2, color: 'var(--accent)', background: 'none', border: 'none' }}><Check size={10} /></button>
                    <button onClick={(e) => { e.stopPropagation(); cancelEditTitle() }} style={{ padding: 2, color: 'var(--text-dim)', background: 'none', border: 'none' }}><X size={10} /></button>
                  </div>
                ) : (
                  <>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, color: activeConvId === conv.id ? 'var(--accent)' : 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'var(--font-sans)', fontWeight: activeConvId === conv.id ? 500 : 400 }}>{conv.title}</div>
                      {conv.updated_at && <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 3, fontFamily: 'var(--font-sans)' }}>{formatTime(conv.updated_at)}</div>}
                    </div>
                    <div style={{ display: 'flex', gap: 2, opacity: 0.5, transition: 'opacity 0.1s ease' }}
                      onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                      onMouseLeave={e => (e.currentTarget.style.opacity = '0.5')}
                    >
                      <button onClick={(e) => startEditTitle(conv, e)} style={{ padding: 3, color: 'var(--text-dim)', background: 'none', border: 'none', flexShrink: 0, borderRadius: 'var(--radius-sm)' }}><Edit2 size={11} /></button>
                      <button onClick={(e) => deleteConversation(conv.id, e)} style={{ padding: 3, color: 'var(--red)', background: 'none', border: 'none', flexShrink: 0, borderRadius: 'var(--radius-sm)' }}><Trash2 size={11} /></button>
                    </div>
                  </>
                )}
              </div>
            ))}
            {conversations.length === 0 && (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12, letterSpacing: '0.06em', fontFamily: 'var(--font-sans)' }}>
                NO CONVERSATIONS
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Toolbar */}
        <div className="chat-toolbar">
          {/* Sidebar toggle */}
          <button onClick={() => setShowConvPanel(p => !p)} style={{
            padding: 5, color: showConvPanel ? 'var(--accent)' : 'var(--text-dim)',
            background: 'none', border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center',
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
          </button>

          <div className="chat-toolbar-separator" />

          {/* MODE group */}
          <div className="chat-toolbar-group">
            <span className="chat-toolbar-label">MODE</span>
            <div className="chat-mode-pill">
              {(['normal','fast','expert'] as const).map(m => {
                const active = chatMode === m
                const labels: Record<string, string> = { normal: 'NORMAL', fast: 'FAST', expert: 'EXPERT' }
                const titles: Record<string, string> = {
                  normal: '默认：LLM 解析意图决定是否调用子 agent',
                  fast: '快速：跳过意图解析，只用 Master Agent',
                  expert: '专家：并行派发给所有 active sub-agent，再汇总',
                }
                return (
                  <button key={m}
                    onClick={() => { setChatMode(m); localStorage.setItem('lastChatMode', m) }}
                    title={titles[m]}
                    className={active ? 'active' : undefined}>
                    {labels[m]}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="chat-toolbar-separator" />

          {/* MODEL group */}
          <div className="chat-toolbar-group">
            <span className="chat-toolbar-label">MODEL</span>
            <select value={providerModel} onChange={e => { localStorage.setItem('lastProviderModel', e.target.value); setProviderModel(e.target.value) }}
              className="chat-settings-select"
              style={{ width: 'auto', minWidth: 140, maxWidth: 260, height: 30, fontSize: 12 }}
              title={availableModels.length === 0 ? 'No verified models — go to Providers and click TEST' : undefined}
            >
              <option value="auto">AUTO</option>
              {availableModels.map(m => <option key={`${m.provider_id}:${m.model}`} value={`${m.provider_id}:${m.model}`}>{m.provider_name} / {m.model}</option>)}
            </select>
            {availableModels.length === 0 && (
              <span style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.06em' }}>no verified models</span>
            )}
          </div>

          <div className="chat-toolbar-separator" />

          {/* AGENT group */}
          <div className="chat-toolbar-group">
            <span className="chat-toolbar-label">AGENT</span>
            <select
              value={selectedAgentId}
              onChange={e => {
                const v = e.target.value
                setSelectedAgentId(v)
                if (v) localStorage.setItem('lastSelectedAgentId', v)
                else localStorage.removeItem('lastSelectedAgentId')
              }}
              title={selectedAgentId ? '已锁定到指定 Sub-Agent，绕过意图解析' : '由 Master Agent 解析意图后路由'}
              className="chat-settings-select"
              style={{
                width: 'auto', minWidth: 160, maxWidth: 280, height: 30, fontSize: 12,
                background: selectedAgentId ? 'rgba(0,255,65,0.08)' : undefined,
                border: selectedAgentId ? '1px solid var(--accent-border)' : undefined,
                color: selectedAgentId ? 'var(--accent)' : undefined,
              }}>
              <option value="">MASTER (AUTO ROUTE)</option>
              {availableAgents.map(a => (
                <option key={a.id} value={a.id}>
                  {a.agent_name}{a.backend_type ? ` · ${a.backend_type.toUpperCase()}` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Spacer + Actions */}
          {activeConvId && (
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <button
                onClick={() => setShowConvSettings(s => !s)}
                className={`chat-action-btn ${showConvSettings ? 'active' : ''}`}>
                <Settings size={12} /> SESSION
              </button>
              <button onClick={clearChat} className="chat-action-btn">
                CLEAR
              </button>
            </div>
          )}
        </div>

        {/* Session Settings Panel */}
        {showConvSettings && activeConvId && (
          <div className="chat-settings-panel">
            <div className="chat-settings-section">
              <div className="chat-settings-label">KNOWLEDGE BASE</div>
              <select
                value={convSettings.knowledge_base_id ?? ''}
                onChange={e => setConvSettings(s => ({ ...s, knowledge_base_id: e.target.value ? Number(e.target.value) : null }))}
                className="chat-settings-select">
                <option value="">— None —</option>
                {availableKBs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
              </select>
            </div>
            <div className="chat-settings-section">
              <div className="chat-settings-label">MODEL OVERRIDE</div>
              <select
                value={convSettings.model_override}
                onChange={e => setConvSettings(s => ({ ...s, model_override: e.target.value }))}
                className="chat-settings-select">
                <option value="">— Global Default —</option>
                {availableModels.map(m => <option key={`${m.provider_id}:${m.model}`} value={m.model}>{m.provider_name} / {m.model}</option>)}
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }} className="chat-settings-section">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div className="chat-settings-label" style={{ marginBottom: 0 }}>CUSTOM SYSTEM PROMPT</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--text-dim)', fontWeight: 600 }}>TEMPLATE</span>
                  <select
                    value=""
                    onChange={e => {
                      const id = e.target.value
                      if (!id) return
                      const tpl = promptTemplates.find(t => String(t.id) === id)
                      if (!tpl) return
                      if (convSettings.system_prompt_override.trim() &&
                          !confirm('Replace current system prompt with template "' + tpl.name + '"?')) {
                        e.target.value = ''
                        return
                      }
                      setConvSettings(s => ({ ...s, system_prompt_override: tpl.content }))
                      e.target.value = ''
                    }}
                    title={promptTemplates.length === 0 ? 'No templates — create one under Prompt Templates' : 'Pick a saved prompt template'}
                    className="chat-settings-select"
                    style={{ width: 'auto', minWidth: 180, height: 28, fontSize: 12 }}>
                    <option value="">— Select template —</option>
                    {promptTemplates.filter(t => t.category === 'system' || t.category === 'general').map(t => (
                      <option key={t.id} value={t.id}>{t.name}{t.category === 'general' ? ' (general)' : ''}</option>
                    ))}
                    {promptTemplates.filter(t => t.category !== 'system' && t.category !== 'general').length > 0 && (
                      <optgroup label="Other categories">
                        {promptTemplates.filter(t => t.category !== 'system' && t.category !== 'general').map(t => (
                          <option key={t.id} value={t.id}>{t.name} ({t.category})</option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  {convSettings.system_prompt_override && (
                    <button
                      onClick={() => setConvSettings(s => ({ ...s, system_prompt_override: '' }))}
                      className="chat-action-btn"
                      style={{ fontSize: 10, padding: '4px 8px' }}>CLEAR</button>
                  )}
                </div>
              </div>
              <textarea
                value={convSettings.system_prompt_override}
                onChange={e => setConvSettings(s => ({ ...s, system_prompt_override: e.target.value }))}
                rows={3}
                placeholder="Leave empty to use global default. Pick a saved template from the dropdown above, or type your own."
                className="chat-settings-textarea" />
            </div>
            <div className="chat-settings-footer">
              <button onClick={() => setShowConvSettings(false)} className="chat-action-btn">CANCEL</button>
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
                className="btn btn-primary btn-sm" style={{ fontWeight: 700 }}>
                SAVE SETTINGS
              </button>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="chat-messages">
          {!activeConvId ? (
            <div className="chat-empty">
              <div className="chat-empty-icon">⬡</div>
              <div className="chat-empty-text">SELECT OR CREATE A CONVERSATION</div>
              <button onClick={createConversation} className="chat-empty-btn">
                + {t('chat.newChat').toUpperCase()}
              </button>
            </div>
          ) : messages.length === 0 ? (
            <div className="chat-empty">
              <div style={{ fontSize: 36, opacity: 0.2, color: 'var(--accent)' }}>⬡</div>
              <div className="chat-empty-text" style={{ opacity: 0.6 }}>READY — SEND A MESSAGE</div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className={`chat-msg ${msg.role}`}>
                <div className="chat-msg-role">
                  {msg.role === 'user' ? '◆ OPERATOR' : msg.role === 'assistant' ? '◆ CYBERGUARD' : '◆ SYSTEM'}
                </div>
                <div className={`chat-msg-bubble ${msg.role}`}>
                  {msg.role === 'assistant' ? (
                    <div className="chat-markdown">
                      <ReactMarkdown
                        urlTransform={(url) => /^https?:\/\//i.test(url) ? url : '#'}
                      >{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
                  )}
                </div>
                {/* Render attachment previews for user messages */}
                {msg.role === 'user' && msg.attachments && msg.attachments.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                    {msg.attachments.map((att, idx) =>
                      att.type === 'image' ? (
                        <div key={`${att.name}-${att.size}-${idx}`} style={{ position: 'relative' }}>
                          <img
                            src={att.url}
                            onClick={() => setLightboxUrl(att.url || null)}
                            style={{
                              width: 72, height: 72, objectFit: 'cover',
                              border: '1px solid var(--accent-border)',
                              borderRadius: 'var(--radius-md)',
                              cursor: 'pointer',
                            }}
                          />
                        </div>
                      ) : (
                        <div key={`${att.name}-${att.size}-${idx}`} style={{
                          display: 'flex', alignItems: 'center', gap: 5,
                          padding: '5px 10px',
                          border: '1px solid var(--accent-border)',
                          borderRadius: 'var(--radius-md)',
                          fontSize: 12, color: 'var(--text-muted)',
                        }}>
                          <FileText size={11} />
                          <span>{att.name}</span>
                        </div>
                      )
                    )}
                  </div>
                )}
                {msg.created_at && <div className="chat-msg-time">{formatTime(msg.created_at)}</div>}
              </div>
            ))
          )}
          {pollingStatus && (
            <div className="chat-polling">
              <div className="chat-polling-dot" />
              {pollingStatus}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="chat-input-row">
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
            <div className="chat-attach-preview" style={{ width: '100%' }}>
              {attachments.map((att, i) => (
                <div key={i} className="chat-attach-chip">
                  {ACCEPTED_IMAGE_TYPES.includes(att.file.type) ? (
                    <ImageIcon size={12} style={{ color: 'var(--accent)' }} />
                  ) : (
                    <FileText size={12} style={{ color: 'var(--accent)' }} />
                  )}
                  <span style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {att.file.name}
                  </span>
                  <button
                    onClick={() => {
                      if (att.previewUrl) URL.revokeObjectURL(att.previewUrl)
                      setAttachments(prev => prev.filter((_, idx) => idx !== i))
                    }}>
                    <X size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={!activeConvId || loading}
            className="chat-input-btn">
            <Paperclip size={15} />
          </button>
          <textarea
            ref={textareaRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKey}
            placeholder={activeConvId ? 'Type your message...' : 'Select a conversation first...'}
            disabled={!activeConvId || loading}
            rows={1}
            className="chat-input-textarea"
          />
          <button
            onClick={() => {
              if (loading && activeTaskIdRef.current) {
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
            className={`chat-send-btn ${loading ? 'cancel' : ''}`}>
            {loading ? (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
            ) : <Send size={15} />}
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
                fontSize: 13,               }}>
              CLOSE
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
