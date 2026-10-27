import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { RoleContext } from '../context/permissions'
import Findings from './Findings'

const finding = { id: 7, title: 'Response encoding', target: 'test.example', severity: 'high', status: 'pending',
  description: 'Raw input reflected', remediation: 'Encode input', created_by: 1, assignee_id: null, version: 1, source: 'agent',
  independent_reviewer: true,
  events: [{ id: 1, actor_id: 1, action: 'submit', note: 'Observation', evidence: '<script>alert(1)</script>', evidence_hash: 'abc', created_at: '2026-10-24T00:00:00' }] }

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'getFindings').mockResolvedValue({ items: [finding], total: 1 })
  vi.spyOn(api, 'getFinding').mockResolvedValue(finding)
  vi.spyOn(api, 'getFindingAssignees').mockResolvedValue([{ id: 1, username: 'owner' }])
  vi.spyOn(api, 'getAuthMe').mockResolvedValue({ user_id: 2 })
  vi.spyOn(api, 'changeFinding').mockResolvedValue({ ...finding, status: 'confirmed', version: 2 })
  vi.spyOn(api, 'createFinding').mockResolvedValue(finding)
})

it('allows an independent reviewer to confirm with the current version and preserves literal evidence', async () => {
  render(<RoleContext.Provider value="analyst"><Findings /></RoleContext.Provider>)
  fireEvent.click(await screen.findByRole('button', { name: '#7 Response encoding' }))
  const confirm = await screen.findByRole('button', { name: 'Confirm' })
  expect(confirm).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Review / progress note'), { target: { value: 'Reproduced independently' } })
  fireEvent.click(confirm)
  await waitFor(() => expect(api.changeFinding).toHaveBeenCalledWith(7, expect.objectContaining({ action: 'confirm', version: 1, note: 'Reproduced independently' })))
  expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
  expect(document.querySelector('.findings-event script')).toBeNull()
})

it('keeps audit readers read-only', async () => {
  render(<RoleContext.Provider value="auditor"><Findings /></RoleContext.Provider>)
  fireEvent.click(await screen.findByRole('button', { name: '#7 Response encoding' }))
  await screen.findByRole('button', { name: 'Export Markdown' })
  expect(screen.queryByRole('button', { name: 'New finding' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull()
  expect(screen.queryByLabelText('Review / progress note')).toBeNull()
})

it('does not show self-review controls', async () => {
  vi.spyOn(api, 'getFinding').mockResolvedValue({ ...finding, independent_reviewer: false })
  render(<RoleContext.Provider value="analyst"><Findings /></RoleContext.Provider>)
  fireEvent.click(await screen.findByRole('button', { name: '#7 Response encoding' }))
  await screen.findByText('An independent reviewer must confirm and retest this finding.')
  expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull()
})

it('requires retest evidence and reports a conflict without claiming success', async () => {
  vi.spyOn(api, 'getFinding').mockResolvedValue({ ...finding, status: 'ready_for_retest', assignee_id: 1 })
  vi.spyOn(api, 'changeFinding').mockRejectedValue(new Error('Finding changed; reload before submitting'))
  render(<RoleContext.Provider value="approver"><Findings /></RoleContext.Provider>)
  fireEvent.click(await screen.findByRole('button', { name: '#7 Response encoding' }))
  const resolve = await screen.findByRole('button', { name: 'Retest passed' })
  fireEvent.change(screen.getByLabelText('Review / progress note'), { target: { value: 'Checked' } })
  expect(resolve).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Original evidence / retest evidence'), { target: { value: 'Encoded response' } })
  fireEvent.click(resolve)
  expect(await screen.findByRole('alert')).toHaveTextContent('Finding changed')
})

it('hides retest sign-off from a former owner the server marks as not independent', async () => {
  // user 2 is neither creator nor current owner, but owned the fix earlier.
  vi.spyOn(api, 'getFinding').mockResolvedValue({ ...finding, status: 'ready_for_retest', assignee_id: 3, independent_reviewer: false })
  render(<RoleContext.Provider value="analyst"><Findings /></RoleContext.Provider>)
  fireEvent.click(await screen.findByRole('button', { name: '#7 Response encoding' }))
  await screen.findByText('An independent reviewer must confirm and retest this finding.')
  expect(screen.queryByRole('button', { name: 'Retest passed' })).toBeNull()
})
