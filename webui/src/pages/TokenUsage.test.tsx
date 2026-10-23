import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    expect(await screen.findByText('12,000')).toBeInTheDocument()
    expect(screen.getByText('3,400')).toBeInTheDocument()
    expect(screen.getAllByText('$0.1234').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('MiniMax-M3')).toBeInTheDocument()
    expect(screen.getByText('MiniMax/MiniMax-M3')).toBeInTheDocument()
  })
  it('switches 7/90 day ranges using calendar dates and keeps the selector after failure', async () => {
    render(<TokenUsage />)
    await screen.findByText('12,000')
    getTokenUsageSummary.mockRejectedValueOnce(new Error('Temporary failure'))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '7' } })
    await screen.findByRole('alert')
    expect(screen.getByRole('combobox')).toHaveValue('7')
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    await screen.findByText('12,000')
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '90' } })
    await waitFor(() => expect(getTokenUsageSummary).toHaveBeenCalledTimes(4))
    for (const [start] of getTokenUsageSummary.mock.calls) expect(start).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    await screen.findByText('12,000')
  })

})
