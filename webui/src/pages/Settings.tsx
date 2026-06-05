import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { Save, RotateCcw } from 'lucide-react'

interface MasterConfig {
  id: number
  model: string
  temperature: number
  system_prompt: string
  intent_parser_prompt: string
  summarizer_prompt: string
  max_rounds: number
  auto_approve_threshold: number
  // Branding
  branding_logo?: string | null
  branding_company_name?: string | null
}

interface ProviderModel {
  provider_id: number
  provider_name: string
  provider_type: string
  base_url: string
  model: string
  // optional verification status (only show usable/verified models in settings)
  verified?: boolean | null
  last_tested_at?: string | null
  test_error?: string | null
}

const DEFAULTS: MasterConfig = {
  id: 1,
  model: 'MiniMax-m2.7',
  temperature: 0.7,
  system_prompt: `You are CyberGuard, a security operations assistant. You help users with threat analysis, vulnerability assessment, log analysis, and security compliance. Be precise and actionable.`,
  intent_parser_prompt: `You are CyberGuard's intent parser. Analyze user input and create a task plan.

Output JSON with:
- intent: one of [task_execution, group_chat, knowledge_query, admin_action]
- task_plan: array of {"agent_type": str, "task": "description", "requires_approval": bool}
- reasoning: brief explanation

Task decomposition rules:
- Split compound requests into multiple tasks
- Each task maps to one agent_type
- Do NOT use agent_id — use agent_type only

agent_type options:
- threat_intel: threat IOC analysis, CVE lookup, malware analysis, APT tracking
- log_anomaly: log parsing, anomaly detection, SIEM alerts
- vuln_scanner: vulnerability scanning, CVE assessment, exploit analysis
- remediation: fix/remediate/mute/isolate/quarantine actions
- compliance: policy audit, framework compliance (ISO27001, GDPR, PCI-DSS)
- osint: open-source intelligence, recon, footprinting
- general: anything not matching above categories

Examples:
- "scan 192.168.1.0/24 for vulns" → agent_type: vuln_scanner
- "check if this IP is malicious" → agent_type: threat_intel
- "analyze firewall logs for anomalies" → agent_type: log_anomaly
- "block this domain" → agent_type: remediation`,
  summarizer_prompt: `You are CyberGuard's summarizer. Create a concise summary of agent results for the user.`,
  max_rounds: 10,
  auto_approve_threshold: 0,
  branding_logo: null,
  branding_company_name: null,
}

