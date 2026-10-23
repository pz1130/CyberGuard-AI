import { RoleContext } from '../context/permissions'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SearchProvider } from '../context/SearchContext'
import Chat from './Chat'

/**
 * A purged conversation has no messages, but it is not an empty conversation.
 * Showing the ordinary "ready — send a message" state would tell the person
 * their history was never there, when in fact it was archived to write-once
 * storage and the row still names the object holding it.
 */
const getProviders = vi.fn()
const getConversations = vi.fn()
const getConversation = vi.fn()
const getConversationMessages = vi.fn()
const getAgents = vi.fn()
const getKnowledgeBases = vi.fn()
const getPromptTemplates = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    getProviders: (...a: unknown[]) => getProviders(...a),
    getConversations: (...a: unknown[]) => getConversations(...a),
    getConversation: (...a: unknown[]) => getConversation(...a),
    getConversationMessages: (...a: unknown[]) => getConversationMessages(...a),
    getAgents: (...a: unknown[]) => getAgents(...a),
    getKnowledgeBases: (...a: unknown[]) => getKnowledgeBases(...a),
    getPromptTemplates: (...a: unknown[]) => getPromptTemplates(...a),
    chatStream: vi.fn(),
  },
}))

const renderChat = () =>
  render(<RoleContext.Provider value="admin"><SearchProvider><Chat /></SearchProvider></RoleContext.Provider>)

describe('Chat — an archived conversation', () => {
  beforeEach(() => {
    localStorage.clear()
    getProviders.mockReset().mockResolvedValue([])
    getAgents.mockReset().mockResolvedValue([])
    getKnowledgeBases.mockReset().mockResolvedValue([])
    getPromptTemplates.mockReset().mockResolvedValue([])
    getConversationMessages.mockReset().mockResolvedValue({ messages: [] })
  })

  it('says the transcript was archived rather than that it is empty', async () => {
    const conv = { id: 5, title: 'Archived work', archived: true,
                   updated_at: '2026-09-13T00:00:00Z' }
    getConversations.mockReset().mockResolvedValue([conv])
    getConversation.mockReset().mockResolvedValue(conv)

    renderChat()

    await waitFor(() =>
      expect(screen.getByText(/has been archived/i)).toBeTruthy())
  })

  it('still shows the ordinary empty state for a new conversation', async () => {
    const conv = { id: 6, title: 'Brand new', archived: false,
                   updated_at: '2026-09-13T00:00:00Z' }
    getConversations.mockReset().mockResolvedValue([conv])
    getConversation.mockReset().mockResolvedValue(conv)

    renderChat()

    await waitFor(() => expect(screen.getByText(/READY/i)).toBeTruthy())
    expect(screen.queryByText(/has been archived/i)).toBeNull()
  })
})
