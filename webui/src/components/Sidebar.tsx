import { MessageSquare, Cpu, Wrench, BookOpen, Radio, Clock, Puzzle, Settings, Shield, Coins, Database, FileText, UserCog } from 'lucide-react'

export type Tab = 'chat' | 'agents' | 'providers' | 'skills' | 'knowledge' | 'groupchat' | 'schedule' | 'mcp' | 'envvars' | 'security' | 'token' | 'backup' | 'audit' | 'users'

const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: 'chat', label: '聊天', icon: <MessageSquare size={18} /> },
  { key: 'agents', label: 'Sub-Agent 管理', icon: <Cpu size={18} /> },
  { key: 'providers', label: 'AI Provider 配置', icon: <Puzzle size={18} /> },
  { key: 'skills', label: 'Skill Pool', icon: <Wrench size={18} /> },
  { key: 'knowledge', label: '知识库', icon: <BookOpen size={18} /> },
  { key: 'groupchat', label: '群聊室', icon: <Radio size={18} /> },
  { key: 'schedule', label: '定时任务', icon: <Clock size={18} /> },
  { key: 'mcp', label: 'MCP', icon: <Puzzle size={18} /> },
  { key: 'envvars', label: '环境变量', icon: <Settings size={18} /> },
  { key: 'security', label: '安全', icon: <Shield size={18} /> },
  { key: 'token', label: 'Token 消耗', icon: <Coins size={18} /> },
  { key: 'backup', label: '备份', icon: <Database size={18} /> },
  { key: 'audit', label: '审计日志', icon: <FileText size={18} /> },
  { key: 'users', label: '用户管理', icon: <UserCog size={18} /> },
]

interface Props {
  tab: Tab
  setTab: (t: Tab) => void
  label?: (l: string) => void
  pages?: any
}

export default function Sidebar({ tab, setTab }: Props) {
  return (
    <aside className="w-60 h-screen bg-gray-900 flex flex-col flex-shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-gray-800">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center mr-3">
          <Shield size={18} className="text-white" />
        </div>
        <span className="font-bold text-base text-white tracking-wide">CyberGuard</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2">
        {TABS.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`w-full flex items-center px-4 py-2.5 text-sm gap-3 transition-colors ${
              tab === key
                ? 'bg-emerald-500/10 text-emerald-400 border-r-2 border-emerald-400'
                : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}
          >
            {icon}
            <span>{label}</span>
          </button>
        ))}
      </nav>

      {/* Version */}
      <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-500">
        v1.0.0 · M1 MVP
      </div>
    </aside>
  )
}
