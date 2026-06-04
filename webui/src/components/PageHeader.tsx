import React from 'react'

interface PageHeaderProps {
  eyebrow: string
  title: string
  description?: string
  /** Right side actions (buttons etc.) */
  actions?: React.ReactNode
  style?: React.CSSProperties
}

export default function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  style,
}: PageHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 24,
        ...style,
      }}
    >
      <div>
        <div
          style={{
            fontSize: 11,
            letterSpacing: '0.08em',
            color: 'var(--text-dim)',
            marginBottom: 6,
          }}
        >
          {eyebrow}
        </div>
        <h1
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '0.1em',
            color: 'var(--text-primary)',
            margin: 0,
          }}
        >
          {title}
        </h1>
        {description && (
          <div
            style={{
              fontSize: 12,
              letterSpacing: '0.1em',
              color: 'var(--text-dim)',
              marginTop: 4,
            }}
          >
            {description}
          </div>
        )}
      </div>
      {actions && (
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>{actions}</div>
      )}
    </div>
  )
}
