import { Moon, Sun, Globe } from 'lucide-react'

interface Props {
  dark: boolean
  toggleDark: () => void
  lang: 'zh' | 'en'
  toggleLang: () => void
}

export default function Header({ dark, toggleDark, lang, toggleLang }: Props) {
  return (
    <header className="h-14 bg-gradient-to-r from-emerald-500 to-teal-500 flex items-center justify-between px-6 flex-shrink-0 shadow-lg">
      <h1 className="text-white font-semibold text-base tracking-wide">CyberGuard AI Agent Platform</h1>
      <div className="flex items-center gap-2">
        <button
          onClick={toggleLang}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/20 hover:bg-white/30 text-white text-sm transition-colors"
        >
          <Globe size={14} />
          {lang === 'zh' ? '中文' : 'EN'}
        </button>
        <button
          onClick={toggleDark}
          className="p-2 rounded-lg bg-white/20 hover:bg-white/30 text-white transition-colors"
        >
          {dark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  )
}
