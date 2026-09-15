import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { useIdleLogout } from './useIdleLogout'

describe('useIdleLogout', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.setItem('token', 'a-token')
    vi.spyOn(api, 'heartbeat').mockResolvedValue(null)
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('reports that the tab is in use as soon as it mounts', () => {
    renderHook(() => useIdleLogout())
    expect(api.heartbeat).toHaveBeenCalledTimes(1)
  })

  it('throttles a burst of activity into one heartbeat', () => {
    renderHook(() => useIdleLogout())
    ;(api.heartbeat as ReturnType<typeof vi.fn>).mockClear()

    for (let i = 0; i < 50; i++) window.dispatchEvent(new Event('keydown'))
    expect(api.heartbeat).toHaveBeenCalledTimes(0)
  })

  it('reports again once the throttle window has passed', () => {
    renderHook(() => useIdleLogout())
    ;(api.heartbeat as ReturnType<typeof vi.fn>).mockClear()

    vi.setSystemTime(Date.now() + 61_000)
    window.dispatchEvent(new Event('keydown'))
    expect(api.heartbeat).toHaveBeenCalledTimes(1)
  })

  it('stays quiet when nobody is signed in', () => {
    localStorage.removeItem('token')
    renderHook(() => useIdleLogout())
    window.dispatchEvent(new Event('keydown'))
    expect(api.heartbeat).toHaveBeenCalledTimes(0)
  })

  it('stops listening once unmounted', () => {
    const { unmount } = renderHook(() => useIdleLogout())
    ;(api.heartbeat as ReturnType<typeof vi.fn>).mockClear()
    unmount()

    vi.setSystemTime(Date.now() + 61_000)
    window.dispatchEvent(new Event('keydown'))
    expect(api.heartbeat).toHaveBeenCalledTimes(0)
  })
})
