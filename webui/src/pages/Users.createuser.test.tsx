import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import Users from './Users'

/**
 * There was no way to create a user.
 *
 * POST /users worked, and the form component had a CREATE USER branch, but
 * `openForm` was only ever called as `openForm(u)` from a row's edit button —
 * nothing called it with no argument, so the create branch was unreachable.
 * The `users.addUser` translation existed in both languages, unused: the
 * button had been designed and never wired.
 */
describe('Users — creating a local account', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getUsers').mockResolvedValue([] as never)
    vi.spyOn(api, 'getSsoConfig').mockResolvedValue({} as never)
    vi.spyOn(api, 'getSsoRoleMappings').mockResolvedValue([] as never)
    vi.spyOn(api, 'getSecretEnvVars').mockResolvedValue([] as never)
    vi.spyOn(api, 'createUser').mockResolvedValue({ id: 9 } as never)
  })

  const openCreateForm = async () => {
    render(<Users />)
    const button = await screen.findByRole('button', { name: /add user/i })
    fireEvent.click(button)
  }

  it('offers a way to start creating one', async () => {
    await openCreateForm()
    // Header and submit button both read CREATE USER; either proves the form
    // opened in create mode rather than edit mode.
    expect(screen.getAllByText('CREATE USER').length).toBeGreaterThan(0)
    expect(screen.queryByText('UPDATE USER')).toBeNull()
  })

  it('submits the new account to the API', async () => {
    await openCreateForm()

    fireEvent.change(screen.getByLabelText(/username/i),
      { target: { value: 'newanalyst' } })
    fireEvent.change(screen.getByLabelText(/^email/i),
      { target: { value: 'ops@company.local' } })
    fireEvent.change(screen.getByLabelText(/^password/i),
      { target: { value: 'Str0ng-Pass-123' } })
    fireEvent.click(screen.getByRole('button', { name: /create user/i }))

    await waitFor(() => expect(api.createUser).toHaveBeenCalledTimes(1))
    expect(api.createUser).toHaveBeenCalledWith(expect.objectContaining({
      username: 'newanalyst',
      email: 'ops@company.local',
      password: 'Str0ng-Pass-123',
    }))
  })

  it('starts from a blank form rather than the last edited user', async () => {
    await openCreateForm()
    expect((screen.getByLabelText(/username/i) as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText(/^email/i) as HTMLInputElement).value).toBe('')
  })
})
