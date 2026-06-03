/* eslint-disable @typescript-eslint/no-explicit-any */
const BASE = '/api/v1'

async function request(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.hash = '#/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) throw new Error(await res.text())
  const text = await res.text()
  if (!text) return null
  return JSON.parse(text)
}

export const api = {
  // Auth
  login: (body: { username: string; password: string }) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  refresh: (body: { refresh_token: string }) =>
    request('/auth/refresh', { method: 'POST', body: JSON.stringify(body) }),
  getAuthMe: () => request('/auth/me'),

  // Liveness probe — hits the root /health/ready (NOT under /api/v1) and never
  // triggers the 401 redirect; returns a coarse system status for the header.
  healthStatus: async (): Promise<'online' | 'degraded' | 'offline'> => {
    const token = localStorage.getItem('token')
    try {
      const res = await fetch('/health/ready', token ? { headers: { Authorization: `Bearer ${token}` } } : undefined)
      if (res.ok) return 'online'
      if (res.status === 503) return 'degraded'
      return 'offline'
    } catch {
      return 'offline'
    }
  },

  // SSO (Azure AD)
  getSsoStatus: () => request('/auth/sso/status'),
  getSsoConfig: () => request('/sso/config'),
  updateSsoConfig: (body: Record<string, unknown>) =>
    request('/sso/config', { method: 'PUT', body: JSON.stringify(body) }),
  getSsoRoleMappings: () => request('/sso/role-mappings'),
  createSsoRoleMapping: (body: { azure_key: string; app_role: string; priority?: number }) =>
    request('/sso/role-mappings', { method: 'POST', body: JSON.stringify(body) }),
  deleteSsoRoleMapping: (id: number) => request(`/sso/role-mappings/${id}`, { method: 'DELETE' }),
  getSecretEnvVars: () => request('/sso/secret-envvars'),

  // Users
  getUsers: () => request('/users'),
  getUserMe: () => request('/users/me'),
  createUser: (body: any) => request('/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id: number, body: any) => request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteUser: (id: number) => request(`/users/${id}`, { method: 'DELETE' }),

  // Providers
  getProviders: () => request('/providers'),
  createProvider: (body: any) => request('/providers', { method: 'POST', body: JSON.stringify(body) }),
  updateProvider: (id: string, body: any) => request(`/providers/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteProvider: (id: string) => request(`/providers/${id}`, { method: 'DELETE' }),
  testProvider: (id: number, model?: string) => request(`/providers/test`, {
    method: 'POST',
    body: JSON.stringify({ provider_id: id, ...(model ? { test_model: model } : {}) }),
  }),
  discoverProviderModels: (id: number) => request(`/providers/${id}/models/discover`),
  probeProviderModels: (id: number) => request(`/providers/${id}/models/probe`, { method: 'POST' }),

  // Agents
  getAgents: () => request('/agents'),
  createAgent: (body: any) => request('/agents', { method: 'POST', body: JSON.stringify(body) }),
  updateAgent: (id: string, body: any) => request(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAgent: (id: string) => request(`/agents/${id}`, { method: 'DELETE' }),
  testAgent: (id: string, body: any) => request(`/agents/${id}/test`, { method: 'POST', body: JSON.stringify(body) }),
  regenAgentApiKey: (id: string) => request(`/agents/${id}/api-key`, { method: 'POST' }),

  // Skills
  getSkills: (qs = '') => request('/skills' + qs),
  createSkill: (body: any) => request('/skills', { method: 'POST', body: JSON.stringify(body) }),
  updateSkill: (id: string, body: any) => request(`/skills/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteSkill: (id: string) => request(`/skills/${id}`, { method: 'DELETE' }),
  installSkillFromUrl: (body: { url: string; headers?: Record<string, string> }) =>
    request('/skills/install/url', { method: 'POST', body: JSON.stringify(body) }),
  importSkillFile: (formData: FormData) => {
    const token = localStorage.getItem('token')
    return fetch(`${BASE}/skills/import`, {
      method: 'POST',
      body: formData,
      headers: { Authorization: `Bearer ${token}` },
    }).then(r => r.json())
  },

  // Knowledge — knowledge bases
  getKnowledgeBases: () => request('/knowledge/bases'),
  getKnowledgeBase: (id: number) => request(`/knowledge/bases/${id}`),
  createKnowledgeBase: (body: any) => request('/knowledge/bases', { method: 'POST', body: JSON.stringify(body) }),
  updateKnowledgeBase: (id: number, body: any) => request(`/knowledge/bases/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteKnowledgeBase: (id: number) => request(`/knowledge/bases/${id}`, { method: 'DELETE' }),

  // Knowledge — documents
  getDocuments: (kbId: number) => request(`/knowledge/bases/${kbId}/documents`),
  ingestText: (kbId: number, body: { filename: string; content: string; mime_type?: string; provider_id?: number }) =>
    request(`/knowledge/bases/${kbId}/documents/text`, { method: 'POST', body: JSON.stringify(body) }),
  uploadDocument: async (kbId: number, file: File, providerId?: number) => {
    const token = localStorage.getItem('token')
    const fd = new FormData()
    fd.append('file', file)
    if (providerId != null) fd.append('provider_id', String(providerId))
    const res = await fetch(`${BASE}/knowledge/bases/${kbId}/documents/upload`, {
      method: 'POST',
      body: fd,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  deleteDocument: (kbId: number, docId: number) =>
    request(`/knowledge/bases/${kbId}/documents/${docId}`, { method: 'DELETE' }),

  // Knowledge — query
  queryKnowledge: (body: { kb_id: number; query: string; top_k?: number; similarity_threshold?: number; provider_id?: number }) =>
    request('/knowledge/query', { method: 'POST', body: JSON.stringify(body) }),

  // Chat (async task via Celery — for complex requests with agents/attachments)
  chat: (body: { message: string; agent_id?: string; provider_id?: number; model?: string; conversation_id?: number; mode?: string }) =>
    request('/chat', { method: 'POST', body: JSON.stringify(body) }),

  // Chat stream (SSE — for simple text-only conversations)
  chatStream: async function* (body: { message: string; conversation_id?: number; provider_id?: number; model?: string }) {
    const token = localStorage.getItem('token')
    const res = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await res.text())
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()!
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { yield JSON.parse(line.slice(6)) } catch { /* skip malformed */ }
        }
      }
    }
  },

  // Stream a single sub-agent run (SSE): start / tool_call_start / tool_call_end / text / done / error
  executeAgentStream: async function* (
    agentId: string | number,
    task: string,
    conversationId?: number,
  ) {
    const token = localStorage.getItem('token')
    const res = await fetch(`${BASE}/agents/${agentId}/execute/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ task, conversation_id: conversationId }),
    })
    if (!res.ok) throw new Error(await res.text())
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()!
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { yield JSON.parse(line.slice(6)) } catch { /* skip malformed */ }
        }
      }
    }
  },

  // Chat with attachments (multipart/form-data)
  uploadChatAttachments: (
    files: File[],
    message: string,
    conversationId: number,
    modelOverride?: { provider_id?: number; model?: string },
    agentId?: string,
    mode?: string,
  ) => {
    const token = localStorage.getItem('token')
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    fd.append('message', message)
    fd.append('conversation_id', String(conversationId))
    if (modelOverride?.provider_id) fd.append('provider_id', String(modelOverride.provider_id))
    if (modelOverride?.model) fd.append('model', modelOverride.model)
    if (agentId) fd.append('agent_id', agentId)
    if (mode) fd.append('mode', mode)
    return fetch(`${BASE}/chat/attachments`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    }).then(async r => {
      if (!r.ok) throw new Error(await r.text())
      return r.json()
    })
  },

  // Tasks
  getTasks: () => request('/tasks'),
  getTask: (id: string) => request(`/tasks/${id}`),
  cancelTask: (id: string) => request(`/tasks/${id}/cancel`, { method: 'POST' }),
  createTask: (body: any) => request('/tasks', { method: 'POST', body: JSON.stringify(body) }),
  updateTask: (id: string, body: any) => request(`/tasks/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteTask: (id: string) => request(`/tasks/${id}`, { method: 'DELETE' }),

  // Schedule
  getScheduledTasks: () => request('/schedule'),
  createScheduledTask: (body: any) => request('/schedule', { method: 'POST', body: JSON.stringify(body) }),
  updateScheduledTask: (id: string, body: any) => request(`/schedule/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteScheduledTask: (id: string) => request(`/schedule/${id}`, { method: 'DELETE' }),

  // ---- Approvals ----
  getApprovals: (statusFilter: 'pending' | 'approved' | 'rejected' | 'all' = 'pending') =>
    request(`/approvals?status_filter=${statusFilter}`),
  decideApproval: (id: number, decision: 'approved' | 'rejected', comment?: string) =>
    request(`/approvals/${id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, comment }),
    }),

  // Audit
  getAuditLogs: (params?: { user_id?: number; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.user_id) q.set('user_id', String(params.user_id))
    if (params?.limit) q.set('limit', String(params.limit))
    if (params?.offset) q.set('offset', String(params.offset))
    const qs = q.toString()
    return request(`/audit/logs${qs ? '?' + qs : ''}`)
  },
  exportAuditLogs: (params?: any) =>
    request(`/audit/export?${new URLSearchParams(params || {})}`),

  // Backup
  listBackups: () => request('/backup'),
  createBackup: (body?: any) => request('/backup', { method: 'POST', body: JSON.stringify(body || {}) }),
  restoreBackup: (id: string) =>
    request(`/backup/${id}/restore`, {
      method: 'POST',
      body: JSON.stringify({ backup_id: id, confirm: true }),
    }),

  // Config
  exportConfig: () => request('/config/export', { method: 'POST' }),
  getMasterConfig: () => request('/master-config'),
  updateMasterConfig: (body: any) => request('/master-config', { method: 'PUT', body: JSON.stringify(body) }),

  // OCR
  getOcrConfig: () => request('/ocr/config'),
  updateOcrConfig: (body: {
    enabled?: boolean; engine?: string; vision_provider_id?: number | null;
    vision_model?: string | null; languages?: string; max_pages?: number;
  }) => request('/ocr/config', { method: 'PUT', body: JSON.stringify(body) }),

  // Conversations
  getConversations: () => request('/conversations'),
  createConversation: (body?: {
    title?: string
    system_prompt_override?: string | null
    intent_parser_prompt_override?: string | null
    summarizer_prompt_override?: string | null
    model_override?: string | null
    temperature_override?: number | null
    knowledge_base_id?: number | null
  }) => request('/conversations', { method: 'POST', body: JSON.stringify(body || {}) }),
  getConversation: (id: number) => request(`/conversations/${id}`),
  updateConversation: (id: number, body: {
    title?: string
    messages_json?: string
    system_prompt_override?: string | null
    intent_parser_prompt_override?: string | null
    summarizer_prompt_override?: string | null
    model_override?: string | null
    temperature_override?: number | null
    knowledge_base_id?: number | null
  }) =>
    request(`/conversations/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteConversation: (id: number) => request(`/conversations/${id}`, { method: 'DELETE' }),
  appendConversationMessage: (id: number, body: { role: string; content: string }) =>
    request(`/conversations/${id}/messages`, { method: 'POST', body: JSON.stringify(body) }),
  getConversationMessages: (id: number) => request(`/conversations/${id}/messages`),
  importConfig: (body: any) => request('/config/import', { method: 'POST', body: JSON.stringify(body) }),

  // Group Chat (Multi-Agent)
  createGroupChatSession: (body: { agent_ids: number[]; initial_message: string; max_rounds?: number }) =>
    request('/groupchat/sessions', { method: 'POST', body: JSON.stringify(body) }),
  getGroupChatSession: (sessionId: string) =>
    request(`/groupchat/sessions/${sessionId}`),
  runGroupChatRound: (sessionId: string) =>
    request(`/groupchat/sessions/${sessionId}/round`, { method: 'POST' }),
  runGroupChatComplete: (sessionId: string) =>
    request(`/groupchat/sessions/${sessionId}/complete`, { method: 'POST' }),
  cancelGroupChatSession: (sessionId: string) =>
    request(`/groupchat/sessions/${sessionId}`, { method: 'DELETE' }),

  // ---- MCP Servers ----
  getMCPServers: () => request('/mcp/servers'),
  createMCPServer: (body: any) => request('/mcp/servers', { method: 'POST', body: JSON.stringify(body) }),
  updateMCPServer: (id: number, body: any) => request(`/mcp/servers/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteMCPServer: (id: number) => request(`/mcp/servers/${id}`, { method: 'DELETE' }),
  startMCPServer: (id: number) => request(`/mcp/servers/${id}/start`, { method: 'POST' }),
  stopMCPServer: (id: number) => request(`/mcp/servers/${id}/stop`, { method: 'POST' }),
  getMCPServerTools: (serverId: number) => request(`/mcp/servers/${serverId}/tools`),
  getAllMcpTools: (qs = '') => request('/mcp/tools/all' + qs),

  // MCP Tools
  createMCPTool: (body: any) => request('/mcp/tools', { method: 'POST', body: JSON.stringify(body) }),
  updateMCPTool: (id: number, body: any) => request(`/mcp/tools/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteMCPTool: (id: number) => request(`/mcp/tools/${id}`, { method: 'DELETE' }),
  executeMCPTool: (body: { tool_id: number; arguments: Record<string, unknown> }) =>
    request('/mcp/tools/execute', { method: 'POST', body: JSON.stringify(body) }),

  // ---- Environment Variables ----
  getEnvVars: () => request('/envvars'),
  createEnvVar: (body: { key: string; value: string; value_type: string; description?: string }) =>
    request('/envvars', { method: 'POST', body: JSON.stringify(body) }),
  updateEnvVar: (id: number, body: { value?: string; value_type?: string; description?: string; is_active?: boolean }) =>
    request(`/envvars/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteEnvVar: (id: number) => request(`/envvars/${id}`, { method: 'DELETE' }),
  decryptEnvVar: (id: number) => request(`/envvars/decrypt/${id}`),

  // ---- N8N ----
  getN8NConnections: () => request('/n8n/connections'),
  createN8NConnection: (body: { name: string; base_url: string; api_key?: string; is_active?: boolean; is_default?: boolean }) =>
    request('/n8n/connections', { method: 'POST', body: JSON.stringify(body) }),
  updateN8NConnection: (id: number, body: { name?: string; base_url?: string; api_key?: string; is_active?: boolean; is_default?: boolean }) =>
    request(`/n8n/connections/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteN8NConnection: (id: number) => request(`/n8n/connections/${id}`, { method: 'DELETE' }),
  testN8NConnection: (id: number) => request(`/n8n/connections/${id}/test`, { method: 'POST' }),
  getN8NWorkflows: (connectionId?: number) =>
    request(connectionId ? `/n8n/workflows?connection_id=${connectionId}` : '/n8n/workflows'),
  getN8NWorkflow: (id: string, connectionId?: number) =>
    request(connectionId ? `/n8n/workflows/${id}?connection_id=${connectionId}` : `/n8n/workflows/${id}`),
  createN8NWorkflow: (body: { name: string; workflow_json: any; connection_id?: number }) =>
    request('/n8n/workflows', { method: 'POST', body: JSON.stringify(body) }),
  updateN8NWorkflow: (id: string, body: { workflow_json: any; connection_id?: number }) =>
    request(`/n8n/workflows/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteN8NWorkflow: (id: string, connectionId?: number) =>
    request(connectionId ? `/n8n/workflows/${id}?connection_id=${connectionId}` : `/n8n/workflows/${id}`, { method: 'DELETE' }),
  generateN8NWorkflow: (body: { description: string; connection_id?: number }) =>
    request('/n8n/workflows/generate', { method: 'POST', body: JSON.stringify(body) }),

  // ---- Governance ----
  // Frameworks
  getFrameworks: () => request('/governance/frameworks'),
  getFramework: (id: number) => request(`/governance/frameworks/${id}`),
  importFramework: (body: any) =>
    request('/governance/frameworks/import', { method: 'POST', body: JSON.stringify(body) }),
  deleteFramework: (id: number) =>
    request(`/governance/frameworks/${id}`, { method: 'DELETE' }),

  // Assessments
  getAssessments: () => request('/governance/assessments'),
  getAssessment: (id: number) => request(`/governance/assessments/${id}`),
  createAssessment: (body: {
    name: string
    description?: string
    framework_id: number
    scope?: string
    start_date?: string
    due_date?: string
  }) => request('/governance/assessments', { method: 'POST', body: JSON.stringify(body) }),
  updateAssessment: (id: number, body: any) =>
    request(`/governance/assessments/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAssessment: (id: number) =>
    request(`/governance/assessments/${id}`, { method: 'DELETE' }),
  getAssessmentRequirements: (id: number) =>
    request(`/governance/assessments/${id}/requirements`),

  // Requirement assessments + evidence
  updateRequirementAssessment: (raId: number, body: { status?: string; score?: number | null; observation?: string }) =>
    request(`/governance/req-assessments/${raId}`, { method: 'PUT', body: JSON.stringify(body) }),
  addEvidence: (raId: number, body: { name: string; description?: string; kind: 'text' | 'url' | 'file'; url?: string; body?: string; mime_type?: string }) =>
    request(`/governance/req-assessments/${raId}/evidence`, { method: 'POST', body: JSON.stringify(body) }),
  deleteEvidence: (id: number) =>
    request(`/governance/evidence/${id}`, { method: 'DELETE' }),

  uploadEvidenceFile: async (raId: number, file: File, name: string, description?: string) => {
    const token = localStorage.getItem('token')
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name)
    if (description) fd.append('description', description)
    const res = await fetch(`${BASE}/governance/req-assessments/${raId}/evidence/file`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) }, // no Content-Type: browser sets multipart boundary
      body: fd,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  downloadEvidence: async (id: number, filename: string) => {
    const token = localStorage.getItem('token')
    const res = await fetch(`${BASE}/governance/evidence/${id}/download`, {
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
    if (!res.ok) throw new Error(await res.text())
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },

  // AI helpers
  aiSuggestEvidence: (raId: number) =>
    request(`/governance/req-assessments/${raId}/ai-suggest-evidence`, { method: 'POST' }),
  aiAssessRequirement: (raId: number, body: { extra_context?: string; apply?: boolean }) =>
    request(`/governance/req-assessments/${raId}/ai-assess`, { method: 'POST', body: JSON.stringify(body) }),
  aiGenerateReport: (assessmentId: number) =>
    request(`/governance/assessments/${assessmentId}/ai-report`, { method: 'POST' }),

  // ---- Prompt Templates ----
  getPromptTemplates: (category?: string) =>
    request(category ? `/prompt-templates?category=${encodeURIComponent(category)}` : '/prompt-templates'),
  getPromptTemplate: (id: number) => request(`/prompt-templates/${id}`),
  createPromptTemplate: (body: {
    name: string
    description?: string
    content: string
    category?: 'system' | 'intent_parser' | 'summarizer' | 'general'
    is_active?: boolean
  }) => request('/prompt-templates', { method: 'POST', body: JSON.stringify(body) }),
  updatePromptTemplate: (id: number, body: {
    name?: string
    description?: string
    content?: string
    category?: 'system' | 'intent_parser' | 'summarizer' | 'general'
    is_active?: boolean
  }) => request(`/prompt-templates/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deletePromptTemplate: (id: number) =>
    request(`/prompt-templates/${id}`, { method: 'DELETE' }),

  // ---- Tools (executable tool pool) ----
  getTools: (qs = '') => request('/tools' + qs),
  createTool: (body: any) => request('/tools', { method: 'POST', body: JSON.stringify(body) }),
  updateTool: (id: number, body: any) => request(`/tools/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteTool: (id: number) => request(`/tools/${id}`, { method: 'DELETE' }),
  executeTool: (id: number, args: Record<string, any>) =>
    request(`/tools/${id}/execute`, { method: 'POST', body: JSON.stringify({ args }) }),

  // ---- Security Settings ----
  getSecuritySettings: () => request('/security-settings'),
  updateSecuritySettings: (body: Record<string, unknown>) =>
    request('/security-settings', { method: 'PUT', body: JSON.stringify(body) }),

  // ---- Token Usage ----
  getTokenUsageSummary: () => request('/token-usage/summary'),

  // ---- Webhooks ----
  getWebhooks: () => request('/webhooks'),
  createWebhook: (body: {
    name: string
    direction: 'incoming' | 'outgoing'
    description?: string
    is_active?: boolean
    outgoing_url?: string
    outgoing_events?: string[]
    outgoing_secret?: string
  }) => request('/webhooks', { method: 'POST', body: JSON.stringify(body) }),
  updateWebhook: (id: number, body: any) =>
    request(`/webhooks/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteWebhook: (id: number) =>
    request(`/webhooks/${id}`, { method: 'DELETE' }),
  regenWebhookToken: (id: number) =>
    request(`/webhooks/${id}/regenerate-token`, { method: 'POST' }),
  testWebhook: (id: number) =>
    request(`/webhooks/${id}/test`, { method: 'POST', body: JSON.stringify({}) }),
}

export const wsBase = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`
