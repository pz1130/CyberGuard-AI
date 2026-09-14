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
- Provider-bound Master Agent model selection with server-side validation.
  AUTO uses the saved Provider+Model pair; a model name is never sent to a
  different provider. Session-level model-name override was removed.
- Dependency floors for cryptography, starlette, python-multipart, Pillow,
  pypdf, httpx2, and httpcore2. Container scan gate is High and Critical;
  rebuilt images scan clean with `--ignore-unfixed`.
- Collapsed rendering for provider `<think>` and `<reasoning>` output in chat.
- Disposable integration-test stack, CI gate, delivery runbook, evaluation
  framework, responsible-AI statement, architecture, and operations guidance.
- Release images run as non-root (uid 10001 / nginx 101). Compose drops all
  capabilities, sets `no-new-privileges:true`, and uses a read-only rootfs
  for application services.
- HTTP audit middleware is fail-closed for ordinary requests: a `log_audit`
  flush error propagates instead of returning a successful handler response
  with no durable audit row. Health probes stay exempt.
- Frontend tests are in the typecheck and ESLint gates (`tsconfig.test.json`;
  eslint no longer ignores `*.test.ts(x)`).

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
- The private repository still needs a real, tested internal vulnerability
  reporting channel (see SECURITY.md). RC technical acceptance is recorded in
  RC_EVIDENCE.md; final `v1.0.0` acceptance also waits on the Linux AMD64
  source-build run and the immutable tagged source-package checksum.
