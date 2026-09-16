import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import ChatEvidence from './ChatEvidence'

/**
 * The auditor's panel. The purge control is the one that matters: it is the
 * only irreversible operation in the product, so it must not be reachable
 * without first seeing what would go.
 */
describe('ChatEvidence', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  const search = (term: string) => {
    fireEvent.change(screen.getByPlaceholderText(/keyword/i), { target: { value: term } })
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  }

  it('shows the snippets the auditor search returned', async () => {
    vi.spyOn(api, 'auditorSearchConversations').mockResolvedValue({
      results: [{ conversation_id: 7, conversation_title: 'Deleted by the user',
                  message_id: 91, seq: 2, role: 'assistant',
                  created_at: '2026-09-16T10:00:00', snippet: '…three open ports…' }],
    } as never)

    render(<ChatEvidence />)
    search('ports')

    expect(await screen.findByText(/three open ports/)).toBeTruthy()
    expect(screen.getByText(/Deleted by the user/)).toBeTruthy()
  })

  it('does not search on an empty query', () => {
    vi.spyOn(api, 'auditorSearchConversations').mockResolvedValue({ results: [] } as never)
    render(<ChatEvidence />)
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
    expect(api.auditorSearchConversations).not.toHaveBeenCalled()
  })

  it('shows the missing-configuration message instead of swallowing it', async () => {
    vi.spyOn(api, 'exportConversations').mockRejectedValue(
      new Error('S3/OSS not configured: set S3_ENDPOINT and S3_ACCESS_KEY.'))

    render(<ChatEvidence />)
    fireEvent.click(screen.getByRole('button', { name: /^export$/i }))

    expect(await screen.findByText(/S3_ENDPOINT/)).toBeTruthy()
  })

  it('offers no delete button before a dry run', () => {
    render(<ChatEvidence />)
    expect(screen.queryByRole('button', { name: /delete these permanently/i })).toBeNull()
  })

  it('offers no delete button when the dry run found nothing', async () => {
    vi.spyOn(api, 'purgeConversations').mockResolvedValue({ conversations: [] } as never)

    render(<ChatEvidence />)
    fireEvent.click(screen.getByRole('button', { name: /dry run/i }))

    await waitFor(() => expect(screen.getByText(/Nothing is eligible/i)).toBeTruthy())
    expect(screen.queryByRole('button', { name: /delete these permanently/i })).toBeNull()
  })

  it('lists what would go, and only then offers to delete it', async () => {
    vi.spyOn(api, 'purgeConversations').mockResolvedValue({
      conversations: [{ conversation_id: 4, messages: 12, object_key: 'worm/4.jsonl' }],
    } as never)

    render(<ChatEvidence />)
    fireEvent.click(screen.getByRole('button', { name: /dry run/i }))

    await waitFor(() => expect(screen.getByText(/worm\/4\.jsonl/)).toBeTruthy())
    expect(screen.getByText(/12 message\(s\) across 1 conversation\(s\)/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /delete these permanently/i })).toBeTruthy()
  })

  it('does not delete when the confirmation is not typed exactly', async () => {
    const purge = vi.spyOn(api, 'purgeConversations').mockResolvedValue({
      conversations: [{ conversation_id: 4, messages: 12, object_key: 'worm/4.jsonl' }],
    } as never)
    vi.spyOn(window, 'prompt').mockReturnValue('purge')   // lowercase

    render(<ChatEvidence />)
    fireEvent.click(screen.getByRole('button', { name: /dry run/i }))
    await waitFor(() => expect(screen.getByText(/worm\/4\.jsonl/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /delete these permanently/i }))

    expect(purge).toHaveBeenCalledTimes(1)          // the dry run only
    expect(purge).not.toHaveBeenCalledWith(expect.anything(), true)
  })

  it('deletes only when PURGE is typed', async () => {
    const purge = vi.spyOn(api, 'purgeConversations')
      .mockResolvedValueOnce({
        conversations: [{ conversation_id: 4, messages: 12, object_key: 'worm/4.jsonl' }],
      } as never)
      .mockResolvedValueOnce({ messages_deleted: 12 } as never)
    vi.spyOn(window, 'prompt').mockReturnValue('PURGE')

    render(<ChatEvidence />)
    fireEvent.click(screen.getByRole('button', { name: /dry run/i }))
    await waitFor(() => expect(screen.getByText(/worm\/4\.jsonl/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /delete these permanently/i }))

    await waitFor(() => expect(purge).toHaveBeenCalledWith(365, true))
    expect(await screen.findByText(/Deleted 12 message/)).toBeTruthy()
  })
})
