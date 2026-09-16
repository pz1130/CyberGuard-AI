import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import ChangePasswordDialog from './ChangePasswordDialog'

describe('ChangePasswordDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  const fill = (current: string, next: string, confirm: string) => {
    fireEvent.change(screen.getByLabelText(/current password/i), { target: { value: current } })
    fireEvent.change(screen.getByLabelText(/^new password/i), { target: { value: next } })
    fireEvent.change(screen.getByLabelText(/confirm new password/i), { target: { value: confirm } })
  }

  const submitButton = () =>
    screen.getAllByRole('button', { name: /change password/i }).slice(-1)[0]

  it('will not submit until the new password is long enough', () => {
    render(<ChangePasswordDialog onClose={() => {}} />)
    fill('old', 'short', 'short')
    expect((submitButton() as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/at least 8 characters/i)).toBeTruthy()
  })

  it('will not submit when the two new entries differ', () => {
    render(<ChangePasswordDialog onClose={() => {}} />)
    fill('old', 'Str0ng-Pass-123', 'Str0ng-Pass-124')
    expect((submitButton() as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/do not match/i)).toBeTruthy()
  })

  it('will not submit without the current password', () => {
    render(<ChangePasswordDialog onClose={() => {}} />)
    fill('', 'Str0ng-Pass-123', 'Str0ng-Pass-123')
    expect((submitButton() as HTMLButtonElement).disabled).toBe(true)
  })

  it('sends the change and reports how many sessions were signed out', async () => {
    vi.spyOn(api, 'changePassword').mockResolvedValue({ other_sessions_ended: 2 } as never)
    render(<ChangePasswordDialog onClose={() => {}} />)
    fill('Original-1', 'Str0ng-Pass-123', 'Str0ng-Pass-123')
    fireEvent.click(submitButton())

    await waitFor(() => expect(api.changePassword).toHaveBeenCalledWith({
      old_password: 'Original-1', new_password: 'Str0ng-Pass-123',
    }))
    expect(await screen.findByText(/2 other session/i)).toBeTruthy()
  })

  it('shows the server error when the current password is wrong', async () => {
    vi.spyOn(api, 'changePassword').mockRejectedValue(
      new Error('Current password is incorrect'))
    render(<ChangePasswordDialog onClose={() => {}} />)
    fill('wrong', 'Str0ng-Pass-123', 'Str0ng-Pass-123')
    fireEvent.click(submitButton())

    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toMatch(/incorrect/i)
  })
})
