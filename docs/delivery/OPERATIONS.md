# Docker Operations Guide

The workgroup distributes a source archive. Operators build the images inside
their controlled environment; publishing them to a registry is optional.
Locally built images are versioned as `cyberguard-api:1.0.0-rc.1`,
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

## Build the source delivery package

After AMD64 acceptance, commit the final documentation and create a unique
annotated tag. Package that exact tag:

```bash
git status --short
git tag -a v1.0.0-rc.1 -m "CyberGuard 1.0.0-rc.1"
make source-package VERSION=1.0.0-rc.1 REF=v1.0.0-rc.1
```

Retain the generated archive, `.sha256`, manifest, SBOMs, scan output, and
`RC_EVIDENCE.md` together. The archive contains tracked files from the tag
only, so `.env`, provider keys, local databases, and backups are excluded.

## Optional registry publication

Registry publication is not an acceptance condition for this source-only
delivery. If an operator later publishes images, record immutable registry
digests and deploy by `image@sha256:...`, not a moving tag. The optional
`make release-digests` command writes `artifacts/release-digests.md`.

```bash
REGISTRY=<approved-registry>/
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
2. Record the running image IDs (or registry digests, if used) and Alembic
   revision.
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
