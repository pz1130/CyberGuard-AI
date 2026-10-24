# Findings workflow

This feature adds a shared security-team workspace to CyberGuard. It does not
introduce projects or tenant isolation. Anyone granted `finding:read` can read
all findings and their evidence, including exported reports. Only paste evidence
appropriate for that audience. Evidence is stored literally; automatic redaction,
file uploads, URL fetching and automated remediation are outside this first version.

## Workflow

1. An operator/analyst/admin creates a finding in **Findings**, or an internal
   agent calls `finding_submit` on behalf of such a user. Title, target,
   severity, description, remediation and original text evidence are required.
2. A different analyst/approver/admin confirms or rejects it with a note.
3. An operator/analyst/admin assigns a confirmed finding to an active
   operator/analyst/admin. The finding enters **In progress**.
4. The owner (or admin) records progress and requests a retest.
5. An independent analyst/approver/admin records retest evidence and resolves
   the finding, or reopens it. Resolved/rejected findings can also be reopened
   with new evidence. Reopening returns to **Confirmed** for reassignment.
6. Readers can download a Markdown report containing the original submission,
   current state, all evidence, notes, actors, UTC times and audit references.

Reviewers cannot confirm/reject/retest their own submission or a finding they
own for remediation. Admins follow the same independence rule. A single-user
installation therefore needs a second reviewer account to complete this workflow.

| Role | Read/export | Submit | Assign/add evidence/request retest* | Review |
|---|---|---|---|---|
| Admin | Yes | Yes | Yes | Yes |
| Operator | Yes | Yes | Yes | No |
| Analyst | Yes | Yes | Yes | Yes |
| Approver | Yes | No | No | Yes |
| Auditor | Yes | No | No | No |
| Viewer | No | No | No | No |

*Only the assigned owner or admin may request a retest.

## Integrity and concurrency

The submission fields and timeline have no update/delete API. Additional evidence
is appended, with a SHA-256 digest. Each change stores its status/assignment/version
snapshot and a corresponding signed global audit event **in the same database
transaction**. Audit hashes bind the full event payload and finding snapshot.
Audit failure rolls back the change. These are application-level retention
controls; they do not prevent a database administrator from altering tables.

State changes lock the finding row and require the version returned by the last
read. Stale updates receive HTTP 409; reopen the finding to reload before retrying.
The report renders user text in dynamically sized fenced blocks rather than
interpreting it as Markdown or HTML. The UI renders evidence as plain text.

## Integration

- Migration: `048_findings` (requires `047_preserve_audit_actors`).
- API: `/api/v1/findings`, `/{id}`, `/{id}/actions`, `/{id}/report`, `/assignees`.
- Internal agents receive `finding_submit` only for active users with submission
  permission; the grant is checked again at execution time. Existing kill-switch
  and governance hooks run before submission. No review tool is exposed.
- External agents and direct MASTER chat do not gain a submission tool in this
  version. Their output can be recorded manually in Findings.
- This implementation uses CyberGuard's own database, permissions and audit
  infrastructure. No third-party project code or runtime was imported.

Validation: database-backed workflow, RBAC, self-review, stale updates, evidence,
rollback, export and agent tests; UI tests for reviewer controls, literal evidence,
read-only roles and conflict feedback; full `make check` gate.
