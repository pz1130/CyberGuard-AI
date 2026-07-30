# CyberGuard AI Agent Platform

A secure, controllable, and extensible multi-agent AI system for cybersecurity operations — threat hunting, incident response, vulnerability scanning, GRC audits, and policy compliance.

## Architecture

```
                ┌──────────────┐
                │   WebUI      │  React + Vite + TS · 21 modules · 中/EN i18n
                └──────┬───────┘
                       │ REST + WebSocket
                ┌──────▼────────────────────────────────────┐
                │       FastAPI Backend                     │
                │  ┌────────────────────────────────────┐   │
                │  │ Master Agent (LangGraph StateGraph)│   │
                │  │  intent parse → route → summarize  │   │
                │  └────────────────────────────────────┘   │
                │  Routers: chat / agents / providers /     │
                │  skills / knowledge / groupchat / mcp /   │
                │  envvars / approval / token-usage /       │
                │  webhooks / prompt-templates / governance │
                └─┬──────┬──────────┬─────────┬─────────────┘
                  │      │          │         │
              ┌───▼─┐ ┌──▼──┐  ┌────▼───┐ ┌───▼───────────┐
              │ PG  │ │Redis│  │ Celery │ │ Sub-Agents    │
              │ +   │ │ +   │  │ workers│ │ (OpenClaw,    │
              │pgvec│ │queue│  │ + beat │ │  Hermes,      │
              └─────┘ └─────┘  └────────┘ │  Custom HTTP, │
                                          │  local LLM)   │
                                          └───────────────┘
                                          ↑
                            ┌─────────────┴───────────┐
                            │ OpenAI-compatible LLM   │
                            │ Provider (OpenAI / xAI /│
                            │ MiniMax / Anthropic /…) │
                            └─────────────────────────┘
```

## Features

### Core
- **Master Agent** — LangGraph state machine for intent parsing, task decomposition, and summary; configurable model/temperature/system-prompts/round-limits via the Settings tab
- **5 Sub-Agent Types** — Threat Intelligence, Log Anomaly, Vulnerability Scanner, Remediation Advisor, Compliance Checker (+ `osint` / `n8n_workflow` / `general`)
- **Streaming execution** — Server-Sent Events stream of an agent run (`POST /agents/{id}/execute/stream`) surfaced live in the WebUI
- **Multi-Agent Group Chat** — Round-robin discussions with Redis-backed sessions + consensus
- **Skill / Tool Pool** — Centralized MD-file managed capabilities
- **Knowledge Base** — pgvector embedding + RAG (per-KB dimension 1536 / 3072), with **OCR** for scanned PDFs (Tesseract + vision fallback)
- **Prompt Templates** — Pre-built system prompts (Pentest, SOC, IR, …) selectable from chat
- **MCP (Model Context Protocol)** — External tool servers (STDIO host runs in a dedicated `tool-runner` container)
- **Agent safety** — Reflector / loop-guard, per-run tool-call budget, opt-in episodic memory (`enable_episodic`) and pluggable web search (DuckDuckGo + Sploitus, `enable_search`)

### LLM Providers
- **10+ built-in presets** — OpenAI, Anthropic, Google Gemini, DeepSeek, Moonshot/Kimi, xAI/Grok, MiniMax, LM Studio, and any custom OpenAI-compatible endpoint
- **Per-model verification** — TEST each model from the UI; the Chat model picker shows only verified models
- **Capability probing** — on-demand tools/vision detection with 🔧/👁 badges
- **Auto-discovery** — server-side `GET /providers/{id}/models/discover`
- **Resilience** — exponential-backoff retry on 429/5xx (honors `Retry-After`) + opt-in per-provider token-bucket rate limiting

### Governance & Compliance
- **GRC module** — Frameworks (ISO 27001:2022, NIST CSF 2.0 seeded) + Requirements tree + Assessments + Evidence
- **AI-augmented audits** — LLM suggests evidence, judges compliance from uploaded evidence, generates markdown audit report
- **Standard evidence checklists** — 5-8 canonical evidence items per control (~1000+ items total)

### Automation
- **Scheduled Tasks** — Celery beat + Redis broker
- **N8N Integration** — Natural-language → workflow JSON
- **Bi-directional Webhooks** — Inbound (HMAC-validated) + outbound (subscribe to events like `approval.required`)

### Security & Ops
- **RBAC** — 5 pre-defined roles: Admin, Operator, Analyst, Viewer, Auditor
- **Human-in-the-Loop** — High-permission tools require Admin approval; dedicated Approvals tab with real-time SSE push, email notifications, and Redis pub/sub cross-process signalling (`AUTO_APPROVE` bypass for dev)
- **AES-256 Encryption** — Provider API keys, env vars, agent env vars, MCP tokens, knowledge metadata, and encrypted backups
- **Prompt-injection Guardrails** — 5-layer detection
- **Redis sliding-window rate limiting** — per-user req/min, req/h, burst
- **Full Audit Trail** — Exportable to SIEM (ELK/Splunk)
- **Backup/Restore** — pg_dump + AES-256, retention-based cleanup, optional S3/OSS upload with SSRF guards
- **Config Export/Import** — Full system JSON export
- **SSO** — OIDC single sign-on
- **Observability** — Optional OpenTelemetry OTLP tracing (HTTP / DB / LLM / Celery) + opt-in Langfuse LLM tracing