export default function Settings() {
  const { t } = useTranslation()
  const [config, setConfig] = useState<MasterConfig>(DEFAULTS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [availableModels, setAvailableModels] = useState<ProviderModel[]>([])

  // Load available models from providers
  useEffect(() => {
    const loadModels = async () => {
      try {
        const data = await api.getProviders() as { total: number; providers: any[] }
        if (!data?.providers) return
        const models: ProviderModel[] = []
        for (const p of data.providers) {
          if (!p.is_active) continue
          for (const m of (p.models || [])) {
            // Only show models that the user has explicitly verified (or seeded as verified).
            // Matches the logic in Chat.tsx: verified=true from /providers/test or /providers/{id}/models/probe.
            // Unverified / legacy string models are filtered out so Settings only offers usable ones.
            const entry = (typeof m === 'object' && m !== null) ? m as { name?: string; verified?: boolean | null } : null
            if (!entry || entry.verified !== true) continue
            models.push({
              provider_id: p.id,
              provider_name: p.name.toUpperCase(),
              provider_type: p.provider_type,
              base_url: (p.base_url || '').replace(/\/$/, ''),
              model: entry.name || '',
            })
          }
        }
        if (models.length > 0) setAvailableModels(models)
      } catch { /* use fallback */ }
    }
    loadModels()
  }, [])
  const [saved, setSaved] = useState(false)
  const [activeTab, setActiveTab] = useState<'master' | 'branding' | 'about'>('master')

  useEffect(() => {
    api.getMasterConfig().then((data: any) => {
      setConfig(data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      await api.updateMasterConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      // Notify live components (header) to refresh branding without full reload
      window.dispatchEvent(new CustomEvent('branding-updated'))
    } catch (e: any) {
      alert(t('settings.saveFailedPrefix') + e.message)
    } finally {
      setSaving(false)
    }
  }

  const reset = () => {
    if (!confirm(t('settings.resetConfirm'))) return
    setConfig(DEFAULTS)
  }

  const field = (key: keyof MasterConfig, label: string, extra?: { type: 'textarea' | 'number' | 'slider' | 'text'; rows?: number; min?: number; max?: number; step?: number }) => {
    const val = config[key] as string | number
    return (
      <div key={key} style={{ marginBottom: 20 }}>
        <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>{label}</label>
        {extra?.type === 'textarea' ? (
          <textarea
            value={val as string}
            rows={extra.rows || 8}
            onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
            style={{
              width: '100%', padding: '10px 12px',
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 14, lineHeight: 1.6,
              resize: 'vertical',
            }}
          />
        ) : extra?.type === 'slider' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <input
              type="range"
              min={extra.min || 0}
              max={extra.max || 1}
              step={extra.step || 0.1}
              value={val as number}
              onChange={e => setConfig(c => ({ ...c, [key]: parseFloat(e.target.value) }))}
              style={{ flex: 1 }}
            />
            <span style={{ fontSize: 14, color: 'var(--accent)', minWidth: 40 }}>{val as number}</span>
          </div>
        ) : extra?.type === 'number' ? (
          <input
            type="number"
            value={val as number}
            min={extra.min}
            max={extra.max}
            onChange={e => setConfig(c => ({ ...c, [key]: parseInt(e.target.value) }))}
            style={{
              width: 120, height: 36, padding: '0 12px',
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 14,
                          }}
          />
        ) : (
          <input
            type="text"
            value={val as string}
            onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
            style={{
              width: '100%', height: 36, padding: '0 12px',
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 14,
                          }}
          />
        )}
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 6 }}>{t('settings.systemConfig')}</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>{t('settings.title').toUpperCase()}</h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={reset} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0 14px', height: 36,
            border: '1px solid var(--border-bright)', background: 'transparent',
            color: 'var(--text-muted)', fontSize: 12, letterSpacing: '0.1em', cursor: 'pointer',
                      }}>
            <RotateCcw size={11} /> {t('settings.resetBtn')}
          </button>
          <button onClick={save} disabled={saving} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0 16px', height: 36,
            background: saved ? 'var(--green)' : 'var(--accent)',
            border: '1px solid var(--accent-border)',
            color: '#000', fontWeight: 700, fontSize: 12, letterSpacing: '0.06em',
            cursor: saving ? 'not-allowed' : 'pointer',           }}>
            <Save size={11} /> {saving ? t('settings.saving') : saved ? t('settings.saved') : t('settings.saveBtn')}
          </button>
        </div>
      </div>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: '1px solid var(--border)' }}>
        {(['master', 'branding', 'about'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '8px 20px', background: 'none', border: 'none', borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
            color: activeTab === tab ? 'var(--accent)' : 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em',
            cursor: 'pointer', textTransform: 'uppercase',
          }}>{t(`settings.${tab}`).toUpperCase()}</button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em' }}>LOADING...</div>
      ) : activeTab === 'master' ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
              {t('settings.modelConfig')}
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>{t('settings.modelLabel')}</label>
              <select
                value={config.model}
                onChange={e => setConfig(c => ({ ...c, model: e.target.value }))}
                style={{
                  width: '100%', height: 36, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14,
                                  }}>
                {availableModels.length === 0 && <option value={config.model}>{config.model} ({t('settings.modelLoadFail')})</option>}
                {availableModels.map(m => (
                  <option key={`${m.provider_id}:${m.model}`} value={m.model}>
                    {m.provider_name} / {m.model}
                  </option>
                ))}
              </select>
            </div>
            {field('temperature', 'TEMPERATURE', { type: 'slider', min: 0, max: 1, step: 0.05 })}
            {field('max_rounds', 'MAX ROUNDS', { type: 'number', min: 1, max: 50 })}
            {field('auto_approve_threshold', 'AUTO APPROVE THRESHOLD (0=never)', { type: 'number', min: 0, max: 100 })}
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
              {t('settings.promptConfig')}
            </div>
            {field('system_prompt', 'SYSTEM PROMPT', { type: 'textarea', rows: 6 })}
            {field('intent_parser_prompt', 'INTENT PARSER PROMPT', { type: 'textarea', rows: 10 })}
            {field('summarizer_prompt', 'SUMMARIZER PROMPT', { type: 'textarea', rows: 4 })}
          </div>
        </div>
      ) : activeTab === 'branding' ? (
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
            {t('settings.brandingTitle')}
          </div>
          <div style={{ maxWidth: 520 }}>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>{t('settings.companyName')}</label>
              <input
                type="text"
                value={config.branding_company_name || ''}
                onChange={e => setConfig(c => ({ ...c, branding_company_name: e.target.value || null }))}
                placeholder={t('settings.companyName')}
                style={{
                  width: '100%', height: 36, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 14,
                }}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>{t('settings.logo')}</label>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/svg+xml,image/webp"
                  onChange={async (e) => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    if (file.size > 2 * 1024 * 1024) { alert(t('settings.logoTooLarge')); return }
                    const reader = new FileReader()
                    reader.onload = () => {
                      const dataUrl = reader.result as string
                      setConfig(c => ({ ...c, branding_logo: dataUrl }))
                    }
                    reader.readAsDataURL(file)
                  }}
                  style={{ flex: 1 }}
                />
                <button
                  onClick={() => setConfig(c => ({ ...c, branding_logo: null, branding_company_name: null }))}
                  style={{ padding: '6px 12px', fontSize: 12, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}
                >
                  {t('settings.reset')}
                </button>
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>{t('settings.logoHelp')}</div>
            </div>

            {/* Preview */}
            <div style={{ marginTop: 12, padding: 16, background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 8 }}>{t('settings.preview')}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                {config.branding_logo ? (
                  <img src={config.branding_logo} alt="logo preview" style={{ width: 48, height: 48, objectFit: 'contain', border: '1px solid var(--border)', borderRadius: 6, background: '#fff' }} />
                ) : (
                  <div style={{ width: 48, height: 48, border: '1px solid var(--border)', borderRadius: 6, background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
                    ⬡
                  </div>
                )}
                <div style={{ fontSize: 15, fontWeight: 600 }}>
                  {config.branding_company_name || 'CyberGuard'}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ padding: '20px 0', color: 'var(--text-muted)', fontSize: 14, lineHeight: 1.8 }}>
          <div style={{ marginBottom: 16 }}>
            <span style={{ color: 'var(--accent)', letterSpacing: '0.1em' }}>CYBERGUARD OS</span>
            <span style={{ marginLeft: 12 }}>{t('settings.aboutVersion')}</span>
          </div>
          <div>{t('settings.aboutPlatform')}</div>
          <div style={{ marginTop: 16, color: 'var(--text-dim)', fontSize: 13 }}>
            {t('settings.aboutDesc')}
          </div>
        </div>
      )}
    </div>
  )
}