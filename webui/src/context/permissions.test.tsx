import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PermissionButton } from '../components/PermissionButton'
import SidebarNew from '../components/SidebarNew'
import { RoleContext, canAccessTab } from './permissions'

describe('role visibility', () => {
  it('hides administration and mutation controls from viewers', () => {
    render(<RoleContext.Provider value="viewer">
      <SidebarNew tab="agents" setTab={() => {}} />
      <PermissionButton permission="agent:write">Create agent</PermissionButton>
    </RoleContext.Provider>)
    expect(screen.getByRole('button', { name: /^sub-agent$/i })).toBeInTheDocument()
    expect(screen.queryByText('Create agent')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /user management/i })).not.toBeInTheDocument()
    expect(canAccessTab('viewer', 'security')).toBe(false)
    expect(canAccessTab('auditor', 'audit')).toBe(true)
    expect(canAccessTab('approver', 'approvals')).toBe(true)
    expect(canAccessTab('unknown', 'users')).toBe(false)
  })
})
