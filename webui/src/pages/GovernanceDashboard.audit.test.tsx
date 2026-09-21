import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GovernanceDashboard from './GovernanceDashboard'
import { RoleContext } from '../context/permissions'

const verifyAudit = vi.fn()
const getAuditEvidence = vi.fn()
vi.mock('../api/client', () => ({ api: {
  getGovernanceMetrics: async () => ({ metrics: [], all_pass: false }),
  getHaltStatus: async () => ({ global: false }), getRollbacks: async () => [],
  getApprovals: async () => [], verifyAudit: () => verifyAudit(),
  getAuditEvidence: () => getAuditEvidence(),
}}))
const broken = {
  status: 'broken', fully_verified: false, first_broken_row_id: 13540,
  total_rows: 100, verified_rows: 49, payload_mismatches: 51, link_mismatches: 0,
  unsigned_rows: 0, legacy_rows: 0, unsupported_rows: 0,
  affected_rows: 51, issues_truncated: false,
  issues: [{ row_id: 13540, action: 'user.password_changed', reasons: ['payload_mismatch'] }],
}
function show() {
  render(<RoleContext.Provider value="admin"><GovernanceDashboard /></RoleContext.Provider>)
}
describe('audit integrity diagnostics', () => {
  beforeEach(() => {
    verifyAudit.mockReset().mockResolvedValue(broken)
    getAuditEvidence.mockReset().mockResolvedValue({ status: 'not_configured' })
  })
  it('shows content failures separately from chain links and blocks verified export', async () => {
    show()
    expect(await screen.findByText('First anomaly: record 13540')).toBeInTheDocument()
    expect(screen.getByText(/Content mismatches: 51 · Broken links: 0/)).toBeInTheDocument()
    expect(screen.getByText('Record content differs from its stored hash')).toBeInTheDocument()
    expect(screen.getByText('External storage not configured')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Archive verified records' })).toBeDisabled()
  })
  it('clears a previous success when the next integrity request fails', async () => {
    verifyAudit.mockResolvedValueOnce({ ...broken, status: 'verified', fully_verified: true, issues: [], first_broken_row_id: null })
    show()
    await screen.findByText('Local hashes consistent')
    verifyAudit.mockRejectedValue(new Error('unavailable'))
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }))
    await screen.findByText('Audit check unavailable')
    expect(screen.queryByText('Local hashes consistent')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Archive verified records' })).toBeDisabled())
  })
  it('does not mark legacy or unsigned coverage as fully verified', async () => {
    verifyAudit.mockResolvedValue({ ...broken, status: 'partial', fully_verified: false, unsigned_rows: 5, legacy_rows: 3, issues: [], first_broken_row_id: null })
    show()
    expect(await screen.findByText('Only partially verifiable')).toBeInTheDocument()
    expect(screen.getByText('Unsigned: 5 · Legacy: 3 · Unsupported version: 0')).toBeInTheDocument()
  })
})
