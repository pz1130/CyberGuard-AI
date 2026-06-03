---
name: project_status
description: CyberGuard platform implementation status — last updated 2026-06-03 (full suite verified 272/272 on a fresh pgvector container; migration chain unified to a single head 017_agent_episodes; chat attachments #13 + groupchat semantic consensus #14 merged)
type: project
---

# CyberGuard Project Status — 2026-06-03 (updated)

## ▶ Resume point (next session)

- **Branch:** `main` — all work committed, working tree clean, in sync with `origin/main`. Latest commit: this refresh (immediately after `6128df4`).
- **Branches:** only `main` (local + remote). All feature branches merged & cleaned up.
- **Open PRs / issues:** none.
- **Tests:** 26 test files (`tests/test_*.py`). **Full suite: 272/272 passing** on a fresh `pgvector/pgvector:pg16` container (port 5433, see local-test-db-ports.md). TypeScript: 0 errors.
- **Alembic heads (single):** `017_agent_episodes`. The bridge migration `002b_create_document_chunks` is now a real ancestor of 003 (down_revision corrected at `6128df4`). Dev-startup multiple-head handling (PR #12) is no longer strictly required but is harmless.
- **Archived work:** tag `archive/fix-and-enhance` (`d1a802c`, pushed to origin) preserves the deleted local `feature/fix-and-enhance` branch — only `app/providers/` (native multi-provider layer) is unique/worth re-porting; do not merge wholesale (migration chain collides).

### Remaining known issues (prioritized)

| Priority | Issue |
|----------|-------|
| 🟢 Low | LangChain deprecation: `JsonPlusSerializer.allowed_objects`, handle on dependency upgrade |
| 🟢 Low | GlobalSearch not covering Users page (optional, depends on UX needs) |
| 🟢 Low | Security page `require_mfa` field missing (removed from UI rewrite, backend not implementing) |

---

## Session 2026-06-02 — PentAGI-inspired features (PRs #5–#12, all merged)

Six feature PRs + two migration fixes merged into `main` on 2026-06-02:

- **#5 Reflector / loop-guard** — internal-agent self-reflection + loop detection.
- **#6 Tool-call budget** — per-run cap on internal-agent tool calls.
- **#7 Pluggable OSINT search providers** — DuckDuckGo + Sploitus behind `enable_search` (opt-in).
- **#8 Langfuse LLM tracing** — optional per-conversation/agent tracing; env-gated no-op when unconfigured.
- **#9 Episodic memory** — record/recall successful agent runs. New table `agent_episodes`, alembic `017_agent_episodes`, opt-in `enable_episodic`.
- **#11 document_chunks bridge migration** — `002b_create_document_chunks` (resolves #10: `001_initial` never created `document_chunks`, breaking `alembic upgrade head` on fresh DBs). Full chain `001→002→002b→003→…→017` verified clean on a fresh `pgvector/pgvector:pg16` container.
- **#12 multi-head startup fix** — dev-startup now handles the two-head alembic state instead of erroring.

## Session 2026-06-03 — End-to-end verification, gap-#13/#14, migration-chain fix

Two feature PRs merged (#13 chat-attachment extraction, #14 groupchat hybrid semantic consensus) plus one migration-chain fix (`6128df4`). Full test suite **272/272 verified** on a fresh `pgvector/pgvector:pg16` container.

- **#13 Chat attachment extraction** — chat `/chat/attachments` previously base64-decoded payloads as UTF-8 and truncated to 1000 chars (binary/PDF/image attachments became replacement-character garbage). Replaced with an async `extract_attachment_text` pipeline (`app/services/attachment_extractor.py`) that routes by content type: text/markdown/csv → utf-8 decode; PDF → pypdf via `knowledge_service.extract_text` with `ScannedPdfError` → OCR fallback; images → `ocr_service.ocr_image` (new wrapper). Per-attachment cap `ATTACHMENT_MAX_CHARS=8000`, total cap `ATTACHMENT_TOTAL_MAX_CHARS=24000`. OCR-disabled marker is explicit, failure marker attributed per-file. Extraction never raises; one bad attachment never aborts the agent run. `tests/test_attachment_extractor.py` covers all routing paths. Spec: `docs/superpowers/specs/2026-06-02-chat-attachment-extraction-design.md`.
- **#14 Group-chat hybrid semantic consensus** — `GroupChatSession._check_consensus` previously used crude word-overlap Jaccard. Rewritten as a 3-tier orchestrator: (1) embed agent responses via `router.embed`, compute `min_cos` against first-agent anchor; `>= GROUPCHAT_CONSENSUS_HIGH (0.85)` → `True`, `< GROUPCHAT_CONSENSUS_LOW (0.65)` → `False`; (2) gray band / embed failure → `_llm_judge_consensus` (LLM prompted with numbered responses, parses leading YES/NO, returns `None` on unparseable/error); (3) `_jaccard_consensus` fallback (the old heuristic, now extracted). `_first_agent_provider_id` extracted for DRY. All three settings live in `app/config.py`. `_check_consensus` never raises — embedding → judge → Jaccard each degrade. `tests/test_group_chat_consensus.py` covers every branch. Spec: `docs/superpowers/specs/2026-06-02-groupchat-semantic-consensus-design.md`.
- **Migration chain fix (`6128df4`)** — discovered while running the verification: PR-#11's bridge migration `002b_create_document_chunks` was *added* but `003_pgvector_knowledge.down_revision` was never updated from `002_openclaw_gateway` to `002b_create_document_chunks`, leaving two valid heads. The previous "verified end-to-end" claim in project memory was wrong (verified only by graph inspection, not by actually running `alembic upgrade head` on a fresh DB). Fixed by setting 003's `down_revision` to `002b_create_document_chunks`; chain is now linear `001 → 002 → 002b → 003 → 004 → … → 017` with a single head `017_agent_episodes`.

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

- _（无明确声明但未实现的功能）_

## Recently completed

- **Chat attachment extraction (#13)** ✅ — `app/services/attachment_extractor.py` routes attachments by content type (text/PDF/image) through the existing `knowledge_service.extract_text` + `ocr_service` toolkits. Per-attachment cap `ATTACHMENT_MAX_CHARS=8000`, total cap `ATTACHMENT_TOTAL_MAX_CHARS=24000`; OCR-disabled and per-file failure markers are explicit. `app/services/ocr_service.py` gains a public `ocr_image()` wrapper. `app/workers/tasks.py` calls the async extractor inside the existing event loop. Spec: `docs/superpowers/specs/2026-06-02-chat-attachment-extraction-design.md`. `tests/test_attachment_extractor.py` covers all routing paths (text/markdown/csv, text-PDF, scanned-PDF OCR fallback, image OCR, OCR-disabled marker, capping, failure isolation).
- **Hybrid semantic group-chat consensus (#14)** ✅ — `app/services/group_chat.py::_check_consensus` rewritten as a 3-tier orchestrator: `router.embed` → cosine vs first-agent anchor → HIGH (0.85) / LOW (0.65) bands; gray band or embed failure → `_llm_judge_consensus`; unparseable/error → `_jaccard_consensus` fallback. New settings `GROUPCHAT_CONSENSUS_HIGH/LOW/JACCARD_THRESHOLD` in `app/config.py`. `_first_agent_provider_id` extracted for DRY (used by both consensus and summary). `_check_consensus` never raises. Spec: `docs/superpowers/specs/2026-06-02-groupchat-semantic-consensus-design.md`. `tests/test_group_chat_consensus.py` covers every branch.
- **Migration chain unified to a single head (`6128df4`)** ✅ — `003_pgvector_knowledge.down_revision` now points at `002b_create_document_chunks`. Verified end-to-end on a fresh `pgvector/pgvector:pg16` container: `alembic upgrade head` runs the full chain `001 → 002 → 002b → 003 → 004 → … → 017` cleanly with one head `017_agent_episodes`. Full test suite **272/272 passes** in 3.38 s.
- **Guardrail sanitization** ✅ — `GuardrailResult.sanitized` 不再恒为 `None`。新增纯函数 `sanitize_text()`（幂等，固定点循环整条管线）中和「机械噪声」型注入：剥离 system/instruction 标签、HTML/markdown 标记，折叠 unicode/escape flood，截断 >20KB 段，移除分隔符注入；纯意图型 jailbreak 不可机械清理 → 返回 `None`，交给 block 逻辑。`check_prompt` / `check_prompt_sync` 均按 `cleaned if cleaned != text else None` 填充。新增 `pick_effective_input()`：仅在 medium/high 且未阻塞时替换为清理文本（critical 永不替换）。`POST /chat` 接入——派发给 worker 的是 `effective_input`，审计记录仍存原始 `body.message`。`tests/test_integration.py::TestGuardrails` 30 个测试全绿（含幂等性 fuzz、emoji flood、空输入、纯 jailbreak 等）。
- **Governance evidence 文件上传（`kind=file`）** ✅ — 后端 multipart 端点（`POST /governance/req-assessments/{id}/evidence/file`）+ 鉴权下载（`GET /governance/evidence/{id}/download`）；共享 `app/core/uploads.py::validate_and_read_upload`（magic-byte 校验，chat 已重构复用）；删除时 best-effort 清理磁盘文件；前端 Governance 页 FILE 选项（multipart）+ 下载按钮（显示 KB 大小）；`evidence_data` docker 卷挂载 `/data/evidence`；无需 DB 迁移（列已存在）。11 个新测试全部通过。
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

## Branch cleanup (2026-06-02)

- **删除** `origin/feat/evidence-file-upload` 与 `origin/feat/internal-agents` — 二者 tip 均已是 `origin/main` 的祖先（功能也确认在 main 中），已完全合并，安全删除。
- **删除** `feature/fix-and-enhance`（曾仅本地、未推送、47 个独立提交）— 已 **force-delete**，但 tip 以轻量标签 **`archive/fix-and-enhance`**（`d1a802c`，已推送 origin）保留，可随时 `git checkout -b <name> archive/fix-and-enhance` 找回。该分支为 provider 层重构（`ProviderManager` 单例 + Anthropic/Gemini/Ollama/LM Studio/OpenRouter 原生 provider + `/discover` `/probe` `/models` 端点）。**不要整分支合并**：迁移链与 main 冲突，且大部分已被 main 取代；唯一独有的是 `app/providers/`。将来若需要这些 provider 能力，从标签 **重新移植** `app/providers/` 即可。
