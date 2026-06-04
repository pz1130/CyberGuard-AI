import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Key, Lock, AlertTriangle, Save, Loader2 } from 'lucide-react'
import { api } from '../api/client'

interface SecuritySettings {
  encryption_enabled: boolean
  rbac_enabled: boolean
  audit_logging: boolean
  max_login_attempts: number
  session_timeout_minutes: number
  api_key_rotation_days: number
}

const DEFAULT: SecuritySettings = {
  encryption_enabled: true,
  rbac_enabled: true,
  audit_logging: true,
  max_login_attempts: 5,
  session_timeout_minutes: 30,
  api_key_rotation_days: 90,
}

export default function Security() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<SecuritySettings>(DEFAULT)
  const [saved, setSaved] = useState<SecuritySettings>(DEFAULT)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    api.getSecuritySettings()
      .then(d => {
        const s = d as SecuritySettings
        setSettings(s)
        setSaved(s)
      })
      .catch(() => setNotice({ ok: false, msg: 'FAILED TO LOAD SETTINGS' }))
      .finally(() => setLoading(false))
  }, [])

  const dirty = JSON.stringify(settings) !== JSON.stringify(saved)

  const update = <K extends keyof SecuritySettings>(key: K, value: SecuritySettings[K]) =>
    setSettings(s => ({ ...s, [key]: value }))

  const save = async () => {
    setSaving(true)
    setNotice(null)
    try {
      const d = await api.updateSecuritySettings(settings as unknown as Record<string, unknown>) as SecuritySettings
      setSaved(d)
      setSettings(d)
      setNotice({ ok: true, msg: 'SETTINGS SAVED' })
      setTimeout(() => setNotice(null), 3000)
    } catch (e: any) {
      setNotice({ ok: false, msg: e?.message || 'SAVE FAILED' })
    } finally {
      setSaving(false)
    }
  }

  const Toggle = ({ enabled, onToggle, color = 'var(--cyan)' }: {
    enabled: boolean; onToggle: () => void; color?: string
  }) => (
    <button onClick={onToggle} style={{
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
    icon: React.ReactNode; title: string; desc: string
    enabled: boolean; onToggle: () => void; color?: string
  }) => (
    <div className="item-card" style={{
      display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      padding: 20,
      marginBottom: 12,
      background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
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

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 40, color: 'var(--text-muted)', fontSize: 13 }}>
        <Loader2 size={16} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
        LOADING...
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>ZERO TRUST ARCHITECTURE</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{t('security.title').toUpperCase()}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {notice && (
            <span style={{ fontSize: 12, letterSpacing: '0.1em', color: notice.ok ? 'var(--accent)' : 'var(--red)' }}>
              {notice.msg}
            </span>
          )}
          <button
            onClick={save}
            disabled={!dirty || saving}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '0 16px', height: 34,
              background: dirty ? 'var(--accent)' : 'var(--bg-elevated)',
              border: `1px solid ${dirty ? 'var(--accent-border)' : 'var(--border-bright)'}`,
              color: dirty ? '#000' : 'var(--text-dim)',
              fontSize: 12, letterSpacing: '0.1em', fontWeight: 700,
              cursor: dirty ? 'pointer' : 'not-allowed',
                            transition: 'all 0.15s',
            }}
          >
            {saving
              ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
              : <Save size={12} />}
            SAVE
          </button>
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

        <div className="item-card" style={{ padding: 20, marginBottom: 12, display: 'block', background: 'var(--bg-surface)', border: '1px solid var(--border-bright)' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
            THRESHOLD CONFIGURATION
          </div>
          {([
            { key: 'max_login_attempts', label: 'MAX LOGIN ATTEMPTS', min: 3, max: 20 },
            { key: 'session_timeout_minutes', label: 'SESSION TIMEOUT (MINUTES)', min: 5, max: 480 },
            { key: 'api_key_rotation_days', label: 'API KEY ROTATION (DAYS)', min: 7, max: 365 },
          ] as const).map(({ key, label, min, max }) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', letterSpacing: '0.08em' }}>{label}</span>
              <input
                type="number" min={min} max={max}
                value={settings[key]}
                onChange={e => update(key, parseInt(e.target.value) || min)}
                style={{
                  width: 80, height: 32, padding: '0 10px', textAlign: 'right',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 13,                 }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
