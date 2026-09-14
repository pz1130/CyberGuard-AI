import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { bootTheme } from './theme'

const getAuthMe = vi.fn()
const getSsoStatus = vi.fn()
const getBranding = vi.fn()

vi.mock('./api/client', () => ({
  api: {
    getAuthMe: (...args: unknown[]) => getAuthMe(...args),
    getSsoStatus: (...args: unknown[]) => getSsoStatus(...args),
    getBranding: (...args: unknown[]) => getBranding(...args),
  },
}))

describe('App theme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    getAuthMe.mockReset()
    getSsoStatus.mockReset().mockResolvedValue({ enabled: false })
    getBranding.mockReset().mockResolvedValue({})
  })

  it('does not mutate the document element during render', async () => {
    localStorage.setItem('theme', 'light')
    const { default: App } = await import('./App')
    render(<App />)
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
    expect(await screen.findByRole('button', { name: /authenticate/i })).toBeInTheDocument()
  })

  it('bootTheme applies the stored light theme before React render', async () => {
    localStorage.setItem('theme', 'light')
    bootTheme()
    const { default: App } = await import('./App')
    render(<App />)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(await screen.findByRole('button', { name: /authenticate/i })).toBeInTheDocument()
  })
})
