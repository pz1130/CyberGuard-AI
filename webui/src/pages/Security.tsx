import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Key, Lock, AlertTriangle, Save, Loader2 } from 'lucide-react'
import { api } from '../api/client'
import PageHeader from '../components/PageHeader'
import { errorMessage } from '../lib/errorMessage'

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

function Toggle({ enabled, onToggle, color = 'var(--cyan)' }: {
  enabled: boolean; onToggle: () => void; color?: string
}) {
  return (
    <button onClick={onToggle} style={{
      position: 'relative', width: 44, height: 22,
      background: enabled ? color : 'var(--bg-elevated)',
      border: `1px solid ${enabled ? color : 'var(--border-bright)'}`,
      cursor: 'pointer', transition: 'all 0.2s',
      borderRadius: 'var(--radius-full)',
    }}>
      <div style={{
        position: 'absolute', top: 2, left: 2,
        width: 16, height: 16,
        background: enabled ? '#0b1018' : 'var(--text-dim)',
        borderRadius: 'var(--radius-full)',
        transition: 'all 0.2s',
        transform: enabled ? 'translateX(22px)' : 'translateX(0)',
      }} />
    </button>
  )
}

function SettingRow({ icon, title, desc, enabled, onToggle, color = 'var(--cyan)' }: {
  icon: ReactNode; title: string; desc: string
  enabled: boolean; onToggle: () => void; color?: string
}) {
  return (
    <div className="item-card" style={{
      display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      padding: '16px 20px',
      marginBottom: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          width: 36, height: 36, border: '1px solid var(--border)',
          background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          color, borderRadius: 'var(--radius-md)', flexShrink: 0,
        }}>
          {icon}
        </div>
        <div>
          <div className="item-card-title">{title}</div>
          <div className="item-card-desc">{desc}</div>
        </div>
      </div>
      <Toggle enabled={enabled} onToggle={onToggle} color={color} />
    </div>
  )
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
      .catch(() => setNotice({ ok: false, msg: t('security.loadFailed') }))
      .finally(() => setLoading(false))
  }, [t])

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
      setNotice({ ok: true, msg: t('security.saved') })
      setTimeout(() => setNotice(null), 3000)
    } catch (e: unknown) {
      setNotice({ ok: false, msg: errorMessage(e) || t('security.saveFailed') })
    } finally {
      setSaving(false)
    }
  }

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
      <PageHeader
        eyebrow={t('security.eyebrow').toUpperCase()}
        title={t('security.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {notice && (
              <span style={{ fontSize: 12, letterSpacing: '0.08em', color: notice.ok ? 'var(--accent)' : 'var(--red)' }}>
                {notice.msg}
              </span>
            )}
            <button
              onClick={save}
              disabled={!dirty || saving}
              className="btn btn-primary"
              style={{
                display: 'flex', alignItems: 'center', gap: 8, height: 36,
                opacity: (!dirty || saving) ? 0.5 : 1,
                cursor: (!dirty || saving) ? 'not-allowed' : 'pointer',
              }}
            >
              {saving
                ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                : <Save size={13} />}
              {saving ? t('security.saving').toUpperCase() : t('security.save').toUpperCase()}
            </button>
          </div>
        }
      />

      <div style={{ maxWidth: 680 }}>
        <SettingRow
          icon={<Key size={15} />}
          title={t('security.encryption')}
          desc={t('security.encryptionDesc')}
          enabled={settings.encryption_enabled}
          onToggle={() => update('encryption_enabled', !settings.encryption_enabled)}
          color="var(--cyan)"
        />
        <SettingRow
          icon={<Lock size={15} />}
          title={t('security.rbac')}
          desc={t('security.rbacDesc')}
          enabled={settings.rbac_enabled}
          onToggle={() => update('rbac_enabled', !settings.rbac_enabled)}
          color="var(--cyan)"
        />
        <SettingRow
          icon={<AlertTriangle size={15} />}
          title={t('security.audit')}
          desc={t('security.auditDesc')}
          enabled={settings.audit_logging}
          onToggle={() => update('audit_logging', !settings.audit_logging)}
          color="var(--amber)"
        />

        <div className="item-card" style={{ padding: 20, marginBottom: 12, display: 'block' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.06em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
            {t('security.thresholds').toUpperCase()}
          </div>
          {([
            { key: 'max_login_attempts', label: t('security.maxLoginAttempts'), min: 3, max: 20 },
            { key: 'session_timeout_minutes', label: t('security.sessionTimeout'), min: 5, max: 480 },
            { key: 'api_key_rotation_days', label: t('security.keyRotation'), min: 7, max: 365 },
          ] as const).map(({ key, label, min, max }) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{label}</span>
              <input
                type="number" min={min} max={max}
                value={settings[key]}
                onChange={e => update(key, parseInt(e.target.value) || min)}
                className="form-input font-mono"
                style={{
                  width: 80, height: 32, padding: '0 8px', textAlign: 'right',
                }}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
