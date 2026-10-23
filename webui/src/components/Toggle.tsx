/**
 * An accessible on/off switch, styled by `.toggle-switch` in index.css.
 *
 * It lived inside Security.tsx until the three controls on that page — encryption,
 * RBAC and audit logging — stopped being switchable, because none of them is a
 * choice the product should offer. Lifted here rather than deleted: the styling
 * and the accessibility work (a real `role="switch"` with `aria-checked`, not a
 * styled div) apply to any toggle the app grows, and deleting them with their
 * first caller would have thrown that away.
 */
export default function Toggle({ enabled, onToggle, label }: {
  enabled: boolean
  onToggle: () => void
  label?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      onClick={onToggle}
      className={`toggle-switch ${enabled ? 'active' : ''}`}
    >
      <span className="toggle-switch-thumb" />
    </button>
  )
}
