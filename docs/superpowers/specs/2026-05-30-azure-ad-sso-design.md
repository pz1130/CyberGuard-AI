# Azure AD (Entra ID) SSO module

**Date:** 2026-05-30
**Status:** Approved — implementing

## Goal

Add an SSO module under user management that lets the app authenticate users via
Azure AD (Microsoft Entra ID) using OpenID Connect Authorization Code flow, while
keeping local username/password login as a fallback. First-time SSO users are
provisioned just-in-time and assigned an app role mapped from their Azure AD
groups/app-roles.

## Decisions (locked)

- **Config**: hybrid. `tenant_id`, `client_id`, `redirect_uri`, `enabled`,
  `default_role`, `allow_jit`, role mappings live in DB and are editable in the UI.
  The **client secret is read from env only** (`AZURE_CLIENT_SECRET`), never stored
  in or returned from the DB; the UI shows only whether it is configured.
- **Provisioning**: JIT create on first login + map Azure AD group object-ids /
  app-role values to app roles (`admin`/`operator`/`viewer`). Highest-privilege
  match wins; no match → `default_role`.
- **Login**: keep password login; add a "Sign in with Microsoft" button. Local
  admin remains a fallback.
- **Library**: MSAL (`msal`), single-tenant
  (`authority = https://login.microsoftonline.com/{tenant_id}`).
- **Token delivery to SPA**: URL fragment (`#sso_token=<jwt>`) → localStorage,
  consistent with the existing Bearer-token model.

## Architecture & data flow

```
Login page → GET /api/v1/auth/sso/login
  → build MSAL auth URL; store {state, nonce} in Redis (TTL 5m) → 302 to Microsoft
User authenticates → 302 to redirect_uri → GET /api/v1/auth/sso/callback?code&state
  → verify state (Redis, single-use); MSAL acquire_token_by_authorization_code;
    validate id_token (signature/issuer/audience/nonce — MSAL)
  → extract oid, email, name, groups (or roles)
  → resolve app role (mapping; highest-privilege; default_role on no match)
  → find User by external_id → else by email (link) → else JIT-create (if allow_jit)
  → mint app HS256 JWT via create_access_token (sub/username/role)
  → 302 to {webui_origin}/#sso_token=<jwt>
SPA reads fragment, stores token, cleans URL, loads app.
```

The app is served same-origin (nginx serves the SPA and proxies `/api/v1` +
`/health` to the API), so `redirect_uri` is `{public_webui_origin}/api/v1/auth/sso/callback`
and is configurable.

## Components

### Backend
- **Dependency**: add `msal`.
- **Config** (`app/config.py`): `AZURE_CLIENT_SECRET: str = ""` (env).
- **Migration `014_sso`**:
  - `users`: add `auth_provider VARCHAR default 'local' NOT NULL`,
    `external_id VARCHAR NULL` (indexed); alter `hashed_password` to **nullable**.
  - `sso_config` (single row, id=1): `enabled bool`, `tenant_id`, `client_id`,
    `redirect_uri`, `default_role` (default `viewer`), `allow_jit bool` (default true),
    `created_at`, `updated_at`.
  - `sso_role_mapping`: `id`, `azure_key` (group object-id or app-role value),
    `app_role`, `priority int` (higher = stronger), unique on `azure_key`.
- **Models**: extend `User`; add `SsoConfig`, `SsoRoleMapping`.
- **Service `app/services/sso_service.py`**:
  - `is_enabled(db) -> bool` — config.enabled AND secret present.
  - `build_auth_url(db, state, nonce) -> str` (MSAL ConfidentialClientApplication).
  - `exchange_code(db, code) -> claims` (returns oid/email/name/groups).
  - `resolve_role(db, claims) -> str` — pure logic, fully unit-tested.
  - `provision_or_link_user(db, claims) -> User` — link by external_id, then email;
    else JIT create; reject if inactive or JIT disabled and no match.
  - Cache invalidation hook like other settings (single-row cache).
- **Routers**:
  - `app/routers/sso.py` (or extend `auth.py`):
    - `GET /auth/sso/status` → `{ enabled: bool }` (no auth).
    - `GET /auth/sso/login` → 302 to Microsoft (404/redirect if disabled).
    - `GET /auth/sso/callback` → process, 302 to webui with token fragment.
  - Admin-only management (the "SSO module"):
    - `GET /sso/config` → config + `secret_configured: bool` (never the secret).
    - `PUT /sso/config`.
    - `GET/POST/DELETE /sso/role-mappings`.

### Frontend
- `api/client.ts`: `getSsoStatus`, `getSsoConfig`, `updateSsoConfig`,
  `getSsoRoleMappings`, `createSsoRoleMapping`, `deleteSsoRoleMapping`.
- `Login.tsx`: fetch status; show "Sign in with Microsoft" → full-page nav to
  `/api/v1/auth/sso/login`. Password form unchanged.
- App entry: if `location.hash` has `sso_token`, store it, clean hash, reload.
- Users area: new **SSO** tab/section (admin-only): config form (enabled, tenant id,
  client id, redirect uri, default role, JIT toggle; client-secret status only) +
  role-mapping CRUD.

## Error handling

| Case | Behaviour |
|------|-----------|
| SSO disabled / secret missing | `/auth/sso/login` → 302 `/?error=sso_unavailable` |
| Invalid / expired / reused state | 401 |
| Token exchange or id_token validation fails | 302 `/?error=sso_failed` |
| User inactive | 403 |
| JIT disabled and no existing user | 302 `/?error=sso_no_account` |
| oid/email collision | link by `oid` first, then by `email` |

Never log tokens or the client secret.

## Security

- `state` + `nonce` stored in Redis with short TTL, single-use (deleted on callback).
- MSAL validates id_token signature/issuer/audience; nonce checked.
- Scopes: `openid profile email` (+ group/role claims via app registration).
- Client secret in env only; `redirect_uri` taken from config (allowlisted).
- All `/sso/config` + `/sso/role-mappings` endpoints require role `ADMIN`.

## Testing (TDD, MSAL + Azure mocked — no network)

- `resolve_role`: single match, multiple matches (highest priority wins), no match → default.
- `provision_or_link_user`: new JIT user; link by external_id; link by email (sets
  external_id); inactive user rejected; JIT disabled + no user → rejected.
- `is_enabled`: requires both enabled flag and secret present.
- `GET /auth/sso/status` reflects enablement.
- `/sso/config` PUT/GET round-trip; secret never returned; RBAC enforced (non-admin 403).
- `/sso/role-mappings` CRUD + RBAC.

## Files

- `pyproject.toml`, `app/config.py`
- `alembic/versions/014_sso.py`
- `app/models/user.py`, `app/models/sso.py`
- `app/services/sso_service.py`
- `app/routers/sso.py`, `app/main.py` (router include)
- `webui/src/api/client.ts`, `webui/src/pages/Login.tsx`, `webui/src/App.tsx`,
  `webui/src/pages/Users.tsx` (+ SSO section component)
- `tests/test_sso_service.py`, `tests/test_sso_api.py`
