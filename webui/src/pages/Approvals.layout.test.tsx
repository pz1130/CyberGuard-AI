import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import Approvals from './Approvals'

/**
 * The approvals row overlapped itself at ordinary window widths: the action
 * type was drawn on top of the status badge and the approve/reject buttons,
 * and the auto-refresh note was cut off the right edge.
 *
 * Every fixed-width part of the row already had flexShrink: 0, so when space
 * ran out the only thing that could give was the middle column — and its title
 * had no truncation, unlike the description directly beneath it. A long
 * single token cannot wrap, so it spilled over its neighbours instead.
 *
 * jsdom does not lay anything out, so these assert the properties that make
 * overlap impossible rather than measuring boxes.
 */
// Matches the screenshot that reported the bug: high risk, urgent, no agent
// name, and a description short enough that the action type is what overflows.
const PENDING = {
  id: 1,
  request_id: '493f651a-2ca2-4a63-a973-b080e3f08f13',
  user_id: 1,
  approver_id: null,
  agent_id: null,
  agent_name: null,
  action_type: 'agent_execution',
  action_description: '1:',
  payload: null,
  risk_level: 'high',
  urgency: 'urgent',
  status: 'pending',
  created_at: '2026-09-14T01:41:14Z',
  expires_at: '2026-09-14T02:41:14Z',
  decided_at: null,
  approver_comment: null,
}

describe('Approvals row layout', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getApprovals').mockResolvedValue(
      { requests: [PENDING], total: 1 } as never)
  })

  it('truncates the action type instead of letting it overflow', async () => {
    render(<Approvals />)
    const title = await screen.findByText('AGENT_EXECUTION')

    expect(title.style.overflow).toBe('hidden')
    expect(title.style.textOverflow).toBe('ellipsis')
    expect(title.style.whiteSpace).toBe('nowrap')
  })

  it('lets the middle column shrink below its content width', async () => {
    render(<Approvals />)
    const title = await screen.findByText('AGENT_EXECUTION')

    // The row that holds the title must be allowed to shrink, or the title's
    // own truncation never gets the chance to apply.
    const titleRow = title.parentElement as HTMLElement
    expect(titleRow.style.minWidth).toBe('0px')
  })

  it('gives each request a full-width row instead of a grid column', async () => {
    render(<Approvals />)
    await screen.findByText('AGENT_EXECUTION')

    // A multi-column grid made each card narrower than its fixed-width parts,
    // leaving the title 0–21px wide; more window width only added columns.
    const list = screen.getByTestId('approval-list')
    expect(list.style.display).toBe('flex')
    expect(list.style.flexDirection).toBe('column')
    expect(list.style.gridTemplateColumns).toBe('')
  })

  it('wraps the filter tabs rather than cutting them off', async () => {
    render(<Approvals />)
    const pending = await screen.findByRole('button', { name: 'PENDING' })
    const filterRow = pending.parentElement as HTMLElement

    expect(filterRow.style.flexWrap).toBe('wrap')
  })

  it('keeps the decision buttons at their full size', async () => {
    render(<Approvals />)
    await waitFor(() => expect(screen.getByTitle('APPROVE')).toBeTruthy())

    const buttons = screen.getByTitle('APPROVE').parentElement as HTMLElement
    expect(buttons.style.flexShrink).toBe('0')
  })
})
