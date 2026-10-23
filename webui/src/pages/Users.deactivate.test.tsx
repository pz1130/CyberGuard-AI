import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import Users from './Users'

/**
 * Removing a user deactivates them. Deleting is impossible for anyone who has
 * held a conversation — conversations.user_id is NOT NULL behind a plain
 * foreign key — and cascading would destroy the transcripts the product
 * exists to preserve. So the control has to say what it does, and there has to
 * be a way back, or deactivation is deletion with extra steps.
 */
const ACTIVE = { id: 3, username: 'amy', email: 'amy@company.local',
                 role: 'operator', is_active: true }
const INACTIVE = { ...ACTIVE, id: 4, username: 'bob', is_active: false }

describe('Users — deactivation', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getSsoConfig').mockResolvedValue({} as never)
    vi.spyOn(api, 'getSsoRoleMappings').mockResolvedValue([] as never)
    vi.spyOn(api, 'getSecretEnvVars').mockResolvedValue([] as never)
    vi.spyOn(api, 'deleteUser').mockResolvedValue(null as never)
    vi.spyOn(api, 'updateUser').mockResolvedValue({} as never)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('offers deactivation for an active user', async () => {
    vi.spyOn(api, 'getUsers').mockResolvedValue([ACTIVE] as never)
    render(<Users />)

    const button = await screen.findByRole('button', { name: /deactivate/i })
    fireEvent.click(button)
    await waitFor(() => expect(api.deleteUser).toHaveBeenCalledWith(3))
  })

  it('offers reactivation for an inactive one', async () => {
    vi.spyOn(api, 'getUsers').mockResolvedValue([INACTIVE] as never)
    render(<Users />)

    const button = await screen.findByRole('button', { name: /reactivate/i })
    fireEvent.click(button)
    await waitFor(() =>
      expect(api.updateUser).toHaveBeenCalledWith(4, { is_active: true }))
  })

  it('never offers both for the same user', async () => {
    vi.spyOn(api, 'getUsers').mockResolvedValue([ACTIVE] as never)
    render(<Users />)

    await screen.findByRole('button', { name: /deactivate/i })
    expect(screen.queryByRole('button', { name: /reactivate/i })).toBeNull()
  })

  it('does nothing when the confirmation is declined', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    vi.spyOn(api, 'getUsers').mockResolvedValue([ACTIVE] as never)
    render(<Users />)

    fireEvent.click(await screen.findByRole('button', { name: /deactivate/i }))
    expect(api.deleteUser).not.toHaveBeenCalled()
  })

  it('warns that access goes but the conversations stay', async () => {
    vi.spyOn(api, 'getUsers').mockResolvedValue([ACTIVE] as never)
    render(<Users />)

    fireEvent.click(await screen.findByRole('button', { name: /deactivate/i }))
    const asked = (window.confirm as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(asked).toMatch(/lose access/i)
    expect(asked).toMatch(/conversations are kept/i)
  })
})
