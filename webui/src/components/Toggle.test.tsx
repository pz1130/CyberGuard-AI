import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import Toggle from './Toggle'

/**
 * It has no caller yet — the page it came from no longer needs a switch. These
 * pin the behaviour that made it worth keeping, so the next page to adopt it
 * gets a working component rather than an untested leftover.
 */
describe('Toggle', () => {
  it('exposes itself as a switch with its state readable', () => {
    render(<Toggle enabled onToggle={() => {}} label="Audit logging" />)
    const el = screen.getByRole('switch', { name: 'Audit logging' })
    expect(el.getAttribute('aria-checked')).toBe('true')
  })

  it('reports the off state too', () => {
    render(<Toggle enabled={false} onToggle={() => {}} label="Audit logging" />)
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false')
  })

  it('calls back when clicked', () => {
    const onToggle = vi.fn()
    render(<Toggle enabled={false} onToggle={onToggle} />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('carries the active class only when on, which is what index.css styles', () => {
    const { rerender } = render(<Toggle enabled={false} onToggle={() => {}} />)
    expect(screen.getByRole('switch').className).not.toContain('active')
    rerender(<Toggle enabled onToggle={() => {}} />)
    expect(screen.getByRole('switch').className).toContain('active')
  })

  it('is a real button, so it does not submit a surrounding form', () => {
    render(<Toggle enabled onToggle={() => {}} />)
    expect(screen.getByRole('switch').getAttribute('type')).toBe('button')
  })
})
