import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Key, Lock, AlertTriangle, Save, Loader2 } from 'lucide-react'
import { api } from '../api/client'
import PageHeader from '../components/PageHeader'
import { errorMessage } from '../lib/errorMessage'

interface SecuritySettings {
  max_login_attempts: number
  session_timeout_minutes: number
}

const DEFAULT: SecuritySettings = {
  max_login_attempts: 5,
  session_timeout_minutes: 30,
}

/**
 * A control the platform always enforces.
 *
 * These were toggles. Nothing ever read the values, and wiring them up would
 * have meant shipping switches for "store credentials in plaintext", "skip
 * permission checks" and "stop writing the audit trail". They are invariants,
 * so the page states them instead of offering them.
 */
function EnforcedRow({ icon, title, desc }: {
  icon: ReactNode; title: string; desc: string
}) {
  const { t } = useTranslation()
  return (
    <div className="item-card" style={{
      display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      padding: '16px 20px', marginBottom: 12, gap: 12, flexWrap: 'wrap',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
        <div style={{
          width: 38, height: 38,
          border: '1px solid var(--accent-border)',
          background: 'var(--accent-dim)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--accent)', borderRadius: 'var(--radius-md)', flexShrink: 0,
        }}>
          {icon}
        </div>
        <div style={{ minWidth: 0 }}>
          <div className="item-card-title">{title}</div>
          <div className="item-card-desc">{desc}</div>
        </div>
      </div>
      <span style={{
        fontSize: 11, letterSpacing: '0.1em', fontWeight: 700,
        color: 'var(--accent)', border: '1px solid var(--accent-border)',
        background: 'var(--accent-dim)', padding: '4px 10px',
        borderRadius: 'var(--radius-sm)', whiteSpace: 'nowrap', flexShrink: 0,
      }}>
        {t('security.enforced')}
      </span>
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
              className={`btn ${dirty ? 'btn-primary' : 'btn-secondary'}`}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, height: 36,
                opacity: (!dirty || saving) ? 0.6 : 1,
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
        <EnforcedRow icon={<Key size={15} />}
          title={t('security.encryption')} desc={t('security.encryptionDesc')} />
        <EnforcedRow icon={<Lock size={15} />}
          title={t('security.rbac')} desc={t('security.rbacDesc')} />
        <EnforcedRow icon={<AlertTriangle size={15} />}
          title={t('security.audit')} desc={t('security.auditDesc')} />
        <div style={{
          fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6,
          margin: '4px 2px 18px', fontFamily: 'var(--font-sans)',
        }}>
          {t('security.enforcedNote')}
        </div>

        <div className="item-card" style={{ padding: 20, marginBottom: 12, display: 'block' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.06em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
            {t('security.thresholds').toUpperCase()}
          </div>
          {([
            { key: 'max_login_attempts', label: t('security.maxLoginAttempts'), min: 3, max: 20 },
            { key: 'session_timeout_minutes', label: t('security.sessionTimeout'), min: 5, max: 480 },
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
