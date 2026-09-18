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
      <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 180, flexShrink: 0, letterSpacing: '0.04em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)' }}>{label}</span>
      <div style={{ flex: 1, height: 16, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', transition: 'all 0.3s ease' }} />
      </div>
      <span style={{ fontSize: 12, color: 'var(--accent)', width: 64, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{(value / 1000).toFixed(1)}K</span>
    </div>
  )
}

export default function TokenUsage() {
  const { t } = useTranslation()
  const [data, setData] = useState<TokenUsageSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rangeDays, setRangeDays] = useState(30)
  const [retry, setRetry] = useState(0)
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
  }, [rangeDays, retry])

  const rangeControl = <select className="form-input" value={rangeDays}
    aria-label={t('token.dateRange')} onChange={e => setRangeDays(Number(e.target.value))}>
    {[7, 30, 90].map(days => <option key={days} value={days}>{t('token.lastDays', { count: days })}</option>)}
  </select>

  if (loading || error || !data) {
    return <div>
      <PageHeader eyebrow="COST ANALYSIS" title={t('token.title').toUpperCase()} actions={rangeControl} />
      <div className="card" style={{ padding: 20 }} role={error ? 'alert' : 'status'}>
        {loading ? t('token.loading') : t('token.loadError')}
        {error && <button className="btn" onClick={() => { setLoading(true); setError(null); setRetry(n => n + 1) }}>{t('common.retry')}</button>}
      </div>
    </div>
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
              style={{ width: 120, height: 32, fontSize: 12 }}
            >
              <option value={7}>{t('token.lastDays', { count: 7 })}</option>
              <option value={30}>{t('token.lastDays', { count: 30 })}</option>
              <option value={90}>{t('token.lastDays', { count: 90 })}</option>
            </select>
          </div>
        }
      />

      {/* Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
        {[
          { label: t('token.totalInputTokens').toUpperCase(), value: totalInput.toLocaleString(), color: 'var(--accent)', sub: 'PROMPT' },
          { label: t('token.totalOutputTokens').toUpperCase(), value: totalOutput.toLocaleString(), color: 'var(--text-primary)', sub: 'COMPLETION' },
          { label: t('token.estimatedCostUsd').toUpperCase(), value: data.priced_tokens > 0 ? '$' + totalCost.toFixed(4) : '—', color: 'var(--accent)', sub: 'ESTIMATED' },
        ].map(({ label, value, color, sub }) => (
          <div key={label} className="card" style={{ padding: '18px 20px', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 600 }}>{label}</span>
              <span className="badge badge-neutral" style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>{sub}</span>
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color, fontFamily: 'var(--font-mono)', letterSpacing: '0.02em' }}>{value}</div>
          </div>
        ))}
      </div>

      {data.unpriced_tokens > 0 && (
        <div style={{ margin: '-10px 0 16px', fontSize: 12, color: 'var(--text-muted)' }}>
          {t('token.unpricedNotice', { count: data.unpriced_tokens.toLocaleString() })}
        </div>
      )}

      {/* Bar chart */}
      <div className="card" style={{ padding: 0, marginBottom: 20, overflow: 'hidden' }}>
        <div style={{
          padding: '12px 18px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--bg-surface)',
        }}>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-primary)' }}>
            {t('token.inputByModel').toUpperCase()}
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }}>
            PROMPT TOKENS
          </span>
        </div>
        <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {data.by_model.length > 0 ? data.by_model.map(d => (
            <Bar key={`${d.provider_id}:${d.model_name}`} label={`${d.provider_name}/${d.model_name}`} value={d.prompt_tokens} max={maxVal} />
          )) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '16px 0' }}>{t('token.noData')}</div>
          )}
        </div>
      </div>

      {/* Table */}
      <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              {[t('token.model'), t('token.input'), t('token.output'), t('token.estimatedCostUsd')].map((h, i) => (
                <th key={i} style={i > 0 ? { textAlign: 'right' } : undefined}>{h.toUpperCase()}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.by_model.length > 0 ? data.by_model.map(d => (
              <tr key={`${d.provider_id}:${d.model_name}`}>
                <td style={{ color: 'var(--text-primary)', letterSpacing: '0.04em', fontFamily: 'var(--font-mono)' }}>{d.model_name}</td>
                <td style={{ color: 'var(--accent)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{(d.prompt_tokens / 1000).toFixed(1)}K</td>
                <td style={{ color: 'var(--text-primary)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{(d.completion_tokens / 1000).toFixed(1)}K</td>
                <td style={{ color: 'var(--accent)', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{d.estimated_cost_usd == null ? '—' : `$${d.estimated_cost_usd.toFixed(4)}`}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={4} style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>{t('token.noData')}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
