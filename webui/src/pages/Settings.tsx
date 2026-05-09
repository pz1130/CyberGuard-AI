import { useState, useEffect } from 'react'
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
}

interface ProviderModel {
  provider_id: number
  provider_name: string
  provider_type: string
  base_url: string
  model: string
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
}

export default function Settings() {
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
            models.push({
              provider_id: p.id,
              provider_name: p.name.toUpperCase(),
              provider_type: p.provider_type,
              base_url: (p.base_url || '').replace(/\/$/, ''),
              model: typeof m === 'string' ? m : (m as any).name || m,
            })
          }
        }
        if (models.length > 0) setAvailableModels(models)
      } catch { /* use fallback */ }
    }
    loadModels()
  }, [])
  const [saved, setSaved] = useState(false)
  const [activeTab, setActiveTab] = useState<'master' | 'about'>('master')

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
    } catch (e: any) {
      alert('Save failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const reset = () => {
    if (!confirm('Reset to defaults?')) return
    setConfig(DEFAULTS)
  }

  const field = (key: keyof MasterConfig, label: string, extra?: { type: 'textarea' | 'number' | 'slider' | 'text'; rows?: number; min?: number; max?: number; step?: number }) => {
    const val = config[key] as string | number
    return (
      <div key={key} style={{ marginBottom: 20 }}>
        <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>{label}</label>
        {extra?.type === 'textarea' ? (
          <textarea
            value={val as string}
            rows={extra.rows || 8}
            onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
            style={{
              width: '100%', padding: '10px 12px',
              background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
              color: 'var(--text-primary)', fontSize: 12, lineHeight: 1.6,
              fontFamily: 'var(--font-mono)', resize: 'vertical',
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
            <span style={{ fontSize: 12, color: 'var(--accent)', minWidth: 40 }}>{val as number}</span>
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
              color: 'var(--text-primary)', fontSize: 12,
              fontFamily: 'var(--font-mono)',
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
              color: 'var(--text-primary)', fontSize: 12,
              fontFamily: 'var(--font-mono)',
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
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>SYSTEM CONFIGURATION</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>SETTINGS</h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={reset} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0 14px', height: 36,
            border: '1px solid var(--border-bright)', background: 'transparent',
            color: 'var(--text-muted)', fontSize: 10, letterSpacing: '0.1em', cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
          }}>
            <RotateCcw size={11} /> RESET
          </button>
          <button onClick={save} disabled={saving} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0 16px', height: 36,
            background: saved ? 'var(--green)' : 'var(--accent)',
            border: '1px solid var(--accent-border)',
            color: '#000', fontWeight: 700, fontSize: 10, letterSpacing: '0.15em',
            cursor: saving ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-mono)',
          }}>
            <Save size={11} /> {saving ? 'SAVING...' : saved ? 'SAVED!' : 'SAVE CHANGES'}
          </button>
        </div>
      </div>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: '1px solid var(--border)' }}>
        {(['master', 'about'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '8px 20px', background: 'none', border: 'none', borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
            color: activeTab === tab ? 'var(--accent)' : 'var(--text-muted)', fontSize: 11, letterSpacing: '0.1em',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', textTransform: 'uppercase',
          }}>{tab === 'master' ? 'MASTER AGENT' : 'ABOUT'}</button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 11, letterSpacing: '0.1em' }}>LOADING...</div>
      ) : activeTab === 'master' ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
              MODEL CONFIGURATION
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>MODEL</label>
              <select
                value={config.model}
                onChange={e => setConfig(c => ({ ...c, model: e.target.value }))}
                style={{
                  width: '100%', height: 36, padding: '0 12px',
                  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
                  color: 'var(--text-primary)', fontSize: 12,
                  fontFamily: 'var(--font-mono)',
                }}>
                {availableModels.length === 0 && <option value={config.model}>{config.model} (无法加载 Provider)</option>}
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
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border)' }}>
              PROMPT CONFIGURATION
            </div>
            {field('system_prompt', 'SYSTEM PROMPT', { type: 'textarea', rows: 6 })}
            {field('intent_parser_prompt', 'INTENT PARSER PROMPT', { type: 'textarea', rows: 10 })}
            {field('summarizer_prompt', 'SUMMARIZER PROMPT', { type: 'textarea', rows: 4 })}
          </div>
        </div>
      ) : (
        <div style={{ padding: '20px 0', color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.8 }}>
          <div style={{ marginBottom: 16 }}>
            <span style={{ color: 'var(--accent)', letterSpacing: '0.1em' }}>CYBERGUARD OS</span>
            <span style={{ marginLeft: 12 }}>Version 1.0.0</span>
          </div>
          <div>Enterprise Security Operations Platform</div>
          <div style={{ marginTop: 16, color: 'var(--text-dim)', fontSize: 11 }}>
            Multi-agent orchestration with LangGraph · MCP tool protocol · Real-time group chat · Knowledge base RAG · Full audit trail
          </div>
        </div>
      )}
    </div>
  )
}