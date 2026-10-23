# Approval permissions and email notifications

Administrators can assign the **Approver / 审批员** role in Users, including
SSO role mappings. It grants `approval:read` and `approval:decide`: reviewing,
approving, and rejecting requests, without user administration, agent execution,
or system settings access. Administrators retain both permissions. Other roles
cannot use approval list, detail, decision, status or SSE endpoints. Decisions
record an `approval.decide` audit event whose `human_reviewer` is the deciding
user's ID. Like every audit event, it stores the request ID and decision only as
`input_hash`, so the audit log alone does not show the outcome; the approval
request itself keeps `status`, `approver_id`, `approver_comment` and `decided_at`.

Under **Settings → Email notifications**, an administrator can enable delivery,
choose SMTP or Microsoft 365 OAuth, and toggle pending/decision notifications.
Pending requests notify active admin/approver users and the optional additional
mailbox. Decisions notify the requester at their user account email.

SMTP supports STARTTLS (typically 587), implicit SSL/TLS (typically 465), and
plain internal relays. Username/password authentication is optional for relays.
Passwords and OAuth secrets are encrypted with the existing AES-GCM credential
store. Configuration responses expose only whether a credential is saved.
Blank secret fields preserve saved credentials; explicit clear checkboxes remove
them. Saved settings take precedence over legacy `SMTP_*` environment variables,
including when disabled. Until settings are saved, the environment remains the
fallback. Both API and worker processes load the shared database configuration.

Microsoft 365 OAuth uses the client credentials grant and Microsoft Graph:

1. Register an application in your organization's Microsoft Entra tenant.
2. Add Microsoft Graph **Mail.Send**, under **Application permissions**, and
   grant tenant administrator consent.
3. Create a client secret; enter its **value**, tenant ID and client ID.
4. Enter the organizational sender mailbox address, save, and send a test email
   to a supplied recipient. The sender must have an Exchange Online mailbox.

This is app-only organizational mail, not delegated login or personal Outlook.com
mail. Graph endpoints use the Microsoft public cloud. See Microsoft's
[client credentials documentation](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
and [sendMail API](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0).

Admin APIs: `GET/PUT /api/v1/email/config`, `POST /api/v1/email/test` with
`{"to_email":"recipient@example.org"}`. Test failures return 502; success means
the service accepted the request, not confirmed inbox delivery. The settings
must be saved before testing in the UI. Notifications are best-effort; delivery
failure does not change the approval decision and is logged without credentials
or token responses. There is no delivery retry queue.

## Custom templates

In the same settings page, edit the subject and HTML body separately for pending
approvals and decisions. Templates are saved with the mailbox configuration in
`email_config.config_json`, shared by API and workers. Existing saved mailboxes
receive defaults automatically. Restoring defaults affects the selected template
in the editor; save to apply it. The sample preview updates while editing and
runs in a sandbox without scripts or external resources. Select a notification
type in the test email form to send its saved template with sample values.

Variables use `{{name}}` (optional surrounding whitespace is allowed):

| Notification | Variables |
|---|---|
| Pending approval | `request_id`, `action_description`, `risk_level`, `user_id` |
| Decision | `request_id`, `decision`, `comment` |

Subjects cannot contain line breaks. Variable values in subjects have line breaks
replaced with spaces, and HTML body values are escaped. Risk levels and decisions
are uppercase. Unknown variables, empty templates and expressions are rejected
on save. No template code execution is supported. The subject is limited to 255
characters and body to 50,000. API fields: `created_subject`, `created_body`,
`decided_subject`, `decided_body`. `/email/test` additionally accepts `template`
(`connection`, `created`, `decided`; default `connection`).
