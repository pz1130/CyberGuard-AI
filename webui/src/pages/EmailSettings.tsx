import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { errorMessage } from '../lib/errorMessage'

type TemplateKind = 'created' | 'decided'
type TemplateKey = 'created_subject' | 'created_body' | 'decided_subject' | 'decided_body'
const sampleValues: Record<TemplateKind, Record<string, string>> = {
  created: { request_id: 'sample-request-001', action_description: '隔离可疑主机 / Isolate suspicious host', risk_level: 'HIGH', user_id: '42' },
  decided: { request_id: 'sample-request-001', decision: 'APPROVED', comment: '已确认，可执行 / Reviewed and approved' },
}
const previewTemplate = (template: string, kind: TemplateKind, html: boolean) =>
  template.replace(/\{\{\s*([a-z_]+)\s*\}\}/g, (_, key: string) => {
    const value = sampleValues[kind][key] || ''
    return html ? value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;') : value
  })

interface MailConfig {
  enabled: boolean
  method: 'smtp' | 'oauth'
  from_email: string | null
  admin_email: string | null
  smtp_host: string
  smtp_port: number
  smtp_security: 'starttls' | 'ssl' | 'none'
  smtp_username: string
  oauth_tenant_id: string | null
  oauth_client_id: string | null
  notify_created: boolean
  notify_decided: boolean
  created_subject?: string
  created_body?: string
  decided_subject?: string
  decided_body?: string
  template_defaults?: Record<TemplateKey, string>
  smtp_password_set?: boolean
  oauth_client_secret_set?: boolean
}

