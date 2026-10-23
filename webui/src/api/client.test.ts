import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

describe('expired sessions', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); vi.unstubAllGlobals() })
  it('clears credentials and notifies the app when a JSON request expires', async () => {
    localStorage.setItem('token', 'expired')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })))
    const expired = vi.fn()
    window.addEventListener('cyberguard:session-expired', expired)
    await expect(api.getSkills()).rejects.toThrow(/session expired/i)
    expect(expired).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('sessionExpired')).toBe('1')
    window.removeEventListener('cyberguard:session-expired', expired)
  })
  it('also handles expiry on streaming and multipart requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })))
    await expect(api.chatStream({ message: 'hello' }).next()).rejects.toThrow(/session expired/i)
    await expect(api.importSkillFile(new FormData())).rejects.toThrow(/session expired/i)
  })
})
