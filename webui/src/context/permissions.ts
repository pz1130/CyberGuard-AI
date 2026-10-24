import { createContext } from 'react'
import type { Tab } from '../components/SidebarNew'

export const RoleContext = createContext('')
const grants: Record<string, string[]> = {
  operator: ['finding:read', 'finding:submit', 'finding:manage', 'agent:read', 'agent:execute', 'skill:read', 'knowledge:read', 'task:read', 'task:write', 'task:execute'],
  analyst: ['finding:read', 'finding:submit', 'finding:manage', 'finding:review', 'agent:read', 'skill:read', 'knowledge:read', 'task:read'],
  viewer: ['agent:read', 'skill:read', 'task:read'],
  approver: ['finding:read', 'finding:review', 'approval:read', 'approval:decide'],
  auditor: ['finding:read', 'audit:read', 'task:read'],
}
export function hasPermission(role: string, permission: string): boolean {
  return role === 'admin' || (grants[role] || []).includes(permission)
}
const pagePermissions: Record<Tab, string> = {
  findings: 'finding:read', chat: 'task:execute', agents: 'agent:read', providers: 'agent:read',
  skills: 'skill:read', tools: 'skill:read', knowledge: 'knowledge:read',
  mcp: 'agent:read', envvars: 'settings:read', security: 'settings:read',
  token: 'admin:all', backup: 'admin:all', audit: 'audit:read',
  approvals: 'approval:read', users: 'user:read', settings: 'settings:read',
  prompts: 'settings:read', govDashboard: 'settings:read',
}
export function canAccessTab(role: string, tab: Tab): boolean {
  return hasPermission(role, pagePermissions[tab])
}