### UX
- **Bilingual UI** — full 中文 / English switching across every page
- **Branding** — custom logo + company name (Settings → Branding)
- **Multi-worker by default** — API runs `${API_WORKERS:-4}` Uvicorn workers; all shared state lives in Redis/Postgres

## Quick Start

### 1. Start infrastructure

```bash
cd cyberguard
docker-compose up -d postgres redis
```

### 2. Start backend

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

A default admin user is seeded on first start — **username `admin`, password `admin123`** (idempotent, all environments). **Change it before any real deployment.**

### 3. Start WebUI (development)

```bash
cd webui
npm install
npm run dev
```

Open **http://localhost:3000**

### Production

```bash
docker-compose up -d
```

### Database Migrations

This project uses Alembic with:

- `alembic.ini`
- `alembic/versions/`

Run migrations with:

```bash
alembic -c alembic.ini upgrade head
```

## WebUI Tabs (21 modules)

| Group | Tab (中 / EN) | Description |
|-------|---------------|-------------|
| Core | 聊天 / Chat | Master Agent chat, per-conversation prompt overrides, mode (normal/fast/expert), attachments, streaming |
| Features | Sub-Agent | Register / configure remote sub-agents (OpenClaw / Hermes / Custom HTTP) |
| Features | AI Provider | Presets + per-model TEST verification, capability probing, auto-discovery |
| Features | Skill Pool | Manage Skills as MD files with permission levels |
| Features | 工具池 / Tool Pool | Executable tools run sandboxed in the `tool-runner` container |
| Features | Prompt 模板 / Prompt Templates | Reusable system prompts (Pentest Auditor, SOC L2, IR, …) |
| Features | 知识库 / Knowledge | pgvector embedding + document upload (incl. OCR) + RAG search |
| Features | 群聊室 / Group Chat | Multi-agent round-robin discussions + consensus |
| Features | N8N 工作流 / N8N Workflows | Workflow management + LLM-generated workflows |
| Features | Webhook | Bi-directional HMAC-signed webhooks |
| Features | 治理合规 / Governance | GRC: frameworks, audits, evidence, AI-assisted assessment |
| Ops | 定时任务 / Scheduled Tasks | Celery beat scheduled jobs |
| Ops | MCP | Model Context Protocol server management |
| Ops | 环境变量 / Env Variables | AES-256 encrypted env vars |
| Ops | 安全 / Security | RBAC + encryption status |
| Ops | Token 消耗 / Token Usage | Per-user/provider usage tracking |
| Ops | 备份 / Backup | pg_dump + AES-256 backup / restore / delete |
| Ops | 审批管理 / Approvals | Human-in-the-loop approval queue with real-time SSE |
| Ops | 审计日志 / Audit Logs | Full HTTP + agent execution audit trail |
| Ops | 用户管理 / User Management | RBAC role and user management |
| Ops | 设置 / Settings | Master Agent global config (model/temperature/prompts/rounds) + Branding |

## API

All API endpoints are under `/api/v1/`. Key routes:

- `POST /api/v1/chat` — Submit task to Master Agent
- `POST /api/v1/agents/{id}/execute/stream` — SSE-streamed agent run
- `POST /api/v1/groupchat/sessions` — Multi-agent panel discussion
- `GET  /api/v1/approvals` · `POST /api/v1/approvals/{id}/decide` — Human-in-the-loop queue + decision
- `GET  /api/v1/approvals/events` — SSE stream of new approval requests
- `POST /api/v1/providers/test` · `POST /api/v1/providers/{id}/models/probe` — Verify / probe a model
- `POST /api/v1/schedule` — Create scheduled task
- `GET /api/v1/audit/export` — Export SIEM-format logs
- `POST /api/v1/backup` · `DELETE /api/v1/backup/{id}` — Trigger / delete backup
- `POST /api/v1/config/export` — Full system JSON export
- `GET /api/v1/prompt-templates` — Reusable system prompts
- `POST /api/v1/webhooks/incoming/{token}` — External system → Master Agent
- `GET /api/v1/governance/frameworks` — ISO 27001 / NIST CSF / custom
- `POST /api/v1/governance/assessments` — Start a compliance audit
- `POST /api/v1/governance/req-assessments/{id}/ai-assess` — AI-judged compliance
- `POST /api/v1/governance/assessments/{id}/ai-report` — Generate audit report

## Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/cyberguard
REDIS_URL=redis://localhost:6379/0
ENCRYPTION_KEY=   # 32-byte hex for AES-256
SECRET_KEY=       # JWT secret
MASTER_AGENT_MODEL=gpt-4o
MASTER_AGENT_TEMPERATURE=0.7
MOCK_MODE=true    # Set to false when real API keys are configured
API_WORKERS=4     # Uvicorn worker processes
AUTO_APPROVE=false # true bypasses the human approval gate (dev only)
```

## Testing

```bash
# Requires a Postgres+pgvector database (see DATABASE_URL)
pytest -q
```

The suite currently collects **365 tests** locally (the exact count is enforced by CI) across 42 `tests/test_*.py` files, covering the LLM router,
tool executor, approval state machine, backup helpers (SSRF guards, encryption
roundtrip), group-chat/multi-worker, OCR, governance, providers, and more.

## License

MIT
