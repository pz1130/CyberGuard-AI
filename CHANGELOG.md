# Changelog

## 1.0.0-rc.1 — 2026-09-12

First IFI workgroup release candidate of the Docker reference implementation.

### Included

- Focused AI-for-Security scope covering governed security operations.
- WebUI, API, worker, PostgreSQL/pgvector, Redis, and isolated tool-runner in
  Docker Compose.
- Alert triage and vulnerability-prioritisation demo paths.
- Structured tool risk and confidence decisions, human approval with
  suspend/resume, RBAC, kill switch, rollback registration, PII and egress
  controls, and tamper-evident audit events.
- Authenticated encryption for stored credentials and explicit secure admin
  bootstrap with no built-in password.
- Provider-reported token accounting for standard, streaming, and embedding
  calls, with administrator-configured per-model cost estimates.
- Durable PostgreSQL LangGraph checkpoints for task execution and approval
  resume across API and worker processes.
- Provider-bound Master Agent model selection with server-side validation and
  deterministic fallback that excludes providers without credentials.
- Collapsed rendering for provider `<think>` and `<reasoning>` output in chat.
- Disposable integration-test stack, CI gate, delivery runbook, evaluation
  framework, responsible-AI statement, architecture, and operations guidance.

### Removed from the release surface

- Desktop application and desktop-only documentation.
- Kubernetes deployment manifests.
- GRC framework/assessment management, group-chat rooms, N8N management,
  user-defined scheduled jobs, webhooks, and Flower monitoring.

Historical migrations remain for upgrade continuity. Migration 033 removes
the duplicated GRC tables; export any required GRC records before upgrading.
Removed modules expose no API routes or WebUI pages.

### Known limitations

- Model/provider performance must be measured with the frozen evaluation set;
  no accuracy claim is made by this candidate.
- Operators must provide TLS termination, host/network hardening, monitoring,
  external secret management, backup custody, and provider governance.
- The audit hash chain is tamper-evident application storage, not independent
  WORM retention.
- A deployment-specific security reporting contact is required before public
  release.