export default function EmailSettings() {
  const { t } = useTranslation()
  const [config, setConfig] = useState<MailConfig | null>(null)
  const [password, setPassword] = useState('')
  const [secret, setSecret] = useState('')
  const [clearPassword, setClearPassword] = useState(false)
  const [clearSecret, setClearSecret] = useState(false)
  const [templateKind, setTemplateKind] = useState<TemplateKind>('created')
  const [testTemplate, setTestTemplate] = useState<'connection' | TemplateKind>('connection')
  const [recipient, setRecipient] = useState('')
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.getEmailConfig().then(data => setConfig(data as MailConfig)).catch(e => setError(errorMessage(e)))
  }, [])

  const update = (patch: Partial<MailConfig>) => {
    setConfig(c => c ? { ...c, ...patch } : c)
    setDirty(true); setNotice('')
  }
  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!config) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api.updateEmailConfig({ ...config,
        smtp_password: clearPassword ? '' : password || null,
        oauth_client_secret: clearSecret ? '' : secret || null,
      })
      setConfig(result as MailConfig)
      setPassword(''); setSecret(''); setClearPassword(false); setClearSecret(false)
      setDirty(false); setNotice(t('email.saved'))
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }
  const test = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true); setError(''); setNotice('')
    try {
      await api.testEmail({ to_email: recipient, ...(testTemplate === 'connection' ? {} : { template: testTemplate }) })
      setNotice(t('email.testSent'))
    } catch (e) { setError(errorMessage(e)) }
    finally { setBusy(false) }
  }

  const textField = (key: 'from_email' | 'admin_email' | 'smtp_host' | 'smtp_username' | 'oauth_tenant_id' | 'oauth_client_id', required = false) => (
    <label style={{ display: 'grid', gap: 6 }}>
      {t(`email.${key}`)}
      <input value={config?.[key] || ''} required={required} maxLength={255}
        onChange={e => update({ [key]: e.target.value || (key === 'smtp_host' || key === 'smtp_username' ? '' : null) })} />
    </label>
  )

  return <div style={{ maxWidth: 850 }}>
    <h2>{t('email.title')}</h2>
    <p style={{ color: 'var(--text-muted)' }}>{t('email.description')}</p>
    {error && <p role="alert" style={{ color: 'var(--red)' }}>{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!config ? <p>{t('email.loading')}</p> : <>
      <form onSubmit={save}>
        <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
          <label><input type="checkbox" checked={config.enabled} onChange={e => update({ enabled: e.target.checked })} /> {t('email.enabled')}</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20, margin: '20px 0' }}>
            <label style={{ display: 'grid', gap: 6 }}>{t('email.method')}
              <select value={config.method} onChange={e => update({ method: e.target.value as MailConfig['method'] })}>
                <option value="smtp">SMTP</option><option value="oauth">Microsoft 365 / Outlook OAuth</option>
              </select>
            </label>
            {textField('from_email', config.enabled)}
            {textField('admin_email')}
          </div>
          <p style={{ color: 'var(--text-muted)' }}>{t('email.recipientsHint')}</p>
          {config.method === 'smtp' ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20 }}>
            {textField('smtp_host', config.enabled)}
            <label style={{ display: 'grid', gap: 6 }}>{t('email.port')}
              <input type="number" min={1} max={65535} required value={config.smtp_port} onChange={e => update({ smtp_port: Number(e.target.value) })} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>{t('email.security')}
              <select value={config.smtp_security} onChange={e => update({ smtp_security: e.target.value as MailConfig['smtp_security'] })}>
                <option value="starttls">STARTTLS</option><option value="ssl">SSL / TLS</option><option value="none">{t('email.plain')}</option>
              </select>
            </label>
            {textField('smtp_username')}
            <label style={{ display: 'grid', gap: 6 }}>{t('email.password')}
              <input type="password" autoComplete="new-password" disabled={clearPassword} value={password}
                placeholder={config.smtp_password_set ? t('email.secretSaved') : ''}
                onChange={e => { setPassword(e.target.value); setDirty(true) }} />
            </label>
            <label><input type="checkbox" checked={clearPassword} onChange={e => { setClearPassword(e.target.checked); setDirty(true) }} /> {t('email.clearPassword')}</label>
          </div> : <>
            <p>{t('email.oauthHint')} <a href="https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0" target="_blank" rel="noreferrer">{t('email.oauthDocs')}</a></p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20 }}>
              {textField('oauth_tenant_id', config.enabled)}
              {textField('oauth_client_id', config.enabled)}
              <label style={{ display: 'grid', gap: 6 }}>{t('email.clientSecret')}
                <input type="password" autoComplete="new-password" disabled={clearSecret} value={secret}
                  placeholder={config.oauth_client_secret_set ? t('email.secretSaved') : ''}
                  onChange={e => { setSecret(e.target.value); setDirty(true) }} />
              </label>
              <label><input type="checkbox" checked={clearSecret} onChange={e => { setClearSecret(e.target.checked); setDirty(true) }} /> {t('email.clearSecret')}</label>
            </div>
          </>}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, margin: '24px 0' }}>
            <label><input type="checkbox" checked={config.notify_created} onChange={e => update({ notify_created: e.target.checked })} /> {t('email.notifyCreated')}</label>
            <label><input type="checkbox" checked={config.notify_decided} onChange={e => update({ notify_decided: e.target.checked })} /> {t('email.notifyDecided')}</label>
          </div>
          <section style={{ borderTop: '1px solid var(--border)', paddingTop: 20, marginBottom: 24 }}>
            <h3>{t('email.templates')}</h3>
            <label style={{ display: 'grid', gap: 6 }}>{t('email.templateType')}
              <select value={templateKind} onChange={e => setTemplateKind(e.target.value as TemplateKind)}>
                <option value="created">{t('email.createdTemplate')}</option>
                <option value="decided">{t('email.decidedTemplate')}</option>
              </select>
            </label>
            <p style={{ color: 'var(--text-muted)' }}>{t('email.variablesHint')}<br />
              {Object.keys(sampleValues[templateKind]).map(key => <code key={key} style={{ marginRight: 12 }}>{`{{${key}}}`}</code>)}
            </p>
            <label style={{ display: 'grid', gap: 6, marginBottom: 16 }}>{t('email.templateSubject')}
              <input required maxLength={255} value={config[`${templateKind}_subject`] || ''}
                onChange={e => update({ [`${templateKind}_subject`]: e.target.value })} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>{t('email.templateBody')}
              <textarea required rows={10} maxLength={50000} style={{ width: '100%', resize: 'vertical', fontFamily: 'monospace' }}
                value={config[`${templateKind}_body`] || ''}
                onChange={e => update({ [`${templateKind}_body`]: e.target.value })} />
            </label>
            <button className="btn" type="button" style={{ marginTop: 12 }} disabled={!config.template_defaults}
              onClick={() => update({
                [`${templateKind}_subject`]: config.template_defaults?.[`${templateKind}_subject`],
                [`${templateKind}_body`]: config.template_defaults?.[`${templateKind}_body`],
              })}>{t('email.restoreTemplate')}</button>
            <h4>{t('email.preview')}</h4>
            <p>{previewTemplate(config[`${templateKind}_subject`] || '', templateKind, false)}</p>
            <iframe title={t('email.preview')} sandbox="" referrerPolicy="no-referrer"
              style={{ width: '100%', minHeight: 220, background: '#fff', border: '1px solid var(--border)' }}
              srcDoc={`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">${previewTemplate(config[`${templateKind}_body`] || '', templateKind, true)}`} />
          </section>
          <button className="btn btn-primary" type="submit">{busy ? t('email.working') : t('email.save')}</button>
        </fieldset>
      </form>
      <form onSubmit={test} style={{ borderTop: '1px solid var(--border)', marginTop: 24, paddingTop: 20 }}>
        <label style={{ display: 'grid', gap: 6, marginBottom: 16 }}>{t('email.testTemplate')}
          <select value={testTemplate} disabled={busy} onChange={e => setTestTemplate(e.target.value as typeof testTemplate)}>
            <option value="connection">{t('email.connectionTest')}</option>
            <option value="created">{t('email.createdTemplate')}</option>
            <option value="decided">{t('email.decidedTemplate')}</option>
          </select>
        </label>
        <label style={{ display: 'grid', gap: 6 }}>{t('email.testRecipient')}
          <input required value={recipient} disabled={busy} onChange={e => setRecipient(e.target.value)} />
        </label>
        <p style={{ color: 'var(--text-muted)' }}>{t('email.testHint')}</p>
        <button className="btn" type="submit" disabled={busy || dirty || !config.enabled}>{t('email.test')}</button>
      </form>
    </>}
  </div>
}
