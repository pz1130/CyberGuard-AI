/**
 * CyberGuard Header
 * Taste-skill: 56px single line, sans body, no decorative chrome.
 * - Brand mark (lucide Shield) + product name, no version badge.
 * - Centered search trigger, no animated glyphs.
 * - Theme / Lang / User as 32px icon buttons; status dot is semantic only.
 */
import { Sun, Moon, Globe, Search, Bell, ChevronDown, LogOut, Shield, Terminal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import ChangePasswordDialog from './ChangePasswordDialog'

interface HeaderProps {
  dark: boolean
  toggleDark: () => void
  toggleLang: () => void
  onSearchOpen: () => void
}

type SysStatus = 'online' | 'degraded' | 'offline'

const STATUS_COLOR: Record<SysStatus, string> = {
  online: 'var(--green)',
  degraded: 'var(--amber)',
  offline: 'var(--red)',
}

export default function HeaderNew({
  dark,
  toggleDark,
  toggleLang,
  onSearchOpen,
}: HeaderProps) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('Admin')
  const [role, setRole] = useState('Administrator')
  const [menuOpen, setMenuOpen] = useState(false)
  const [showChangePassword, setShowChangePassword] = useState(false)
  const [sysStatus, setSysStatus] = useState<SysStatus>('online')
  const [branding, setBranding] = useState<{ branding_logo?: string | null; branding_company_name?: string | null }>({})

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) return
    api
      .getAuthMe()
      .then((d: unknown) => {
        const data = d as { username?: string; role?: string } | null
        if (data) {
          if (data.username) setUsername(String(data.username))
          if (data.role) setRole(String(data.role))
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    const check = () => {
      api.healthStatus().then((s) => {
        if (!cancelled) setSysStatus(s as SysStatus)
      })
    }
    check()
    const id = setInterval(check, 30_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  useEffect(() => {
    const load = () => {
      api.getBranding().then((d: unknown) => {
        if (d && typeof d === 'object') setBranding(d as { branding_logo?: string | null; branding_company_name?: string | null })
      }).catch(() => {})
    }
    load()
    const onBranding = () => load()
    window.addEventListener('branding-updated', onBranding)
    return () => window.removeEventListener('branding-updated', onBranding)
  }, [])

  const logout = () => {
    localStorage.removeItem('token')
    window.location.reload()
  }

  const iconBtn = (extra?: React.CSSProperties): React.CSSProperties => ({
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 32,
    height: 32,
    border: '1px solid var(--border)',
    borderRadius: 0,
    background: 'transparent',
    color: 'var(--text-muted)',
    cursor: 'pointer',
    transition:
      'background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast)',
    ...extra,
  })

  return (
    <>
    <header
      className="header-shell"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: 'var(--header-height)',
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '0 16px',
        zIndex: 50,
        fontFamily: 'var(--font-sans)',
      }}
    >
      {/* Brand */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          flexShrink: 0,
        }}
      >
        {branding.branding_logo ? (
          <img
            src={branding.branding_logo}
            alt="logo"
            style={{
              width: 28,
              height: 28,
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--accent-border)',
              objectFit: 'contain',
              background: '#fff',
            }}
          />
        ) : (
          <div
            aria-hidden
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 28,
              height: 28,
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent-dim)',
              border: '1px solid var(--accent-border)',
              color: 'var(--accent)',
            }}
          >
            <Shield size={15} strokeWidth={2.25} />
          </div>
        )}
        <div
          style={{
            fontSize: 15,
            fontWeight: 600,
            color: 'var(--text-primary)',
            letterSpacing: '-0.01em',
          }}
        >
          {branding.branding_company_name || 'CyberGuard'}
        </div>

        {/* Terminal status badge with green blinking animation */}
        <div
          aria-label={`System ${sysStatus}`}
          title={`System status: ${sysStatus}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginLeft: 8,
            padding: '4px 8px',
            color: STATUS_COLOR[sysStatus],
            background: 'var(--bg-elevated)',
            border: `1px solid ${sysStatus === 'online' ? 'var(--accent-border)' : 'var(--border)'}`,
            borderRadius: 0,
            boxShadow: sysStatus === 'online' ? 'var(--accent-glow)' : undefined,
          }}
        >
          <span className={sysStatus === 'online' ? 'terminal-icon-blink' : undefined} style={{ display: 'inline-flex', alignItems: 'center' }}>
            <Terminal size={14} strokeWidth={2.25} />
          </span>
        </div>
      </div>

      {/* Search trigger (centered) */}
      <div className="header-search" style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
        <button
          onClick={onSearchOpen}
          aria-label="Open search"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            width: '100%',
            maxWidth: 480,
            height: 32,
            padding: '0 10px',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            borderRadius: 0,
            color: 'var(--text-dim)',
            fontSize: 13,
            cursor: 'pointer',
            textAlign: 'left',
            transition: 'border-color var(--transition-fast)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--accent-border)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border)'
          }}
        >
          <Search size={14} />
          <span style={{ flex: 1 }}>Search agents, skills, tools...</span>
          <kbd
            className="font-mono"
            style={{
              fontSize: 10,
              padding: '2px 6px',
              border: '1px solid var(--border)',
              borderRadius: 0,
              color: 'var(--text-muted)',
              background: 'var(--bg-surface)',
            }}
          >
            Ctrl+K
          </kbd>
        </button>
      </div>

      {/* Right cluster */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          flexShrink: 0,
        }}
      >
        <button
          onClick={toggleLang}
          title="Switch language"
          aria-label="Switch language"
          style={iconBtn()}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--text-primary)'
            e.currentTarget.style.borderColor = 'var(--border-bright)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.borderColor = 'var(--border)'
          }}
        >
          <Globe size={15} />
        </button>

        <button
          onClick={toggleDark}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle theme"
          style={iconBtn()}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--text-primary)'
            e.currentTarget.style.borderColor = 'var(--border-bright)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.borderColor = 'var(--border)'
          }}
        >
          {dark ? <Moon size={15} /> : <Sun size={15} />}
        </button>

        <button
          title="Notifications"
          aria-label="Notifications"
          style={iconBtn()}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--text-primary)'
            e.currentTarget.style.borderColor = 'var(--border-bright)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.borderColor = 'var(--border)'
          }}
        >
          <Bell size={15} />
        </button>

        {/* User menu */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              height: 32,
              padding: '0 8px 0 4px',
              background: 'var(--bg-elevated)',
              border: menuOpen
                ? '1px solid var(--accent-border)'
                : '1px solid var(--border)',
              borderRadius: 0,
              color: 'var(--text-primary)',
              cursor: 'pointer',
              transition: 'border-color var(--transition-fast)',
            }}
          >
            <span
              aria-hidden
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 24,
                height: 24,
                borderRadius: 'var(--radius-full)',
                background: 'var(--accent-dim)',
                color: 'var(--accent)',
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {username.charAt(0).toUpperCase()}
            </span>
            <span style={{ fontSize: 13, fontWeight: 500 }}>{username}</span>
            <ChevronDown
              size={13}
              style={{ color: 'var(--text-dim)' }}
            />
          </button>

          {menuOpen && (
            <>
              <div
                style={{ position: 'fixed', inset: 0, zIndex: 10 }}
                onClick={() => setMenuOpen(false)}
              />
              <div
                role="menu"
                style={{
                  position: 'absolute',
                  right: 0,
                  top: 'calc(100% + 6px)',
                  minWidth: 200,
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: '0 8px 24px rgba(0, 0, 0, 0.35)',
                  zIndex: 20,
                  overflow: 'hidden',
                  animation: 'fade-in 0.15s ease',
                }}
              >
                <div
                  style={{
                    padding: '10px 12px',
                    borderBottom: '1px solid var(--border)',
                  }}
                >
                  <div
                    style={{
                      fontSize: 11,
                      color: 'var(--text-dim)',
                      marginBottom: 2,
                    }}
                  >
                    {t('header.signedInAs')}
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      color: 'var(--text-primary)',
                    }}
                  >
                    {username}
                  </div>
                  <div
                    style={{ fontSize: 11, color: 'var(--text-muted)' }}
                  >
                    {role}
                  </div>
                </div>
                <button
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); setShowChangePassword(true) }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    padding: '8px 12px',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-muted)',
                    fontSize: 13,
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  {t('header.changePassword')}
                </button>
                <button
                  role="menuitem"
                  onClick={logout}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    padding: '8px 12px',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--red)',
                    fontSize: 13,
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'var(--red-dim)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'transparent'
                  }}
                >
                  <LogOut size={14} />
                  <span>{t('header.signOut')}</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
    {showChangePassword && (
      <ChangePasswordDialog onClose={() => setShowChangePassword(false)} />
    )}
    </>
  )
}
