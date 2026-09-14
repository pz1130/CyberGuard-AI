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

## Restart recovery

PostgreSQL and Redis use `restart: unless-stopped`, matching API, Celery,
tool-runner, and WebUI. After a Docker daemon restart the long-lived services
must return to running/healthy without a manual `compose up`. The one-shot
`migrate` service stays exited (0).

Verify:

```bash
docker compose ps
curl --fail http://localhost:8000/health/ready
```

`postgres` and `redis` must be `running` (healthy). API `/health/ready` must
return HTTP 200. Celery workers must reconnect to Redis without a restart.

## Runtime hardening

Application containers (API, migrate, Celery, tool-runner, WebUI) run as a
non-root numeric user, drop all Linux capabilities, set
`no-new-privileges:true`, and use a read-only root filesystem. Writable state
is limited to named volumes (`/backups`, `/var/run/celerybeat`) and `tmpfs`.
WebUI nginx listens on 8080 inside the container; the host port remains
`${WEBUI_PORT:-3000}`.

PostgreSQL and Redis keep their official entrypoints (root → gosu). They still
`cap_drop: ALL` and set `no-new-privileges:true`, with only the capabilities
gosu needs added back.

Verify a running stack:

```bash
docker compose ps
docker inspect "$(docker compose ps -q api)" \
  --format 'User={{.Config.User}} CapDrop={{json .HostConfig.CapDrop}} Sec={{json .HostConfig.SecurityOpt}} Readonly={{.HostConfig.ReadonlyRootfs}}'
```

Expect `User=10001:10001`, `CapDrop=["ALL"]`, `no-new-privileges:true`,
`Readonly=true`. WebUI user is `101:101`.

## Publish and record immutable digests

Local image IDs are not registry digests. After the workgroup accepts the
candidate:

1. `make docker-build && make security-scan && make sbom`
2. `make release-digests` — writes `artifacts/release-digests.md`
3. Tag and push each image to the chosen registry
4. Re-run `make release-digests` and copy the `repo@sha256:...` values into
   `docs/delivery/RC_EVIDENCE.md`
5. Prefer pulling by digest (`image@sha256:...`) in production, not the
   moving `:1.0.0-rc.1` tag

```bash
REGISTRY=ghcr.io/pz1130/
for image in cyberguard-api:1.0.0-rc.1 cyberguard-tool-runner:1.0.0-rc.1 cyberguard-webui:1.0.0-rc.1; do
  docker tag "$image" "${REGISTRY}${image}"
  docker push "${REGISTRY}${image}"
  docker buildx imagetools inspect "${REGISTRY}${image}" --format '{{json .Manifest.Digest}}'
done
```

## Upgrade

1. Create and verify a backup.
   Before migration 033, export any GRC assessment records that must be moved
   to the companion GRC product; the migration removes the duplicated tables.
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
down -v` irreversibly deletes local database, Redis, and backup
volumes.
