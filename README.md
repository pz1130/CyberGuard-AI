# CyberGuard

CyberGuard is a Docker-based reference implementation for governed AI in
cybersecurity operations. It is prepared as an IFI workgroup
deliverable: demonstrable, inspectable, and explicit about where a human must
remain in control.

## Release scope

The release candidate supports two end-to-end paths:

1. **Security alert triage** — investigate alerts with agents, knowledge, and
   approved tools; retain the evidence and audit trail.
2. **Vulnerability prioritisation** — assess technical and business impact,
   propose remediation, and gate higher-risk actions on human approval.
Included capabilities:

- Master Agent plus internal or explicitly configured external agents
- LLM provider routing, prompt templates, skills, governed tools, and MCP
- Knowledge bases, document ingestion, pgvector retrieval, and OCR
- RBAC, optional Entra ID SSO, human approval, kill switch, audit chain, PII
  handling, egress controls, encrypted credentials, token usage, and backup
- React WebUI, FastAPI API, Celery worker, PostgreSQL/pgvector, Redis, and an
  isolated tool-runner, all deployed with Docker Compose

Out of scope for this release: GRC framework/assessment management, desktop
clients, Kubernetes, group-chat rooms, N8N workflow generation,
user-configurable scheduled jobs, and webhooks.
Historical migrations keep legacy tables readable during upgrades, but those
features have no API or UI surface in this release.

## Architecture

```text
Browser ──> WebUI ──> FastAPI ──> PostgreSQL + pgvector
                         │  └────> Redis
                         ├───────> Celery worker
                         ├───────> isolated tool-runner
                         └───────> configured LLM / MCP endpoints
```

High-risk tool use is evaluated before execution. Depending on policy and
confidence, the request is denied, sent for human approval, or executed with an
audit event. AI output is advisory unless an authorised tool path is used.

## Docker quick start

Prerequisites: Docker Engine with Docker Compose v2.

```bash
cp .env.example .env
```

Edit `.env` and replace every `replace-with-...` value. In particular, set
unique `ENCRYPTION_KEY`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`,
`RUNNER_TOKEN`, and `BOOTSTRAP_ADMIN_PASSWORD` values. Generate the two
application keys with:

```bash
python -c 'import secrets; print(secrets.token_hex(32)); print(secrets.token_hex(32))'
```

Then start the release:

```bash
docker compose config --quiet
docker compose build
docker compose up -d
```

Compose runs database migrations as a one-shot service before starting the API
and workers.

Open `http://localhost:3000` and sign in with `BOOTSTRAP_ADMIN_USERNAME` and
`BOOTSTRAP_ADMIN_PASSWORD`. The bootstrap user is created only when the
database has no user with that name; CyberGuard contains no built-in password.

Check service health:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
```

Stop the stack without deleting data:

```bash
docker compose down
```

## Verification

Install developer dependencies once:

```bash
uv sync --extra test
npm --prefix webui ci
```

Run the release gate:

```bash
make check
```

The test target creates disposable PostgreSQL/pgvector and Redis services on
loopback ports 55432 and 56379, applies every migration, runs the Python suite,
and removes the test volumes. It never uses the configured development or
release database.

Additional checks:

```bash
make docker-config
make docker-build
make security-scan
make sbom
```

The scan gate rejects known, fixed critical vulnerabilities. CycloneDX SBOMs
are written to `artifacts/` for release evidence.

## Delivery documentation

- [Release scope and acceptance](docs/delivery/RELEASE_CANDIDATE.md)
- [RC verification evidence](docs/delivery/RC_EVIDENCE.md)
- [Demonstration runbook](docs/delivery/DEMO_RUNBOOK.md)
- [Evaluation framework](docs/delivery/EVALUATION.md)
- [Architecture and security](docs/delivery/ARCHITECTURE_AND_SECURITY.md)
- [Responsible AI statement](docs/delivery/RESPONSIBLE_AI.md)
- [Operations guide](docs/delivery/OPERATIONS.md)
- [Security policy](SECURITY.md)

## Limitations

- This is a reference implementation, not a security certification or a claim
  that a deployment is production-ready without local risk assessment.
- LLM conclusions may be incomplete or wrong. Evidence and high-impact actions
  require human review.
- External LLM and MCP data handling is governed by the operator's selected
  providers and network policy.
- Runtime governance controls do not constitute legal, regulatory, or audit
  advice.

## License

MIT. See [LICENSE](LICENSE).
