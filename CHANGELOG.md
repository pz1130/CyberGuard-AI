# Changelog

## 1.0.0-rc.1 — 2026-09-12

First IFI workgroup release candidate of the Docker reference implementation.

### Included

- Joined AI-for-Security scope covering security operations and GRC.
- WebUI, API, worker, PostgreSQL/pgvector, Redis, and isolated tool-runner in
  Docker Compose.
- Alert triage, vulnerability prioritisation, and GRC assessment demo paths.
- Structured tool risk and confidence decisions, human approval with
  suspend/resume, RBAC, kill switch, rollback registration, PII and egress
  controls, and tamper-evident audit events.
- Authenticated encryption for stored credentials and explicit secure admin
  bootstrap with no built-in password.
- Disposable integration-test stack, CI gate, delivery runbook, evaluation
  framework, responsible-AI statement, architecture, and operations guidance.

### Removed from the release surface

- Desktop application and desktop-only documentation.
- Kubernetes deployment manifests.
- Group-chat rooms, N8N management, user-defined scheduled jobs, webhooks, and
  Flower monitoring.

Historical migrations for removed modules remain so an existing database can
be upgraded safely. They do not expose API routes or WebUI pages.

### Known limitations

- Model/provider performance must be measured with the frozen evaluation set;
  no accuracy claim is made by this candidate.
- Operators must provide TLS termination, host/network hardening, monitoring,
  external secret management, backup custody, and provider governance.
- The audit hash chain is tamper-evident application storage, not independent
  WORM retention.
- A deployment-specific security reporting contact is required before public
  release.
