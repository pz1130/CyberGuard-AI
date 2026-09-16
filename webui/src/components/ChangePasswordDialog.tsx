import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '../api/client'
import { errorMessage } from '../lib/errorMessage'

/**
 * Self-service password change.
 *
 * Until this existed the only way to a new password was asking an admin to set
 * one, which means the admin knows it and a user whose password leaks cannot
 * act without them. The current password is required by the server; asking for
 * it here too keeps the error local instead of a round trip.
 */
export default function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  const tooShort = next.length > 0 && next.length < 8
  const mismatch = confirm.length > 0 && next !== confirm
  const canSubmit = !!current && next.length >= 8 && next === confirm && !busy

  const submit = async () => {
    setError(''); setBusy(true)
    try {
      const res = await api.changePassword({
        old_password: current, new_password: next,
      }) as { other_sessions_ended?: number }
      const ended = res?.other_sessions_ended ?? 0
      setDone(ended > 0
        ? t('header.passwordChangedSessions', { count: ended })
        : t('header.passwordChanged'))
      setCurrent(''); setNext(''); setConfirm('')
    } catch (e: unknown) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div role="dialog" aria-label={t('header.changePassword')} style={{
      position: 'fixed', inset: 0, zIndex: 1200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', padding: 16,
    }}>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
        padding: 24, width: 380, maxWidth: '100%',
        borderRadius: 'var(--radius-md)',
      }}>
        <div style={{
          fontSize: 14, fontWeight: 600, letterSpacing: '0.08em',
          color: 'var(--text-primary)', marginBottom: 18,
        }}>
          {t('header.changePassword').toUpperCase()}
        </div>

        {done ? (
          <div style={{ fontSize: 13, color: 'var(--green)', marginBottom: 18, lineHeight: 1.6 }}>
            {done}
          </div>
        ) : (
          <>
            <Field id="cp-current" label={t('header.currentPassword')}
              value={current} onChange={setCurrent} />
            <Field id="cp-new" label={t('header.newPassword')}
              value={next} onChange={setNext}
              hint={tooShort ? t('header.passwordTooShort') : ''} />
            <Field id="cp-confirm" label={t('header.confirmPassword')}
              value={confirm} onChange={setConfirm}
              hint={mismatch ? t('header.passwordMismatch') : ''} />
          </>
        )}

        {error && (
          <div role="alert" style={{ fontSize: 12, color: 'var(--red)', marginBottom: 12 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 8 }}>
          <button onClick={onClose} className="btn btn-sm">
            {done ? t('header.close') : t('header.cancel')}
          </button>
          {!done && (
            <button onClick={submit} disabled={!canSubmit} className="btn btn-primary btn-sm">
              {busy ? t('header.saving') : t('header.changePassword')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function Field({ id, label, value, onChange, hint }: {
  id: string; label: string; value: string
  onChange: (v: string) => void; hint?: string
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label htmlFor={id} style={{
        display: 'block', fontSize: 11, letterSpacing: '0.08em',
        color: 'var(--text-muted)', marginBottom: 6,
      }}>{label}</label>
      <input id={id} type="password" value={value} className="form-input"
        onChange={e => onChange(e.target.value)} style={{ width: '100%' }} />
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--red)', marginTop: 4 }}>{hint}</div>
      )}
    </div>
  )
}
