import {
  MessageSquare, Cpu, Wrench, BookOpen, Radio, Clock, Puzzle, Settings,
  Shield, Coins, Database, FileText, UserCog, Plug, ShieldCheck,
} from 'lucide-react'

export type Tab =
  | 'chat' | 'agents' | 'providers' | 'skills' | 'knowledge' | 'groupchat'
  | 'schedule' | 'mcp' | 'envvars' | 'security' | 'token' | 'backup' | 'audit' | 'users'

interface Group {
  label: string
  items: { key: Tab; label: string; icon: React.ReactNode }[]
}

const GROUPS: Group[] = [
  {
    label: '核心',
    items: [
      { key: 'chat', label: '聊天', icon: <MessageSquare size={16} /> },
      { key: 'providers', label: 'AI Provider', icon: <Puzzle size={16} /> },
      { key: 'agents', label: 'Sub-Agent', icon: <Cpu size={16} /> },
      { key: 'skills', label: 'Skill Pool', icon: <Wrench size={16} /> },
    ],
  },
  {
    label: '功能',
    items: [
      { key: 'knowledge', label: '知识库', icon: <BookOpen size={16} /> },
      { key: 'groupchat', label: '群聊室', icon: <Radio size={16} /> },
      { key: 'schedule', label: '定时任务', icon: <Clock size={16} /> },
      { key: 'mcp', label: 'MCP', icon: <Plug size={16} /> },
    ],
  },
  {
    label: '运维',
    items: [
      { key: 'envvars', label: '环境变量', icon: <Settings size={16} /> },
      { key: 'security', label: '安全', icon: <ShieldCheck size={16} /> },
      { key: 'token', label: 'Token 消耗', icon: <Coins size={16} /> },
      { key: 'backup', label: '备份', icon: <Database size={16} /> },
      { key: 'audit', label: '审计日志', icon: <FileText size={16} /> },
      { key: 'users', label: '用户管理', icon: <UserCog size={16} /> },
    ],
  },
]

interface Props {
  tab: Tab
  setTab: (t: Tab) => void
}

export default function Sidebar({ tab, setTab }: Props) {
  return (
    <aside className="w-60 h-screen bg-slate-950 border-r border-slate-800/80 flex flex-col flex-shrink-0">
      {/* Brand */}
      <div className="h-14 flex items-center px-5 border-b border-slate-800/60">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 via-indigo-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-violet-500/20 mr-3">
          <Shield size={16} className="text-white" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="font-semibold text-sm text-slate-100 tracking-tight">CyberGuard</span>
          <span className="text-[10px] text-slate-500">AI Agent Platform</span>
        </div>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-5">
        {GROUPS.map((g) => (
          <div key={g.label}>
            <div className="px-3 mb-1.5 text-[10px] font-semibold text-slate-500 uppercase tracking-widest">
              {g.label}
            </div>
            <div className="space-y-0.5">
              {g.items.map(({ key, label, icon }) => {
                const active = tab === key
                return (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    className={[
                      'group w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all',
                      active
                        ? 'bg-violet-500/10 text-violet-300 ring-1 ring-violet-500/20'
                        : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-100',
                    ].join(' ')}
                  >
                    <span className={active ? 'text-violet-400' : 'text-slate-500 group-hover:text-slate-300'}>
                      {icon}
                    </span>
                    <span className="font-medium">{label}</span>
                    {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-violet-400" />}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-slate-800/60 text-[11px] text-slate-500">
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-violet-400 animate-pulse" />
          v1.0.0 · MVP
        </div>
      </div>
    </aside>
  )
}
