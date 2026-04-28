import { Coins } from 'lucide-react'

const MOCK_DATA = [
  { model: 'gpt-4o', input: 1245000, output: 560000, cost: 18.45 },
  { model: 'gpt-4o-mini', input: 3400000, output: 890000, cost: 3.21 },
  { model: 'claude-3-5-sonnet', input: 780000, output: 320000, cost: 12.80 },
  { model: 'gemini-2.0-flash', input: 2100000, output: 450000, cost: 1.55 },
]

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min((value / max) * 100, 100)
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-400 w-28 flex-shrink-0 truncate">{label}</span>
      <div className="flex-1 bg-slate-800 rounded-full h-4 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-300 w-20 text-right">{(value / 1000).toFixed(0)}K</span>
    </div>
  )
}

export default function TokenUsage() {
  const totalInput = MOCK_DATA.reduce((s, d) => s + d.input, 0)
  const totalOutput = MOCK_DATA.reduce((s, d) => s + d.output, 0)
  const totalCost = MOCK_DATA.reduce((s, d) => s + d.cost, 0)
  const maxVal = Math.max(...MOCK_DATA.map(d => d.input))

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2"><Coins size={20} /> Token 消耗</h2>
          <p className="text-xs text-slate-500 mt-1">模型调用统计与成本分析</p>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: '总 Input Tokens', value: (totalInput / 1000000).toFixed(2) + 'M', color: 'text-blue-400' },
          { label: '总 Output Tokens', value: (totalOutput / 1000000).toFixed(2) + 'M', color: 'text-violet-400' },
          { label: '总成本 (USD)', value: '$' + totalCost.toFixed(2), color: 'text-yellow-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-slate-900 rounded-xl p-4 text-center">
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
            <p className="text-xs text-slate-400 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Bar chart */}
      <div className="bg-slate-900 rounded-xl p-5 mb-6">
        <h3 className="text-sm font-medium text-slate-300 mb-4">Input Tokens 按模型分布</h3>
        <div className="space-y-3">
          {MOCK_DATA.map(d => (
            <Bar key={d.model} label={d.model} value={d.input} max={maxVal} color="bg-blue-500" />
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-slate-900 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="text-left px-4 py-3 text-slate-400 font-medium">模型</th>
              <th className="text-right px-4 py-3 text-slate-400 font-medium">Input</th>
              <th className="text-right px-4 py-3 text-slate-400 font-medium">Output</th>
              <th className="text-right px-4 py-3 text-slate-400 font-medium">成本 (USD)</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_DATA.map(d => (
              <tr key={d.model} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                <td className="px-4 py-3 text-white font-mono text-xs">{d.model}</td>
                <td className="px-4 py-3 text-right text-slate-300">{(d.input / 1000).toFixed(1)}K</td>
                <td className="px-4 py-3 text-right text-slate-300">{(d.output / 1000).toFixed(1)}K</td>
                <td className="px-4 py-3 text-right text-violet-400">${d.cost.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
