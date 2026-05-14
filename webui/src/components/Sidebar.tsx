import { MessageSquare, Cpu, Plug, Wrench, BookOpen, Users, Clock, Settings, Shield, Coins, Database, FileText, UserCog, GitBranch, Webhook, ScrollText, ClipboardCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export type Tab = 'chat' | 'agents' | 'providers' | 'skills' | 'knowledge' | 'groupchat' | 'schedule' | 'mcp' | 'envvars' | 'security' | 'token' | 'backup' | 'audit' | 'users' | 'settings' | 'n8n' | 'webhooks' | 'prompts' | 'governance'

type NavItem = { key: Tab; labelKey: string; icon: React.ReactNode; group: string }
const NAV_ITEMS: NavItem[] = [
  { key: 'chat', labelKey: 'nav.chat', icon: <MessageSquare size={13} />, group: 'CORE' },
  { key: 'agents', labelKey: 'nav.agents', icon: <Cpu size={13} />, group: 'AGENTS' },
  { key: 'providers', labelKey: 'nav.providers', icon: <Plug size={13} />, group: 'AGENTS' },
  { key: 'skills', labelKey: 'nav.skills', icon: <Wrench size={13} />, group: 'FEATURES' },
  { key: 'prompts', labelKey: 'nav.prompts', icon: <ScrollText size={13} />, group: 'FEATURES' },
  { key: 'knowledge', labelKey: 'nav.knowledge', icon: <BookOpen size={13} />, group: 'FEATURES' },
  { key: 'groupchat', labelKey: 'nav.groupchat', icon: <Users size={13} />, group: 'FEATURES' },
  { key: 'n8n', labelKey: 'nav.n8n', icon: <GitBranch size={13} />, group: 'FEATURES' },
  { key: 'webhooks', labelKey: 'nav.webhooks', icon: <Webhook size={13} />, group: 'FEATURES' },
  { key: 'governance', labelKey: 'nav.governance', icon: <ClipboardCheck size={13} />, group: 'FEATURES' },
  { key: 'schedule', labelKey: 'nav.schedule', icon: <Clock size={13} />, group: 'OPS' },
  { key: 'mcp', labelKey: 'nav.mcp', icon: <Plug size={13} />, group: 'OPS' },
  { key: 'envvars', labelKey: 'nav.envvars', icon: <Settings size={13} />, group: 'OPS' },
  { key: 'security', labelKey: 'nav.security', icon: <Shield size={13} />, group: 'OPS' },
  { key: 'token', labelKey: 'nav.token', icon: <Coins size={13} />, group: 'OPS' },
  { key: 'backup', labelKey: 'nav.backup', icon: <Database size={13} />, group: 'OPS' },
  { key: 'audit', labelKey: 'nav.audit', icon: <FileText size={13} />, group: 'OPS' },
  { key: 'users', labelKey: 'nav.users', icon: <UserCog size={13} />, group: 'OPS' },
  { key: 'settings', labelKey: 'nav.settings', icon: <Settings size={13} />, group: 'OPS' },
]

const GROUP_KEYS: Record<string, string> = { CORE: 'nav.core', AGENTS: 'nav.features', FEATURES: 'nav.features', OPS: 'nav.ops' }

interface Props {
  tab: Tab
  setTab: (t: Tab) => void
  onCollapse?: (c: boolean) => void
}

export default function Sidebar({ tab, setTab }: Props) {
  const { t } = useTranslation()
  return (
    <aside style={{
      position: 'fixed',
      left: 0, top: 'var(--header-height)', bottom: 0,
      width: 'var(--sidebar-width)',
      background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border)',
      overflowY: 'auto', overflowX: 'hidden',
      zIndex: 40,
      padding: '16px 0',
    }}>
      {/* Version tag */}
      <div style={{
        padding: '0 16px', marginBottom: 16,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: 9, letterSpacing: '0.25em', color: 'var(--text-dim)' }}>
          ◆ CYBERGUARD OS v1.0.0
        </span>
        <span style={{
          fontSize: 9, letterSpacing: '0.15em', color: 'var(--accent)',
          background: 'var(--accent-dim)',
          padding: '2px 6px',
          border: '1px solid var(--accent-border)',
        }}>
          ACTIVE
        </span>
      </div>

      {(['CORE', 'AGENTS', 'FEATURES', 'OPS'] as const).map((group) => {
        const items = NAV_ITEMS.filter(i => i.group === group)
        if (!items.length) return null
        return (
          <div key={group} style={{ marginBottom: 8 }}>
            {/* Group label */}
            <div style={{
              padding: '8px 16px 4px',
              fontSize: 9, letterSpacing: '0.2em',
              color: 'var(--text-dim)', fontWeight: 600,
              borderTop: '1px solid var(--border)',
              marginTop: items[0]?.group === 'CORE' ? 0 : 8,
            }}>
              {t(GROUP_KEYS[group] || group)}
            </div>

            {items.map((item) => {
              const active = tab === item.key
              return (
                <button
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    width: '100%', padding: '0 16px',
                    height: 36,
                    background: active ? 'var(--accent-dim)' : 'transparent',
                    borderLeft: active ? '2px solid var(--accent)' : '2px solid transparent',
                    color: active ? 'var(--accent)' : 'var(--text-muted)',
                    fontSize: 11, letterSpacing: '0.08em', fontWeight: active ? 600 : 400,
                    cursor: 'pointer', transition: 'all 0.15s',
                    fontFamily: 'var(--font-mono)',
                  }}
                  onMouseEnter={e => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'
                      ;(e.currentTarget as HTMLElement).style.color = 'var(--text-primary)'
                    }
                  }}
                  onMouseLeave={e => {
                    if (!active) {
                      (e.currentTarget as HTMLElement).style.background = 'transparent'
                      ;(e.currentTarget as HTMLElement).style.color = 'var(--text-muted)'
                    }
                  }}
                >
                  <span style={{ opacity: active ? 1 : 0.6 }}>{item.icon}</span>
                  <span style={{ flex: 1, textAlign: 'left' }}>{t(item.labelKey)}</span>
                  {active && (
                    <span style={{
                      width: 4, height: 4, borderRadius: '50%',
                      background: 'var(--accent)',
                      boxShadow: '0 0 6px var(--accent)',
                    }} />
                  )}
                </button>
              )
            })}
          </div>
        )
      })}

      {/* Bottom status */}
      <div style={{
        position: 'sticky', bottom: 0,
        background: 'var(--bg-surface)',
        borderTop: '1px solid var(--border)',
        padding: '12px 16px', marginTop: 16,
      }}>
        <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.15em', lineHeight: 1.8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>SYS</span>
            <span style={{ color: 'var(--accent)' }}>NOMINAL</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>MEM</span>
            <span>62%</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>UPTIME</span>
            <span>99.97%</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
