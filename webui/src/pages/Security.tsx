import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Key, Lock, AlertTriangle, Save, Loader2, Shield } from 'lucide-react'
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

function EnforcedRow({ icon, title, desc }: {
  icon: ReactNode; title: string; desc: string
}) {
  const { t } = useTranslation()
  return (
    <div style={{
      display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      padding: '14px 16px', marginBottom: 10, gap: 14, flexWrap: 'wrap',
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        <div style={{
          width: 36, height: 36,
          border: '1px solid var(--accent-border)',
          background: 'var(--accent-dim)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--accent)', borderRadius: 0, flexShrink: 0,
        }}>
          {icon}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>{title}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{desc}</div>
        </div>
      </div>
      <span style={{
        fontSize: 10, letterSpacing: '0.08em', fontWeight: 700,
        color: 'var(--accent)', border: '1px solid var(--accent-border)',
        background: 'var(--accent-dim)', padding: '3px 8px',
        borderRadius: 0, whiteSpace: 'nowrap', flexShrink: 0,
        fontFamily: 'var(--font-mono)',
      }}>
        {t('security.enforced').toUpperCase()}
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 40, color: 'var(--text-muted)', fontSize: 13, fontFamily: 'var(--font-mono)' }}>
        <Loader2 size={16} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
        LOADING SECURITY CONTROLS...
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
              <span style={{ fontSize: 12, letterSpacing: '0.08em', color: notice.ok ? 'var(--accent)' : 'var(--red)', fontFamily: 'var(--font-mono)' }}>
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

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 20, alignItems: 'start' }}>
        {/* Left Column: Platform Security Invariants */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{
            padding: '14px 18px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--bg-surface)',
          }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
              {t('security.invariants', 'PLATFORM SECURITY INVARIANTS').toUpperCase()}
            </span>
            <span className="badge badge-success" style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>
              3 ENFORCED
            </span>
          </div>
          <div style={{ padding: 18 }}>
            <EnforcedRow icon={<Key size={15} />}
              title={t('security.encryption')} desc={t('security.encryptionDesc')} />
            <EnforcedRow icon={<Lock size={15} />}
              title={t('security.rbac')} desc={t('security.rbacDesc')} />
            <EnforcedRow icon={<AlertTriangle size={15} />}
              title={t('security.audit')} desc={t('security.auditDesc')} />
            <div style={{
              fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6,
              margin: '8px 2px 4px', padding: '10px 14px', background: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
            }}>
              {t('security.enforcedNote')}
            </div>
          </div>
        </div>

        {/* Right Column: Thresholds & Session Configuration */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{
              padding: '14px 18px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'var(--bg-surface)',
            }}>
              <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
                {t('security.thresholds').toUpperCase()}
              </span>
              <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                CONFIGURABLE
              </span>
            </div>
            <div style={{ padding: '18px 20px' }}>
              {([
                { key: 'max_login_attempts', label: t('security.maxLoginAttempts'), min: 3, max: 20, unit: 'ATTEMPTS' },
                { key: 'session_timeout_minutes', label: t('security.sessionTimeout'), min: 5, max: 480, unit: 'MINUTES' },
              ] as const).map(({ key, label, min, max, unit }) => (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 0',
                  borderBottom: '1px solid var(--border)',
                }}>
                  <div>
                    <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
                      RANGE: {min} - {max} {unit}
                    </div>
                  </div>
                  <input
                    type="number" min={min} max={max}
                    value={settings[key]}
                    onChange={e => update(key, Math.min(max, Math.max(min, parseInt(e.target.value) || min)))}
                    className="form-input"
                    style={{
                      width: 88, height: 32, padding: '0 8px', textAlign: 'right', fontFamily: 'var(--font-mono)',
                    }}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Security Posture Summary Card */}
          <div className="card" style={{ padding: '16px 18px', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <Shield size={16} style={{ color: 'var(--accent)' }} />
              <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-primary)' }}>
                SOC DEFENSE IN DEPTH
              </span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
              All login anomalies trigger automatic session throttling and tamper-evident audit logging with cryptographic proof chains.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
