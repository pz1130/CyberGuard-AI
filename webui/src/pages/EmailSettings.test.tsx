import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import EmailSettings from './EmailSettings'

const config = {
  created_subject: 'Review {{request_id}}', created_body: '<p>{{action_description}}</p>',
  decided_subject: 'Decision {{decision}}', decided_body: '<p>{{comment}}</p>',
  template_defaults: { created_subject: 'Review {{request_id}}', created_body: '<p>{{action_description}}</p>', decided_subject: 'Decision {{decision}}', decided_body: '<p>{{comment}}</p>' },
  enabled: true, method: 'smtp', from_email: 'sender@example.org', admin_email: null,
  smtp_host: 'smtp.example.org', smtp_port: 587, smtp_security: 'starttls', smtp_username: 'sender',
  oauth_tenant_id: null, oauth_client_id: null,
  notify_created: true, notify_decided: true, smtp_password_set: true, oauth_client_secret_set: false,
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(api, 'getEmailConfig').mockResolvedValue(config)
  vi.spyOn(api, 'updateEmailConfig').mockResolvedValue(config)
  vi.spyOn(api, 'testEmail').mockResolvedValue({ sent: true })
})

it('preserves saved secrets when left blank and requires saving before a test', async () => {
  render(<EmailSettings />)
  await screen.findByLabelText('Sender mailbox')
  fireEvent.change(screen.getByLabelText('SMTP server'), { target: { value: 'smtp.new.example.org' } })
  expect(screen.getByRole('button', { name: 'Send test email' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Save mailbox settings' }))
  await waitFor(() => expect(api.updateEmailConfig).toHaveBeenCalledWith(expect.objectContaining({
    smtp_host: 'smtp.new.example.org', smtp_password: null, oauth_client_secret: null,
  })))
  await screen.findByText('Mailbox settings saved')
  fireEvent.change(screen.getByLabelText('Test recipient mailbox'), { target: { value: 'receiver@example.org' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send test email' }))
  await waitFor(() => expect(api.testEmail).toHaveBeenCalledWith({ to_email: 'receiver@example.org' }))
})

it('shows Microsoft mailbox fields and keeps the secret out of the displayed settings', async () => {
  render(<EmailSettings />)
  await screen.findByLabelText('Sender mailbox')
  fireEvent.change(screen.getByLabelText('Delivery method'), { target: { value: 'oauth' } })
  expect(screen.getByLabelText('Tenant ID')).toBeTruthy()
  expect(screen.getByLabelText('Client ID')).toBeTruthy()
  expect(screen.getByLabelText('Client secret')).toHaveValue('')
  expect(screen.queryByLabelText('SMTP server')).toBeNull()
})

it('reports delivery failures instead of claiming a test succeeded', async () => {
  vi.spyOn(api, 'testEmail').mockRejectedValue(new Error('Email delivery failed'))
  render(<EmailSettings />)
  await screen.findByLabelText('Sender mailbox')
  fireEvent.change(screen.getByLabelText('Test recipient mailbox'), { target: { value: 'receiver@example.org' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send test email' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Email delivery failed')
})

it('saves custom templates, restores defaults and tests the selected notification', async () => {
  render(<EmailSettings />)
  await screen.findByLabelText('Email subject')
  fireEvent.change(screen.getByLabelText('Email subject'), { target: { value: 'Custom {{request_id}}' } })
  expect(screen.getByText('Custom sample-request-001')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Body (HTML)'), { target: { value: '<h1>{{action_description}}</h1>' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save mailbox settings' }))
  await waitFor(() => expect(api.updateEmailConfig).toHaveBeenCalledWith(expect.objectContaining({
    created_subject: 'Custom {{request_id}}', created_body: '<h1>{{action_description}}</h1>',
  })))
  await screen.findByText('Mailbox settings saved')
  fireEvent.change(screen.getByLabelText('Test email type'), { target: { value: 'created' } })
  fireEvent.change(screen.getByLabelText('Test recipient mailbox'), { target: { value: 'receiver@example.org' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send test email' }))
  await waitFor(() => expect(api.testEmail).toHaveBeenCalledWith({ to_email: 'receiver@example.org', template: 'created' }))
  await screen.findByText('Test email submitted. Check your inbox.')
  fireEvent.change(screen.getByLabelText('Email subject'), { target: { value: 'Modified' } })
  fireEvent.click(screen.getByRole('button', { name: 'Restore current template defaults' }))
  expect(screen.getByLabelText('Email subject')).toHaveValue(config.created_subject)
  expect(screen.getByRole('button', { name: 'Send test email' })).toBeDisabled()
})
