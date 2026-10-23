import { RoleContext } from '../context/permissions'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { api } from '../api/client'
import GlobalSearch from './GlobalSearch'

/**
 * The conversation list no longer carries every message. Until Round 2 adds a
 * server-side message search, this pane matches titles and the server-rendered
 * preview — and must not crash on the absent field.
 */
/** The pane lists nothing until a query is typed. */
async function _search(text: string) {
  const input = await screen.findByPlaceholderText(/SEARCH AGENTS/i)
  fireEvent.change(input, { target: { value: text } })
}

/**
 * The matched substring is wrapped in its own <span>, so a matched title or
 * preview is several text nodes. Match on the rendered text of the whole row.
 */
function _rendered(text: string) {
  // getAllBy: when the query matches the whole string, the highlight span and
  // its wrapper both render exactly that text. Either one proves it is there.
  const matches = screen.getAllByText((_content, el) => {
    if (!el || el.children.length > 2) return false
    return el.textContent === text
  })
  return matches[0]
}

describe('GlobalSearch conversations', () => {
  beforeEach(() => {
    for (const name of [
      'getAgents', 'getProviders', 'getSkills', 'getTools', 'getKnowledgeBases',
      'getMCPServers', 'getPromptTemplates',
    ] as const) {
      vi.spyOn(api, name).mockResolvedValue([] as never)
    }
  })

  it('shows the server-rendered preview and count', async () => {
    vi.spyOn(api, 'getConversations').mockResolvedValue([
      { id: 4, title: 'Port scan triage', message_count: 12,
        last_message_preview: 'three open ports' },
    ] as never)

    render(<RoleContext.Provider value="admin"><GlobalSearch open onClose={() => {}} setTab={() => {}} recentTabs={[]} /></RoleContext.Provider>)
    await _search('port')

    await waitFor(() => expect(_rendered('Port scan triage')).toBeTruthy())
    expect(screen.getByText('12 messages')).toBeTruthy()
    expect(_rendered('three open ports')).toBeTruthy()
  })

  it('renders a conversation with no messages without crashing', async () => {
    vi.spyOn(api, 'getConversations').mockResolvedValue([
      { id: 5, title: 'Empty', message_count: 0, last_message_preview: null },
    ] as never)

    render(<RoleContext.Provider value="admin"><GlobalSearch open onClose={() => {}} setTab={() => {}} recentTabs={[]} /></RoleContext.Provider>)
    await _search('empty')

    await waitFor(() => expect(_rendered('Empty')).toBeTruthy())
    expect(screen.getByText('EMPTY')).toBeTruthy()
  })
})
