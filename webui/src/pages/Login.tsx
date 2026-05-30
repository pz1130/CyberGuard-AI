import { useState } from 'react'
import { api } from '../api/client'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    setLoading(true); setError('')
    try {
      const data = await api.login({ username, password }) as any
      localStorage.setItem('token', data.access_token)
      window.location.reload()
    } catch {
      setError('AUTHENTICATION FAILED — CHECK CREDENTIALS')
    } finally { setLoading(false) }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg-base)',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Grid BG */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'linear-gradient(rgba(0,255,65,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,255,65,0.03) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
        pointerEvents: 'none',
      }} />

      {/* Glow orb */}
      <div style={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 600, height: 600, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0,255,65,0.04) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Card */}
      <div style={{
        position: 'relative', width: '100%', maxWidth: 400, margin: 16,
        border: '1px solid var(--border-bright)',
        background: 'var(--bg-surface)',
        padding: '40px 36px',
        animation: 'fade-in-up 0.4s ease',
      }}>
        {/* Top border accent */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 2,
          background: 'linear-gradient(90deg, transparent, var(--accent), transparent)',
        }} />

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
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, letterSpacing: '0.06em' }}>
              CYBERGUARD
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
              AI AGENT PLATFORM · AUTH GATE
            </div>
          </div>
        </div>

        <div style={{ height: 1, background: 'var(--border)', marginBottom: 28 }} />

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div>
            <label style={{
              display: 'block', fontSize: 12, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8,
            }}>
              USERNAME
            </label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="operator"
              style={{
                width: '100%', height: 40, padding: '0 12px',
                background: 'var(--bg-base)',
                border: '1px solid var(--border-bright)',
                color: 'var(--text-primary)', fontSize: 15,
                fontFamily: 'var(--font-mono)', letterSpacing: '0.05em',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
              onBlur={e => (e.target.style.borderColor = 'var(--border-bright)')}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 12, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8 }}>
              PASSWORD
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="••••••••"
              style={{
                width: '100%', height: 40, padding: '0 12px',
                background: 'var(--bg-base)',
                border: '1px solid var(--border-bright)',
                color: 'var(--text-primary)', fontSize: 15,
                fontFamily: 'var(--font-mono)', letterSpacing: '0.1em',
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
              transition: 'all 0.15s', fontFamily: 'var(--font-mono)',
              boxShadow: loading ? 'none' : '0 0 20px rgba(0,255,65,0.2)',
            }}
          >
            {loading ? 'AUTHENTICATING...' : 'AUTHENTICATE'}
          </button>
        </form>

        <div style={{ marginTop: 24, fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em', textAlign: 'center' }}>
          SECURE · ENCRYPTED · ZERO-TRUST
        </div>
      </div>
    </div>
  )
}
