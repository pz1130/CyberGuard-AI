import { useState, useEffect } from 'react'
import { LogOut, Search } from 'lucide-react'

interface Props {
  dark: boolean
  toggleDark: () => void
  toggleLang: () => void
}

export default function Header({ dark, toggleDark, toggleLang }: Props) {
  const [username, setUsername] = useState('ADMIN')
  const [role, setRole] = useState('OPERATOR')
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) return
    fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setUsername((d.username || 'ADMIN').toUpperCase())
          setRole((d.role || 'OPERATOR').toUpperCase())
        }
      })
      .catch(() => {})
  }, [])

  const logout = () => {
    localStorage.removeItem('token')
    window.location.reload()
  }

  return (
    <header
      style={{
        position: 'fixed',
        top: 0, left: 0, right: 0,
        height: 'var(--header-height)',
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border-bright)',
        boxShadow: '0 1px 0 rgba(0,255,65,0.03), 0 4px 20px rgba(0,0,0,0.5)',
        zIndex: 50,
        display: 'flex', alignItems: 'center',
        padding: '0 20px',
        gap: 16,
        fontFamily: 'var(--font-mono)',
      }}
    >
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, marginRight: 8 }}>
        <div style={{
          width: 32, height: 32,
          border: '1px solid var(--accent-border)',
          background: 'var(--accent-dim)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-mono)', fontSize: 20,
        }}>
          <span style={{ color: 'var(--accent)' }}>⬡</span>
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 17, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>
            CYBERGUARD
          </div>
          <div style={{ fontSize: 11, color: 'var(--accent)', letterSpacing: '0.2em', opacity: 0.7 }}>
            AI AGENT PLATFORM v1.0
          </div>
        </div>
      </div>

      {/* Separator */}
      <div style={{ width: 1, height: 24, background: 'var(--border-bright)', flexShrink: 0 }} />

      {/* Search */}
      <div style={{ flex: 1, maxWidth: 480, position: 'relative' }}>
        <Search size={12} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
        <input
          type="text"
          id="global-search"
          placeholder="SEARCH AGENTS / SKILLS / TOOLS / PROVIDERS..."
          style={{
            width: '100%', height: 34,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-bright)',
            paddingLeft: 36, paddingRight: 12,
            fontSize: 14, letterSpacing: '0.05em',
            color: 'var(--text-primary)',
          }}
        />
        <span style={{
          position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
          fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em', pointerEvents: 'none'
        }}>
          CTRL+K
        </span>
      </div>

      {/* Right side */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', flexShrink: 0 }}>
        {/* Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '0 12px', height: 28, border: '1px solid var(--border-bright)' }}>
          <div className="status-dot online" style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: 12, letterSpacing: '0.15em', color: 'var(--accent)', opacity: 0.8 }}>
            SYS ONLINE
          </span>
        </div>

        {/* Lang */}
        <button
          onClick={toggleLang}
          style={{
            height: 28, padding: '0 10px',
            background: 'transparent',
            border: '1px solid var(--border-bright)',
            color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { (e.target as HTMLElement).style.borderColor = 'var(--accent-border)'; (e.target as HTMLElement).style.color = 'var(--accent)'; }}
          onMouseLeave={e => { (e.target as HTMLElement).style.borderColor = 'var(--border-bright)'; (e.target as HTMLElement).style.color = 'var(--text-muted)'; }}
        >
          ZH/EN
        </button>

        {/* Dark/Light toggle */}
        <button
          onClick={toggleDark}
          title={dark ? 'SWITCH TO LIGHT MODE' : 'SWITCH TO DARK MODE'}
          style={{
            height: 28, padding: '0 10px',
            background: 'transparent',
            border: '1px solid var(--border-bright)',
            color: dark ? 'var(--amber)' : 'var(--cyan)',
            fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { (e.target as HTMLElement).style.borderColor = dark ? 'var(--amber)' : 'var(--cyan)'; }}
          onMouseLeave={e => { (e.target as HTMLElement).style.borderColor = 'var(--border-bright)'; }}
        >
          {dark ? '◆ DARK' : '◇ LIGHT'}
        </button>

        {/* User */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setMenuOpen(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '0 10px', height: 28,
              background: 'var(--bg-elevated)',
              border: menuOpen ? '1px solid var(--accent-border)' : '1px solid var(--border-bright)',
              color: 'var(--text-primary)', cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            <div style={{
              width: 20, height: 20,
              background: 'var(--accent-dim)',
              border: '1px solid var(--accent-border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700, color: 'var(--accent)',
            }}>
              {username[0]}
            </div>
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.1em' }}>{username}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>{role}</div>
            </div>
            <div
              className="blink"
              style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', marginLeft: 4 }}
            />
          </button>

          {menuOpen && (
            <>
              <div
                style={{ position: 'fixed', inset: 0, zIndex: 10 }}
                onClick={() => setMenuOpen(false)}
              />
              <div style={{
                position: 'absolute', right: 0, top: '100%', marginTop: 4,
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-bright)',
                minWidth: 160,
                zIndex: 20,
                animation: 'fade-in-up 0.15s ease',
              }}>
                <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>SIGNED IN AS</div>
                  <div style={{ fontSize: 14, color: 'var(--accent)', marginTop: 2, letterSpacing: '0.1em' }}>{username}</div>
                </div>
                <button
                  onClick={logout}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    width: '100%', padding: '10px 12px',
                    background: 'none', border: 'none',
                    color: 'var(--red)', fontSize: 13, letterSpacing: '0.1em', cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--red-dim)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                >
                  <LogOut size={12} />
                  <span>LOGOUT</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
