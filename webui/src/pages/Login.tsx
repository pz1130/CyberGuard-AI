import { useState, useEffect } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api } from '../api/client'
import { useTranslation } from 'react-i18next'

export default function Login() {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(() => {
    const err = new URLSearchParams(window.location.search).get('error')
    return err ? (t(`login.${err}` as any) || t('login.ssoError')) : ''
  })
  const [loading, setLoading] = useState(false)
  const [ssoEnabled, setSsoEnabled] = useState(false)

  useEffect(() => {
    api.getSsoStatus().then((d: unknown) => setSsoEnabled(!!(d as { enabled?: boolean } | null)?.enabled)).catch(() => {})
    const err = new URLSearchParams(window.location.search).get('error')
    if (err) {
      window.history.replaceState(null, '', window.location.pathname)
    }
  }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    setLoading(true); setError('')
    try {
      const data = await api.login({ username, password }) as { access_token: string }
      localStorage.setItem('token', data.access_token)
      window.location.reload()
    } catch {
      setError(t('login.authFailed'))
    } finally { setLoading(false) }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'radial-gradient(circle at top, rgba(0, 212, 106, 0.06), transparent 30%), var(--bg-base)',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Grid BG */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'linear-gradient(rgba(0,212,106,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,106,0.03) 1px, transparent 1px)',
        backgroundSize: '44px 44px',
        pointerEvents: 'none',
      }} />

      {/* Glow orb */}
      <div style={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 600, height: 600, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0,212,106,0.05) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Card */}
      <div className="login-frame-animated login-border-glow" style={{
        position: 'relative', width: '100%', maxWidth: 400, margin: 16,
        animation: 'fade-in-up 0.4s ease',
        borderRadius: 'var(--radius-lg)',
      }}>
        <div className="login-card-shell" style={{
          background: 'var(--shell-backdrop)',
          boxShadow: 'var(--shadow-xl)',
          backdropFilter: 'blur(16px)',
          padding: '40px 36px',
          borderRadius: 'var(--radius-lg)',
          position: 'relative',
          zIndex: 1,
        }}>

        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <div style={{
            width: 40, height: 40,
            border: '1px solid var(--accent-border)',
            background: 'var(--accent-dim)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24,
          }}>
            <span style={{ color: 'var(--accent)' }}>⬡</span>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, letterSpacing: '0.06em', color: 'var(--shell-text-strong)' }}>
              CYBERGUARD
            </div>
            <div style={{ fontSize: 11, color: 'var(--shell-text-muted)', letterSpacing: '0.08em' }}>
              AI AGENT PLATFORM · AUTH GATE
            </div>
          </div>
        </div>

        <div style={{ height: 1, background: 'var(--shell-border-subtle)', marginBottom: 28 }} />

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div>
            <label style={{
              display: 'block', fontSize: 12, letterSpacing: '0.08em', color: 'var(--shell-text-muted)', marginBottom: 8,
            }}>
              {t('login.username').toUpperCase()}
            </label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="operator"
              style={{
                width: '100%', height: 40, padding: '0 12px',
                background: 'var(--shell-backdrop-strong)',
                border: '1px solid var(--shell-border)',
                color: 'var(--shell-text-strong)', fontSize: 15,
                letterSpacing: '0.05em',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
              onBlur={e => (e.target.style.borderColor = 'var(--border-bright)')}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 12, letterSpacing: '0.08em', color: 'var(--shell-text-muted)', marginBottom: 8 }}>
              {t('login.password').toUpperCase()}
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="••••••••"
              style={{
                width: '100%', height: 40, padding: '0 12px',
                background: 'var(--shell-backdrop-strong)',
                border: '1px solid var(--shell-border)',
                color: 'var(--shell-text-strong)', fontSize: 15,
                letterSpacing: '0.1em',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
              onBlur={e => (e.target.style.borderColor = 'var(--border-bright)')}
            />
          </div>

          {error && (
            <div style={{
              padding: '10px 12px',
              background: 'var(--red-dim)',
              border: '1px solid rgba(255,59,48,0.3)',
              fontSize: 12, letterSpacing: '0.1em', color: 'var(--red)',
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            style={{
              height: 40, width: '100%',
              background: loading ? 'var(--bg-elevated)' : 'var(--accent)',
              border: '1px solid var(--accent-border)',
              color: loading ? 'var(--text-muted)' : '#000',
              fontWeight: 700, fontSize: 14, letterSpacing: '0.08em',
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',               boxShadow: loading ? 'none' : '0 0 20px rgba(0,212,106,0.2)',
            }}
          >
            {loading ? t('login.authenticating').toUpperCase() : t('login.authenticate').toUpperCase()}
          </button>
        </form>

        {ssoEnabled && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' }}>
              <div style={{ flex: 1, height: 1, background: 'var(--shell-border-subtle)' }} />
              <span style={{ fontSize: 10, color: 'var(--shell-text-muted)', letterSpacing: '0.1em' }}>OR</span>
              <div style={{ flex: 1, height: 1, background: 'var(--shell-border-subtle)' }} />
            </div>
            <a
              href="/api/v1/auth/sso/login"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                height: 40, width: '100%', textDecoration: 'none',
                background: 'var(--shell-backdrop-strong)', border: '1px solid var(--shell-border)',
                color: 'var(--shell-text-strong)', fontWeight: 700, fontSize: 13,
                letterSpacing: '0.06em',               }}
            >
              <ShieldCheck size={16} color="var(--accent)" />
              SIGN IN WITH MICROSOFT
            </a>
          </>
        )}

        <div style={{ marginTop: 24, fontSize: 11, color: 'var(--shell-text-muted)', letterSpacing: '0.1em', textAlign: 'center' }}>
          SECURE · ENCRYPTED · ZERO-TRUST
        </div>
        </div>
      </div>
    </div>
  )
}
