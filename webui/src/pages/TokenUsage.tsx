import { Coins } from 'lucide-react'
import { useEffect, useState } from 'react'

interface TokenUsageByModel {
  provider_id: string
  provider_name: string
  model_name: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  call_count: number
}

interface TokenUsageSummary {
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
  total_calls: number
  total_cost_usd: number
  by_model: TokenUsageByModel[]
  by_date: Record<string, { prompt_tokens: number; completion_tokens: number; call_count: number }>
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.min((value / max) * 100, 100)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', width: 160, flexShrink: 0, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <div style={{ flex: 1, height: 14, background: 'var(--bg-base)', border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', transition: 'all 0.3s' }} />
      </div>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', width: 48, textAlign: 'right', letterSpacing: '0.05em', fontFamily: 'var(--font-mono)' }}>{(value / 1000).toFixed(0)}K</span>
    </div>
  )
}

export default function TokenUsage() {
  const [data, setData] = useState<TokenUsageSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('token')
        const response = await fetch('/api/v1/token-usage/summary', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })
        if (response.ok) {
          const result = await response.json()
          setData(result)
        } else {
          setError(`Failed to load data: ${response.status}`)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
        <div style={{ color: 'var(--text-muted)' }}>Loading token usage data...</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>COST ANALYSIS</div>
            <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>TOKEN USAGE</h1>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Coins size={16} style={{ color: 'var(--accent)' }} />
          </div>
        </div>
        <div style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', color: 'var(--text-muted)' }}>
          No token usage data available. Make LLM API calls to see usage here.
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-dim)', marginBottom: 6 }}>COST ANALYSIS</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-primary)' }}>TOKEN USAGE</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Coins size={16} style={{ color: 'var(--accent)' }} />
        </div>
      </div>

      {/* Summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'TOTAL INPUT TOKENS', value: (totalInput / 1000000).toFixed(2) + 'M', color: 'var(--cyan)' },
          { label: 'TOTAL OUTPUT TOKENS', value: (totalOutput / 1000000).toFixed(2) + 'M', color: 'var(--purple)' },
          { label: 'TOTAL COST (USD)', value: '$' + totalCost.toFixed(2), color: 'var(--amber)' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color, letterSpacing: '0.05em', marginBottom: 6 }}>{value}</div>
            <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.15em' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Bar chart */}
      <div style={{ padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', marginBottom: 24 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em', marginBottom: 16 }}>INPUT TOKENS BY MODEL</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {data.by_model.length > 0 ? data.by_model.map(d => (
            <Bar key={`${d.provider_id}:${d.model_name}`} label={`${d.provider_name}/${d.model_name}`} value={d.prompt_tokens} max={maxVal} />
          )) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>No data available</div>
          )}
        </div>
      </div>

      {/* Table */}
      <div style={{ border: '1px solid var(--border-bright)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--bg-base)', borderBottom: '1px solid var(--border-bright)' }}>
              {['MODEL', 'INPUT', 'OUTPUT', 'COST (USD)'].map((h, i) => (
                <th key={i} style={{ padding: '12px 16px', textAlign: i === 0 ? 'left' : 'right', fontSize: 9, letterSpacing: '0.2em', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.by_model.length > 0 ? data.by_model.map(d => (
              <tr key={`${d.provider_id}:${d.model_name}`} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '14px 16px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', letterSpacing: '0.05em' }}>{d.model_name}</td>
                <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>{(d.prompt_tokens / 1000).toFixed(1)}K</td>
                <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--text-muted)', textAlign: 'right', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>{(d.completion_tokens / 1000).toFixed(1)}K</td>
                <td style={{ padding: '14px 16px', fontSize: 11, color: 'var(--purple)', textAlign: 'right', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>${(d.prompt_tokens * 0.000001 * 2 + d.completion_tokens * 0.000006).toFixed(2)}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={4} style={{ padding: '14px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>No data available</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
