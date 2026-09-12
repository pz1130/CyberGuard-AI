# Docker Operations Guide

Release images are versioned as `cyberguard-api:1.0.0-rc.1`,
`cyberguard-tool-runner:1.0.0-rc.1`, and
`cyberguard-webui:1.0.0-rc.1`.

## Start and migrate

Validate configuration before starting:

```bash
docker compose config --quiet
docker compose build
docker compose up -d
```

Compose runs the one-shot `migrate` service before starting the API and
workers. After each build, run `make security-scan` and `make sbom`, then retain
the reports with the release evidence.

## Observe

```bash
docker compose ps
docker compose logs --since=15m api celery_worker tool-runner webui
curl --fail http://localhost:8000/health/ready
```

## Upgrade

1. Create and verify a backup.
2. Record the running image digests and Alembic revision.
3. Pull/build the new immutable version.
4. Run migrations as a one-off command.
5. Restart services and run health plus golden-path smoke checks.
6. Retain the previous images until acceptance completes.

## Backup and restore

Use the authenticated Backup UI/API. Keep encryption keys separately from the
backup. Test restore into a disposable stack before relying on a backup. A
database dump without its matching encryption key cannot restore encrypted
credentials.

## Incident actions

Engage the kill switch when agent execution must stop. Preserve API, worker,
tool-runner, database, and provider logs. Verify the audit chain and export the
relevant run events before changing affected records.

## Decommission

Export required records, revoke provider/MCP credentials, stop the stack, and
remove volumes only after retention owners approve deletion. `docker compose
down -v` irreversibly deletes local database, Redis, evidence, and backup
volumes.
