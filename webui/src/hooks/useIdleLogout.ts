import { useEffect, useRef } from 'react'
import { api } from '../api/client'

/**
 * Report real user activity so the server can end an idle session.
 *
 * The server holds the timer; this only tells it when a human did something.
 * That distinction is the whole feature: the UI polls several endpoints on
 * timers, so a window extended by any request would never close.
 *
 * A heartbeat is sent at most once per THROTTLE_MS no matter how much the user
 * moves around, and only when a token is present.
 */
const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'touchstart', 'scroll'] as const
const THROTTLE_MS = 60_000

export function useIdleLogout(): void {
  const lastSent = useRef(0)

  useEffect(() => {
    let cancelled = false

    const beat = () => {
      if (cancelled) return
      if (!localStorage.getItem('token')) return
      const now = Date.now()
      if (now - lastSent.current < THROTTLE_MS) return
      lastSent.current = now
      // A rejected heartbeat means the session already lapsed; the shared
      // request helper turns that 401 into a redirect, so nothing to do here.
      void api.heartbeat().catch(() => {})
    }

    for (const name of ACTIVITY_EVENTS) {
      window.addEventListener(name, beat, { passive: true })
    }
    // One beat on mount so a freshly loaded tab counts as activity.
    beat()

    return () => {
      cancelled = true
      for (const name of ACTIVITY_EVENTS) {
        window.removeEventListener(name, beat)
      }
    }
  }, [])
}
