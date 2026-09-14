import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Login from './Login'

const login = vi.fn()
const getSsoStatus = vi.fn()
const getBranding = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    login: (...args: unknown[]) => login(...args),
    getSsoStatus: (...args: unknown[]) => getSsoStatus(...args),
    getBranding: (...args: unknown[]) => getBranding(...args),
  },
}))

describe('Login', () => {
  beforeEach(() => {
    localStorage.clear()
    login.mockReset()
    getSsoStatus.mockReset().mockResolvedValue({ enabled: false })
    getBranding.mockReset().mockResolvedValue({})
    vi.stubGlobal('location', {
      ...window.location,
      reload: vi.fn(),
      search: '',
      hash: '',
      pathname: '/',
    })
  })

  it('stores the access token after a successful login', async () => {
    const user = userEvent.setup()
    login.mockResolvedValue({ access_token: 'jwt-from-login' })
    render(<Login />)

    await user.type(screen.getByPlaceholderText('operator'), 'admin')
    await user.type(screen.getByPlaceholderText('••••••••'), 'secret-pass')
    await user.click(screen.getByRole('button', { name: /authenticate/i }))

    expect(login).toHaveBeenCalledWith({ username: 'admin', password: 'secret-pass' })
    expect(localStorage.getItem('token')).toBe('jwt-from-login')
    expect(window.location.reload).toHaveBeenCalled()
  })

  it('shows an auth failure without storing a token', async () => {
    const user = userEvent.setup()
    login.mockRejectedValue(new Error('401'))
    render(<Login />)

    await user.type(screen.getByPlaceholderText('operator'), 'admin')
    await user.type(screen.getByPlaceholderText('••••••••'), 'wrong')
    await user.click(screen.getByRole('button', { name: /authenticate/i }))

    expect(await screen.findByText(/authentication failed/i)).toBeInTheDocument()
    expect(localStorage.getItem('token')).toBeNull()
  })
})
