import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TokenUsage from './TokenUsage'

const getTokenUsageSummary = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    getTokenUsageSummary: (...args: unknown[]) => getTokenUsageSummary(...args),
  },
}))

describe('Token Usage', () => {
  beforeEach(() => {
    getTokenUsageSummary.mockReset().mockResolvedValue({
      total_prompt_tokens: 12000,
      total_completion_tokens: 3400,
      total_tokens: 15400,
      total_calls: 7,
      total_cost_usd: 0.1234,
      priced_tokens: 15400,
      unpriced_tokens: 0,
      by_model: [
        {
          provider_id: '34',
          provider_name: 'MiniMax',
          model_name: 'MiniMax-M3',
          prompt_tokens: 12000,
          completion_tokens: 3400,
          total_tokens: 15400,
          call_count: 7,
          estimated_cost_usd: 0.1234,
        },
      ],
      by_date: {},
    })
  })

  it('renders totals and per-model usage', async () => {
    render(<TokenUsage />)

    expect(await screen.findByRole('heading', { name: /token usage/i })).toBeInTheDocument()
    expect(screen.getByText('12,000')).toBeInTheDocument()
    expect(screen.getByText('3,400')).toBeInTheDocument()
    expect(screen.getAllByText('$0.1234').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('MiniMax-M3')).toBeInTheDocument()
    expect(screen.getByText('MiniMax/MiniMax-M3')).toBeInTheDocument()
  })
})
