import { useState } from 'react'
import { Key, Lock, AlertTriangle } from 'lucide-react'

export default function Security() {
  const [settings, setSettings] = useState({
    encryption_enabled: true,
    audit_logging: true,
    rbac_enabled: true,
    api_key_rotation_days: 90,
    max_login_attempts: 5,
    session_timeout_minutes: 30,
    require_mfa: false,
  })

  const update = (key: string, value: any) => setSettings(s => ({ ...s, [key]: value }))

  const Toggle = ({ enabled, onToggle, color = 'var(--cyan)' }: { enabled: boolean; onToggle: () => void; color?: string }) => (
    <button onClick={onToggle}
      style={{
        position: 'relative', width: 44, height: 22,
        background: enabled ? color : 'var(--bg-elevated)',
        border: `1px solid ${enabled ? color : 'var(--border-bright)'}`,
        cursor: 'pointer', transition: 'all 0.2s',
      }}>
      <div style={{
        position: 'absolute', top: 2, left: 2,
        width: 16, height: 16,
        background: enabled ? color : 'var(--text-dim)',
        transition: 'all 0.2s',
        transform: enabled ? 'translateX(22px)' : 'translateX(0)',
      }} />
    </button>
  )

  const SettingRow = ({ icon, title, desc, enabled, onToggle, color = 'var(--cyan)' }: {
    icon: React.ReactNode; title: string; desc: string; enabled: boolean; onToggle: () => void; color?: string
  }) => (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: 20,
      background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
      marginBottom: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ width: 38, height: 38, border: '1px solid var(--border-bright)', background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', color }}>
          {icon}
        </div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.08em', marginBottom: 4 }}>{title}</div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)', letterSpacing: '0.05em' }}>{desc}</div>
        </div>
      </div>
      <Toggle enabled={enabled} onToggle={onToggle} color={color} />
    </div>
  )

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>ZERO TRUST ARCHITECTURE</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SECURITY CONFIG</h1>
        </div>
      </div>

      <div style={{ maxWidth: 680 }}>
        <SettingRow
          icon={<Key size={15} />}
          title="AES-256 ENCRYPTION"
          desc="Sensitive data encrypted at rest and in transit"
          enabled={settings.encryption_enabled}
          onToggle={() => update('encryption_enabled', !settings.encryption_enabled)}
          color="var(--cyan)"
        />

        <SettingRow
          icon={<Lock size={15} />}
          title="RBAC ACCESS CONTROL"
          desc="Role-based permission management"
          enabled={settings.rbac_enabled}
          onToggle={() => update('rbac_enabled', !settings.rbac_enabled)}
          color="var(--cyan)"
        />

        <SettingRow
          icon={<AlertTriangle size={15} />}
          title="AUDIT LOGGING"
          desc="Record all operations, SIEM export supported"
          enabled={settings.audit_logging}
          onToggle={() => update('audit_logging', !settings.audit_logging)}
          color="var(--amber)"
        />

        {/* Numeric settings */}
        <div style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
            THRESHOLD CONFIGURATION
          </div>
          {[
            { key: 'max_login_attempts', label: 'MAX LOGIN ATTEMPTS', min: 3, max: 20 },
            { key: 'session_timeout_minutes', label: 'SESSION TIMEOUT (MINUTES)', min: 5, max: 480 },
            { key: 'api_key_rotation_days', label: 'API KEY ROTATION (DAYS)', min: 7, max: 365 },
          ].map(({ key, label, min, max }) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.08em' }}>{label}</span>
              <input type="number" min={min} max={max}
                value={(settings as any)[key]}
                onChange={e => update(key, parseInt(e.target.value))}
                style={{
                  width: 80, height: 32, padding: '0 10px', textAlign: 'right',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)',
                }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
