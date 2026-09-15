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

The delivery is a source archive. Operators build all Docker images locally;
no container registry is required. The formal deployment target is a Linux
AMD64 host with Docker Engine and Docker Compose v2. Apple Silicon/ARM64 is
useful for local evaluation but is not the workgroup acceptance platform.

```bash
cp .env.example .env
```

Edit `.env` and replace every `replace-with-...` value. In particular, set
unique `ENCRYPTION_KEY`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`,
`RUNNER_TOKEN`, `SKILL_RUNNER_TOKEN`, `EGRESS_PROXY_TOKEN`, and
`BOOTSTRAP_ADMIN_PASSWORD` values. `SKILL_RUNNER_TOKEN` and `EGRESS_PROXY_TOKEN`
must each differ from `RUNNER_TOKEN` and from one another — keeping them separate
is what bounds what a sandboxed script can reach. Generate the two
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

### First administrator

There is **no default login**. Compose refuses to start until
`BOOTSTRAP_ADMIN_PASSWORD` is set in `.env`. CyberGuard never ships a
built-in password.

On the first API start, if the database has no user named
`BOOTSTRAP_ADMIN_USERNAME`, it creates that administrator. Later restarts do
not reset the password.

| Variable | `.env.example` | What to do |
|---|---|---|
| `BOOTSTRAP_ADMIN_USERNAME` | `admin` | Keep this, or change it before the first start |
| `BOOTSTRAP_ADMIN_EMAIL` | `admin@example.org` | Change if you want |
| `BOOTSTRAP_ADMIN_PASSWORD` | placeholder only | **Required.** Set your own value |

Generate a one-time password:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(18))'
```

Open `http://localhost:3000` and sign in with that username and password.
Change the password after the first login. If you skip
`BOOTSTRAP_ADMIN_PASSWORD`, the stack will not start; if the username already
exists, bootstrap does nothing.

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

Run the application test gate:

```bash
make check
```

The test target creates disposable PostgreSQL/pgvector and Redis services on
loopback ports 55432 and 56379, applies every migration, runs the Python suite,
and removes the test volumes. It never uses the configured development or
release database.

Additional checks:

```bash
make rc-check
```

The full RC gate also validates Compose, builds the three images, rejects
known fixed High/Critical vulnerabilities, and writes CycloneDX SBOMs under
`artifacts/`. The GitHub release gate additionally starts the source-built
stack on AMD64 and runs authenticated API smoke tests.

After acceptance and creation of an immutable tag, build the source delivery
archive with:

```bash
make source-package VERSION=1.0.0-rc.1 REF=v1.0.0-rc.1
```

This writes the archive, its SHA-256 file, and a provenance manifest under
`artifacts/`. It never includes `.env`, local volumes, credentials, or other
untracked files.

## Delivery documentation

- [Release scope and acceptance](docs/delivery/RELEASE_CANDIDATE.md)
- [RC verification evidence](docs/delivery/RC_EVIDENCE.md)
- [Demonstration runbook](docs/delivery/DEMO_RUNBOOK.md)
- [Evaluation framework](docs/delivery/EVALUATION.md)
- [Architecture and security](docs/delivery/ARCHITECTURE_AND_SECURITY.md)
- [Responsible AI statement](docs/delivery/RESPONSIBLE_AI.md)
- [Operations guide](docs/delivery/OPERATIONS.md)
- [Security policy](SECURITY.md)
- [Delivery checklist](docs/delivery/DELIVERY_CHECKLIST.md)

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
