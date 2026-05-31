---
name: project_status
description: CyberGuard platform implementation status — last updated 2026-05-30 (Azure AD SSO complete; 87 tests green; alembic head 015)
type: project
---

# CyberGuard Project Status — 2026-05-30 (updated)

## ▶ Resume point (next session)

- **Branch:** `main` — all work committed, working tree clean. Latest commit: `893634d`.
- **Tests:** 87 passed. TypeScript: 0 errors.
- **Alembic head:** `015_sso_secret_envvar`

### Remaining known issues (prioritized)

| Priority | Issue |
|----------|-------|
| 🟢 Low | LangChain deprecation: `JsonPlusSerializer.allowed_objects`, handle on dependency upgrade |
| 🟢 Low | GlobalSearch not covering Users page (optional, depends on UX needs) |
| 🟢 Low | Security page `require_mfa` field missing (removed from UI rewrite, backend not implementing) |

---

## Session 2026-05-30 afternoon — Azure AD SSO Module

### Full Azure AD (Entra ID) SSO implementation (`bc8c844`, `893634d`)

Components added:
- `app/models/sso.py` — `SsoConfig` (single-row), `SsoRoleMapping` (azure_key unique, priority int)
- `app/services/sso_service.py` — MSAL lazy import, `resolve_role()`/`decide_provisioning()` pure functions, `provision_or_link_user()`, state/nonce Redis 5m TTL
- `app/routers/sso.py` — `/auth/sso/status`, `/login`, `/callback` (public) + `/sso/config`, `/sso/role-mappings` (ADMIN)
- `app/models/user.py` — `auth_provider`/`external_id` columns; `hashed_password` nullable for SSO users
- `alembic/versions/014_sso.py` + `015_sso_secret_envvar.py` — migrations applied
- `webui/src/pages/Login.tsx` — Microsoft button, `getSsoStatus()`, error URL param parsing
- `webui/src/pages/Users.tsx` — USERS/SSO tabs, config card + role-mapping CRUD table
- `webui/src/api/client.ts` — `getSsoConfig`/`updateSsoConfig`/`getSsoRoleMappings`/`createSsoRoleMapping`/`deleteSsoRoleMapping`/`getSecretEnvVars`
- `webui/src/App.tsx` — reads `#sso_token=` URL fragment on load
- `tests/test_sso_service.py` — 10 unit tests

**Secret source:** Client secret resolved from `sso_config.secret_env_var_id` FK → `env_vars` table (type=secret). Fallback to `AZURE_CLIENT_SECRET` env var for backward compat. Frontend shows dropdown of available secret EnvVars in SSO tab.

**Flow:** `GET /auth/sso/login` → 302 Microsoft → `/auth/sso/callback` → validates state (Redis), exchanges code (MSAL), provisions/links user, 302 `#sso_token=<jwt>` → localStorage.

**Architecture:** Single-worker (multi-worker blocked by MCP `_live_processes` subprocess handles, stale caches, group-chat in-memory state — see `multi-worker-blockers.md`).

### Session 2026-05-30 morning — WebUI Polish Sprint

#### CTRL+K Global Search (12 commits, `544401a` → `3c9a6c1`)

- `webui/src/context/SearchContext.tsx` — new React context for cross-page highlight state
- `webui/src/components/GlobalSearch.tsx` — command palette search modal (CTRL+K / Header click)
  - 12 data sources covered (see table below)
  - Cache TTL 60s (stale-while-revalidate)
- All 12 pages got `data-item-id` + `search-highlight` shimmer animation

| Data source | Tab | Icon |
|------------|-----|------|
| Agents | agents | ◆ |
| Providers | providers | ▣ |
| Skills | skills | ◈ |
| Tools | tools | ◇ |
| Knowledge | knowledge | ◉ |
| MCP Servers | mcp | ◎ |
| Schedule Tasks | schedule | ○ |
| Webhooks | webhooks | ⟳ |
| Governance Frameworks | governance (subview=frameworks) | ▦ |
| Governance Assessments | governance (subview=list) | ▧ |
| Prompt Templates | prompts | ≡ |
| N8N Connections | n8n | ⌥ |

#### Chat UI fixes (`43b13c8`, `593e295`)
- CONVERSATIONS header height → explicit `height: 42px`
- SESSION/CLEAR buttons grouped with `marginLeft: auto`
- Toolbar removed `flexWrap: wrap`

#### SYS ONLINE → Real health check (`a18aef3`)
- `Header.tsx` polls `GET /health/ready` every 30s
- Three states: `SYS ONLINE` (green) / `SYS DEGRADED` (amber, 503) / `SYS OFFLINE` (red)

#### TokenUsage raw fetch fix (`a18aef3`)
- `client.ts` added `getTokenUsageSummary()`
- `TokenUsage.tsx` uses api client instead of raw fetch

#### Security page full backend (`3912396`)
- `app/models/security_settings.py`, `app/services/security_settings.py`
- `app/routers/security.py` — `GET/PUT /security-settings`
- `Security.tsx` — real data; SAVE only enabled on changes

#### Approvals page (`c75fb4e`)
- Filter tabs: PENDING / APPROVED / REJECTED / ALL
- PENDING view auto-refreshes every 15s
- Risk level colored borders
- Inline ✓/✗ quick buttons, expandable detail panel

## Milestones

- **M1** — Backend Foundation: FastAPI + Postgres + Celery ✅
- **M2** — LLM Integration: Multi-provider router + intent parsing ✅
- **M3** — Sub-Agent System: external (OpenClaw/Hermes/Custom) + internal (in-app) ✅
- **M4** — WebUI: React + Vite + TypeScript ✅
- **M5** — Agent Collaboration: Multi-agent routing + group chat panel ✅
- **QwenPaw pool alignment** — ① executable Tool pool ✅ · ② unified assignment + tags ✅ · ③ external agents use pools ✅
- **WebUI Polish Sprint** — CTRL+K search + Security backend + Approvals page + health check ✅

---

## Not yet implemented

- S3 / Alibaba OSS backup（API stub 存在，无实现）
- Email notifications（helpers 存在）
- Guardrail sanitization（`GuardrailResult.sanitized` 字段预留，未实现）
- Governance evidence 文件上传（`kind=file` schema 存在，UI 未接）

## Recently completed

- **流式 sub-agent 输出** ✅ — `POST /agents/{id}/execute/stream`（SSE: start/tool_call_start/tool_call_end/text/done/error）。`InternalAgentRunner` 抽出共享 `_run_loop()`，新增 `execute_stream()`（最终答复经 `router.stream_chat()` 逐字重生成）；`AgentExecutor.execute_stream()` 按 kind 分流（internal 原生流式，其它 kind 单 done 事件）。WebUI Agents 页新增 RUN 面板（`api.executeAgentStream`）。
- **OCR for scanned-image PDFs** ✅ — merged via PR #4（Tesseract + vision，Celery 异步，`ocr_config`，alembic head `016_ocr`）。
- **Scheduled-tasks 执行** ✅ — `sync_scheduled_jobs_task` + Celery-beat `beat_schedule`（`app/workers/tasks.py`）已实现；cron 表达式按 beat 周期触发。

## Operational notes

- 拉代码后重建：`docker compose build api webui`
- Migration：`docker compose exec api alembic upgrade head`（开发环境 startup 自动跑）
- Approvals 只在 `AUTO_APPROVE=false` 时产生待审批请求；docker-compose 默认 `AUTO_APPROVE=true`
- `test_smoke_api.py` 需要启动服务后单独运行：`python -m unittest tests.test_smoke_api`
