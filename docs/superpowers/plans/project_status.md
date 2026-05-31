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

- **Guardrail sanitization** — `GuardrailResult.sanitized` 字段预留，永远返回 `None`（`app/core/guardrails.py:423` `# Future: implement sanitization pass`）。
- **Governance evidence 文件上传（`kind=file`）** — schema/类型声明了 `file`（`EvidenceKind = Literal["file","url","text"]` + `file_path` 字段），但 `POST /governance/req-assessments/{id}/evidence` 只处理 `url`/`text`，**无 multipart `UploadFile`、无文件存储**；前端 `Governance.tsx` 表单 state 仅 `'text'|'url'`，`file` 不可选。两端皆缺。

## Recently completed

- **流式 sub-agent 输出** ✅ — `POST /agents/{id}/execute/stream`（SSE: start/tool_call_start/tool_call_end/text/done/error）。`InternalAgentRunner` 抽出共享 `_run_loop()`，新增 `execute_stream()`（最终答复经 `router.stream_chat()` 逐字重生成）；`AgentExecutor.execute_stream()` 按 kind 分流（internal 原生流式，其它 kind 单 done 事件）。WebUI Agents 页新增 RUN 面板（`api.executeAgentStream`）。
- **OCR for scanned-image PDFs** ✅ — merged via PR #4（Tesseract + vision，Celery 异步，`ocr_config`，alembic head `016_ocr`）。
- **Scheduled-tasks 执行** ✅ — `sync_scheduled_jobs_task` + Celery-beat `beat_schedule`（`app/workers/tasks.py`）已实现；cron 表达式按 beat 周期触发。
- **S3 / Alibaba OSS 备份** ✅ — `app/routers/backup.py` 有完整 boto3 multipart 实现（`_upload_to_s3_multipart`），已挂载到 `main.py`；运行时需配 `S3_ENDPOINT`/`S3_ACCESS_KEY`/`S3_SECRET_KEY` 环境变量。
- **Email 通知** ✅ — `app/services/email_service.py` 完整实现（smtplib + STARTTLS），被审批创建/决议（`approval_service.py`、`approval.py`）与定时任务完成（`workers/tasks.py`）三处调用；运行时需配 `SMTP_HOST`/`SMTP_FROM_EMAIL`。

## Operational notes

- 拉代码后重建：`docker compose build api webui`
- Migration：`docker compose exec api alembic upgrade head`（开发环境 startup 自动跑）
- Approvals 只在 `AUTO_APPROVE=false` 时产生待审批请求；docker-compose 默认 `AUTO_APPROVE=true`
- `test_smoke_api.py` 需要启动服务后单独运行：`python -m unittest tests.test_smoke_api`

## Stale branches (保留，勿合并)

- **`feature/fix-and-enhance`**（仅本地，未推送，10 个独立提交）— provider 层重构：`ProviderManager` 单例 + Anthropic/Gemini/Ollama/LM Studio/OpenRouter 原生 provider + `/discover` `/probe` `/models` 端点。**不要直接合并**：迁移链与 main 冲突，且大部分已被 main 取代；仅 `app/providers/` 是独有内容。将来若需要这些 provider 能力，**重新移植** `app/providers/`，不要 merge 整个分支。保留作参考。
