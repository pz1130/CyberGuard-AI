/**
 * CyberGuard Sidebar
 * Taste-skill: 21-module SOC console, restrained operational UI.
 * - 264px fixed column, no version label, no decorative dots.
 * - One accent (emerald), one radius scale, sans-serif body.
 * - Active state: 2px left border in accent + accent-dim background.
 * - Search input at top, no per-item status decoration.
 */
import {
  MessageSquare, Cpu, Plug, Wrench, Terminal, BookOpen, Users,
  Clock, Settings, Shield, Coins, Database, FileText, UserCog,
  GitBranch, Webhook, ScrollText, ClipboardCheck, ShieldCheck,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

export type Tab =
  | 'chat' | 'agents' | 'providers' | 'skills' | 'tools'
  | 'knowledge' | 'groupchat' | 'schedule' | 'mcp' | 'envvars'
  | 'security' | 'token' | 'backup' | 'audit' | 'approvals'
  | 'users' | 'settings' | 'n8n' | 'webhooks' | 'prompts' | 'governance'

type NavItem = {
  key: Tab
  labelKey: string
  icon: React.ReactNode
}

interface NavGroup {
  id: 'core' | 'agents' | 'features' | 'ops'
  labelKey: string
  items: NavItem[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    id: 'core',
    labelKey: 'nav.core',
    items: [
      { key: 'chat', labelKey: 'nav.chat', icon: <MessageSquare size={16} /> },
    ],
  },
  {
    id: 'agents',
    labelKey: 'nav.agents',
    items: [
      { key: 'agents', labelKey: 'nav.agents', icon: <Cpu size={16} /> },
      { key: 'providers', labelKey: 'nav.providers', icon: <Plug size={16} /> },
    ],
  },
  {
    id: 'features',
    labelKey: 'nav.features',
    items: [
      { key: 'skills', labelKey: 'nav.skills', icon: <Wrench size={16} /> },
      { key: 'tools', labelKey: 'nav.tools', icon: <Terminal size={16} /> },
      { key: 'prompts', labelKey: 'nav.prompts', icon: <ScrollText size={16} /> },
      { key: 'knowledge', labelKey: 'nav.knowledge', icon: <BookOpen size={16} /> },
      { key: 'groupchat', labelKey: 'nav.groupchat', icon: <Users size={16} /> },
      { key: 'n8n', labelKey: 'nav.n8n', icon: <GitBranch size={16} /> },
      { key: 'webhooks', labelKey: 'nav.webhooks', icon: <Webhook size={16} /> },
      { key: 'governance', labelKey: 'nav.governance', icon: <ClipboardCheck size={16} /> },
    ],
  },
  {
    id: 'ops',
    labelKey: 'nav.ops',
    items: [
      { key: 'schedule', labelKey: 'nav.schedule', icon: <Clock size={16} /> },
      { key: 'mcp', labelKey: 'nav.mcp', icon: <Plug size={16} /> },
      { key: 'envvars', labelKey: 'nav.envvars', icon: <Settings size={16} /> },
      { key: 'security', labelKey: 'nav.security', icon: <Shield size={16} /> },
      { key: 'token', labelKey: 'nav.token', icon: <Coins size={16} /> },
      { key: 'backup', labelKey: 'nav.backup', icon: <Database size={16} /> },
      { key: 'audit', labelKey: 'nav.audit', icon: <FileText size={16} /> },
      { key: 'approvals', labelKey: 'nav.approvals', icon: <ShieldCheck size={16} /> },
      { key: 'users', labelKey: 'nav.users', icon: <UserCog size={16} /> },
      { key: 'settings', labelKey: 'nav.settings', icon: <Settings size={16} /> },
    ],
  },
]

interface Props {
  tab: Tab
  setTab: (t: Tab) => void
}

export default function SidebarNew({ tab, setTab }: Props) {
  const { t } = useTranslation()

  return (
    <aside
      className="sidebar-shell"
      style={{
        position: 'fixed',
        left: 0,
        top: 'var(--header-height)',
        bottom: 0,
        width: 'var(--sidebar-width)',
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 40,
        overflow: 'hidden',
      }}
    >
      <nav
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: '8px 8px 16px',
        }}
      >
        {NAV_GROUPS.map((group) => (
          <div key={group.id} style={{ marginTop: 12 }}>
            <div
              style={{
                padding: '4px 10px 6px',
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--text-dim)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {t(group.labelKey)}
            </div>

            {group.items.map((item) => {
              const isActive = tab === item.key
              return (
                <button
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  aria-current={isActive ? 'page' : undefined}
                  className={isActive ? 'nav-glass' : undefined}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    width: '100%',
                    padding: '7px 10px',
                    marginBottom: 1,
                    background: isActive ? undefined : 'transparent',
                    border: isActive ? undefined : 'none',
                    borderRadius: 'var(--radius-md)',
                    color: isActive ? 'var(--accent)' : 'var(--text-muted)',
                    fontSize: 13,
                    fontWeight: isActive ? 500 : 400,
                    cursor: 'pointer',
                    transition:
                      'background var(--transition-fast), color var(--transition-fast)',
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = 'var(--bg-hover)'
                      e.currentTarget.style.color = 'var(--text-primary)'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = 'transparent'
                      e.currentTarget.style.color = 'var(--text-muted)'
                    }
                  }}
                >
                  {isActive && <span className="nav-pulse-dot" />}
                  <span
                    style={{
                      display: 'inline-flex',
                      opacity: isActive ? 1 : 0.85,
                    }}
                  >
                    {item.icon}
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }} className="truncate">
                    {t(item.labelKey)}
                  </span>
                </button>
              )
            })}
          </div>
        ))}

      </nav>

      <div
        style={{
          padding: '10px 14px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: 11,
          color: 'var(--text-dim)',
        }}
      >
        <span className="font-mono">Ctrl+K</span>
        <span>{t('nav.quickJump') || 'Quick jump'}</span>
      </div>
    </aside>
  )
}
