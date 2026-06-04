import { useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface ModalProps {
  /** Main title shown in the header (rendered as-is, callers decide casing). */
  title: string
  /** Optional small uppercase label above the title. */
  eyebrow?: string
  /** Called when the user dismisses the modal (X, overlay click, or Escape). */
  onClose: () => void
  children: ReactNode
  /** Optional footer area (typically the action buttons). */
  footer?: ReactNode
  /** Container width. Number → px. Defaults to 560. */
  width?: number | string
  /** Set false to disable closing by clicking the backdrop. Defaults to true. */
  closeOnOverlay?: boolean
}

/**
 * Unified modal chrome (overlay + container + header + body + footer).
 * Uses the design-system .modal-* classes so every dialog shares the same
 * backdrop opacity, z-index, radius, shadow and animation.
 */
export default function Modal({
  title,
  eyebrow,
  onClose,
  children,
  footer,
  width = 560,
  closeOnOverlay = true,
}: ModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="modal-overlay"
      onClick={closeOnOverlay ? (e => { if (e.target === e.currentTarget) onClose() }) : undefined}
    >
      <div className="modal-container" style={{ width, maxWidth: '100%' }}>
        <div className="modal-header">
          <div>
            {eyebrow && <div className="modal-eyebrow">{eyebrow}</div>}
            <span className="modal-header-title">{title}</span>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}
