import { RoleContext } from '../context/permissions'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SearchProvider } from '../context/SearchContext'
import Chat from './Chat'

const getChatReadiness = vi.fn()
const getProviders = vi.fn()
const getConversations = vi.fn()
const getConversation = vi.fn()
const getConversationMessages = vi.fn()
const getAgents = vi.fn()
const getKnowledgeBases = vi.fn()
const getPromptTemplates = vi.fn()
const chatStream = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    getChatReadiness: () => getChatReadiness(),
    getProviders: (...args: unknown[]) => getProviders(...args),
    getConversations: (...args: unknown[]) => getConversations(...args),
    getConversation: (...args: unknown[]) => getConversation(...args),
    getConversationMessages: (...args: unknown[]) => getConversationMessages(...args),
    getAgents: (...args: unknown[]) => getAgents(...args),
    getKnowledgeBases: (...args: unknown[]) => getKnowledgeBases(...args),
    getPromptTemplates: (...args: unknown[]) => getPromptTemplates(...args),
    chatStream: (...args: unknown[]) => chatStream(...args),
  },
}))

const conversation = {
  id: 7,
  title: 'RC chat',
  updated_at: '2026-09-13T00:00:00Z',
}

function renderChat() {
  return render(
    <RoleContext.Provider value="admin"><SearchProvider>
      <Chat />
    </SearchProvider></RoleContext.Provider>,
  )
}

describe('Chat critical path', () => {
  beforeEach(() => {
    localStorage.clear()
    getChatReadiness.mockReset().mockResolvedValue({ master_ready: false })
    getProviders.mockReset().mockResolvedValue([
      {
        id: 34,
        name: 'MiniMax',
        provider_type: 'minimax',
        base_url: 'https://api.minimaxi.com',
        is_active: true,
        models: [{ name: 'MiniMax-M3', verified: true }],
      },
    ])
    getConversations.mockReset().mockResolvedValue([conversation])
    getConversation.mockReset().mockResolvedValue(conversation)
    getConversationMessages.mockReset().mockResolvedValue({ messages: [] })
    getAgents.mockReset().mockResolvedValue([])
    getKnowledgeBases.mockReset().mockResolvedValue([])
    getPromptTemplates.mockReset().mockResolvedValue([])
    chatStream.mockReset()
  })

  it('lets the operator pick a verified model, stream a reply, and collapse thinking', async () => {
    const user = userEvent.setup()
    async function* stream() {
      yield { type: 'chunk', content: '<think>hidden plan</think>visible answer' }
    }
    chatStream.mockReturnValue(stream())

    renderChat()

    expect(await screen.findByText(/AUTO requires a provider and model/)).toBeInTheDocument()
    const modelSelect = await screen.findByRole('combobox', { name: 'Model' })
    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'MINIMAX / MiniMax-M3' })).toBeInTheDocument()
    })
    await user.selectOptions(modelSelect, '34:MiniMax-M3')
    expect(localStorage.getItem('lastProviderModel')).toBe('34:MiniMax-M3')

    const input = await screen.findByPlaceholderText('Type your message...')
    await user.type(input, 'rank these alerts')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(chatStream).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'rank these alerts',
        conversation_id: 7,
        provider_id: 34,
        model: 'MiniMax-M3',
      }),
    )

    const thinking = await screen.findByText('Thinking process')
    expect(thinking.closest('details')).toBeTruthy()
    expect(thinking.closest('details')).toHaveTextContent('hidden plan')
    expect(screen.getByText('visible answer')).toBeInTheDocument()
    expect(screen.queryByText('<think>')).not.toBeInTheDocument()
  })
})
