import { Coins } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface TokenUsageByModel {
  provider_id: string
  provider_name: string
  model_name: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  call_count: number
  estimated_cost_usd: number | null
}

interface TokenUsageSummary {
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
  total_calls: number
  total_cost_usd: number
  priced_tokens: number
  unpriced_tokens: number
  by_model: TokenUsageByModel[]
  by_date: Record<string, { prompt_tokens: number; completion_tokens: number; call_count: number }>
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.min((value / max) * 100, 100)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 160, flexShrink: 0, letterSpacing: '0.05em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <div style={{ flex: 1, height: 14, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', transition: 'all 0.3s' }} />
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 48, textAlign: 'right', letterSpacing: '0.05em' }}>{(value / 1000).toFixed(0)}K</span>
    </div>
  )
}

export default function TokenUsage() {
  const { t } = useTranslation()
  const [data, setData] = useState<TokenUsageSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rangeDays, setRangeDays] = useState(30)
  const [prevRangeDays, setPrevRangeDays] = useState(rangeDays)

  if (rangeDays !== prevRangeDays) {
    setPrevRangeDays(rangeDays)
    setLoading(true)
    setError(null)
  }

  useEffect(() => {
    const start = new Date()
    start.setDate(start.getDate() - rangeDays + 1)
    const startDate = [
      start.getFullYear(),
      String(start.getMonth() + 1).padStart(2, '0'),
      String(start.getDate()).padStart(2, '0'),
    ].join('-')
    let cancelled = false
    api.getTokenUsageSummary(startDate)
      .then(result => { if (!cancelled) setData(result as TokenUsageSummary) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Unknown error') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [rangeDays])

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
        <div style={{ color: 'var(--text-muted)' }}>{t('token.loading')}</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div>
        <PageHeader
          eyebrow="COST ANALYSIS"
          title={t('token.title').toUpperCase()}
          actions={
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Coins size={16} style={{ color: 'var(--accent)' }} />
            </div>
          }
        />
        <div className="item-card" style={{ padding: 20, color: 'var(--text-muted)' }}>
          {t('token.loadError')}
        </div>
      </div>
    )
  }

  const totalInput = data.total_prompt_tokens
  const totalOutput = data.total_completion_tokens
  const totalCost = data.total_cost_usd
  const maxVal = Math.max(...data.by_model.map(d => d.prompt_tokens), 1)

  return (
    <div>
      {/* Header */}
      <PageHeader
        eyebrow={t('token.costAnalysis').toUpperCase()}
        title={t('token.title').toUpperCase()}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Coins size={16} style={{ color: 'var(--accent)' }} />
            <select
              className="form-input"
              value={rangeDays}
              onChange={e => setRangeDays(Number(e.target.value))}
              aria-label={t('token.dateRange')}
              style={{ width: 110, height: 32, fontSize: 12 }}
            >
              <option value={7}>{t('token.lastDays', { count: 7 })}</option>
              <option value={30}>{t('token.lastDays', { count: 30 })}</option>
              <option value={90}>{t('token.lastDays', { count: 90 })}</option>
            </select>
          </div>
        }
      />

      {/* Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: t('token.totalInputTokens').toUpperCase(), value: totalInput.toLocaleString(), color: 'var(--cyan)' },
          { label: t('token.totalOutputTokens').toUpperCase(), value: totalOutput.toLocaleString(), color: 'var(--purple)' },
          { label: t('token.estimatedCostUsd').toUpperCase(), value: data.priced_tokens > 0 ? '$' + totalCost.toFixed(4) : '—', color: 'var(--amber)' },
        ].map(({ label, value, color }) => (
          <div key={label} className="item-card" style={{ padding: 20, textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color, letterSpacing: '0.05em', marginBottom: 6 }}>{value}</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.06em' }}>{label}</div>
          </div>
        ))}
      </div>

      {data.unpriced_tokens > 0 && (
        <div style={{ margin: '-12px 0 20px', fontSize: 12, color: 'var(--text-muted)' }}>
          {t('token.unpricedNotice', { count: data.unpriced_tokens.toLocaleString() })}
        </div>
      )}

      {/* Bar chart */}
      <div className="item-card" style={{ padding: 20, marginBottom: 24 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16 }}>{t('token.inputByModel').toUpperCase()}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {data.by_model.length > 0 ? data.by_model.map(d => (
            <Bar key={`${d.provider_id}:${d.model_name}`} label={`${d.provider_name}/${d.model_name}`} value={d.prompt_tokens} max={maxVal} />
          )) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>{t('token.noData')}</div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="item-card" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              {[t('token.model'), t('token.input'), t('token.output'), t('token.estimatedCostUsd')].map((h, i) => (
                <th key={i} style={i > 0 ? { textAlign: 'right' } : undefined}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.by_model.length > 0 ? data.by_model.map(d => (
              <tr key={`${d.provider_id}:${d.model_name}`}>
                <td style={{ color: 'var(--text-primary)', letterSpacing: '0.05em' }}>{d.model_name}</td>
                <td style={{ color: 'var(--text-muted)', textAlign: 'right', letterSpacing: '0.05em' }}>{(d.prompt_tokens / 1000).toFixed(1)}K</td>
                <td style={{ color: 'var(--text-muted)', textAlign: 'right', letterSpacing: '0.05em' }}>{(d.completion_tokens / 1000).toFixed(1)}K</td>
                <td style={{ color: 'var(--purple)', textAlign: 'right', letterSpacing: '0.05em' }}>{d.estimated_cost_usd == null ? '—' : `$${d.estimated_cost_usd.toFixed(4)}`}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={4} style={{ padding: '14px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>{t('token.noData')}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
