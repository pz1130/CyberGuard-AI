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
  return res.json()
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

  // Agents
  getAgents: () => request('/agents'),
  createAgent: (body: any) => request('/agents', { method: 'POST', body: JSON.stringify(body) }),
  updateAgent: (id: string, body: any) => request(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAgent: (id: string) => request(`/agents/${id}`, { method: 'DELETE' }),
  testAgent: (id: string, body: any) => request(`/agents/${id}/test`, { method: 'POST', body: JSON.stringify(body) }),

  // Skills
  getSkills: () => request('/skills'),
  createSkill: (body: any) => request('/skills', { method: 'POST', body: JSON.stringify(body) }),
  updateSkill: (id: string, body: any) => request(`/skills/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteSkill: (id: string) => request(`/skills/${id}`, { method: 'DELETE' }),

  // Knowledge
  getKnowledgeBases: () => request('/knowledge/bases'),
  createKnowledgeBase: (body: any) => request('/knowledge/bases', { method: 'POST', body: JSON.stringify(body) }),
  queryKnowledge: (body: { query: string; top_k?: number }) =>
    request('/knowledge/query', { method: 'POST', body: JSON.stringify(body) }),

  // Chat
  chat: (body: { message: string; agent_id?: string }) =>
    request('/chat', { method: 'POST', body: JSON.stringify(body) }),

  // Tasks
  getTasks: () => request('/tasks'),
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
  restoreBackup: (id: string) => request(`/backup/${id}/restore`, { method: 'POST' }),

  // Config
  exportConfig: () => request('/config/export'),
  importConfig: (body: any) => request('/config/import', { method: 'POST', body: JSON.stringify(body) }),

  // MCP
  getMCPServers: () => request('/mcp'),
  createMCPServer: (body: any) => request('/mcp', { method: 'POST', body: JSON.stringify(body) }),
  deleteMCPServer: (name: string) => request(`/mcp/${name}`, { method: 'DELETE' }),
}

export const wsBase = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`
