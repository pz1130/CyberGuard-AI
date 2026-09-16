import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import GlobalSearch from './GlobalSearch'

/**
 * Round 1 removed message search: the transcript stopped being shipped with
 * the conversation list, so the pane could only match titles. This restores it
 * and goes further — the browser version only ever searched the 50 most recent
 * conversations, and only what was already in memory.
 */
describe('GlobalSearch — message hits', () => {
  beforeEach(() => {
    // Real timers: testing-library's findBy*/waitFor poll on their own timers,
    // and under fake timers that polling never advances — every test here hung
    // for five seconds, including one that does nothing.
    for (const name of [
      'getAgents', 'getProviders', 'getSkills', 'getTools', 'getKnowledgeBases',
      'getMCPServers', 'getPromptTemplates', 'getConversations',
    ] as const) {
      vi.spyOn(api, name).mockResolvedValue([] as never)
    }
    vi.spyOn(api, 'searchConversationMessages').mockResolvedValue({
      results: [{
        conversation_id: 7, conversation_title: 'Port scan triage',
        message_id: 91, seq: 3, role: 'assistant',
        created_at: '2026-09-16T10:00:00', snippet: '…three open ports…',
      }],
      next_cursor: 91,
    } as never)
  })

  const DEBOUNCE_MS = 250

  const type = async (text: string) => {
    render(<GlobalSearch open onClose={() => {}} setTab={() => {}} recentTabs={[]} />)
    const input = screen.getByPlaceholderText(/SEARCH AGENTS/i)
    fireEvent.change(input, { target: { value: text } })
    return input
  }

  const settle = () => new Promise(r => setTimeout(r, DEBOUNCE_MS * 2))

  it('asks the server for message hits', async () => {
    await type('ports')
    await waitFor(() =>
      expect(api.searchConversationMessages).toHaveBeenCalledWith('ports'))
  })

  it('shows the snippet the server returned', async () => {
    await type('ports')
    // The pane wraps the matched substring in its own <span>, so the snippet
    // renders as several text nodes. Match on the rendered text of the row.
    const rendered = await screen.findAllByText((_content, el) => {
      if (!el || el.children.length > 2) return false
      return (el.textContent || '').includes('three open ports')
    })
    expect(rendered.length).toBeGreaterThan(0)
  })

  it('debounces a burst of typing into one request', async () => {
    const input = await type('p')
    for (const value of ['po', 'por', 'port', 'ports']) {
      fireEvent.change(input, { target: { value } })
    }
    await waitFor(() =>
      expect(api.searchConversationMessages).toHaveBeenCalledTimes(1))
    expect(api.searchConversationMessages).toHaveBeenCalledWith('ports')
  })

  it('does not search on an empty query', async () => {
    await type('   ')
    await settle()
    expect(api.searchConversationMessages).not.toHaveBeenCalled()
  })
})
