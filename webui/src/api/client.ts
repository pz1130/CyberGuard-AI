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
  testProvider: (id: number) => request(`/providers/test`, {
    method: 'POST',
    body: JSON.stringify({ provider_id: id }),
  }),

  // Agents
  getAgents: () => request('/agents'),
  createAgent: (body: any) => request('/agents', { method: 'POST', body: JSON.stringify(body) }),
  updateAgent: (id: string, body: any) => request(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAgent: (id: string) => request(`/agents/${id}`, { method: 'DELETE' }),
  testAgent: (id: string, body: any) => request(`/agents/${id}/test`, { method: 'POST', body: JSON.stringify(body) }),
  regenAgentApiKey: (id: string) => request(`/agents/${id}/api-key`, { method: 'POST' }),

  // Skills
  getSkills: () => request('/skills'),
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

  // Chat
  chat: (body: { message: string; agent_id?: string; provider_id?: number; model?: string; conversation_id?: number }) =>
    request('/chat', { method: 'POST', body: JSON.stringify(body) }),

  // Chat with attachments (multipart/form-data)
  uploadChatAttachments: (
    files: File[],
    message: string,
    conversationId: number,
    modelOverride?: { provider_id?: number; model?: string },
    agentId?: string,
  ) => {
    const token = localStorage.getItem('token')
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    fd.append('message', message)
    fd.append('conversation_id', String(conversationId))
    if (modelOverride?.provider_id) fd.append('provider_id', String(modelOverride.provider_id))
    if (modelOverride?.model) fd.append('model', modelOverride.model)
    if (agentId) fd.append('agent_id', agentId)
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
  createTask: (body: any) => request('/tasks', { method: 'POST', body: JSON.stringify(body) }),
  updateTask: (id: string, body: any) => request(`/tasks/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteTask: (id: string) => request(`/tasks/${id}`, { method: 'DELETE' }),

  // Schedule
  getScheduledTasks: () => request('/schedule'),
  createScheduledTask: (body: any) => request('/schedule', { method: 'POST', body: JSON.stringify(body) }),
  updateScheduledTask: (id: string, body: any) => request(`/schedule/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteScheduledTask: (id: string) => request(`/schedule/${id}`, { method: 'DELETE' }),

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
  getAllMcpTools: () => request('/mcp/tools/all'),

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
}

export const wsBase = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`
