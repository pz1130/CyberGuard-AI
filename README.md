# CyberGuard AI Agent Platform

A secure, controllable, and extensible multi-agent AI system for cybersecurity operations — threat hunting, incident response, vulnerability scanning, GRC audits, and policy compliance.

## Architecture

```
                ┌──────────────┐
                │   WebUI      │  React + Vite + TS, 19 modules, i18n
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
- **Master Agent** — LangGraph state machine for intent parsing, task decomposition, and summary
- **5 Sub-Agent Types** — Threat Intelligence, Log Anomaly, Vulnerability Scanner, Remediation Advisor, Compliance Checker (+ `osint` / `n8n_workflow` / `general`)
- **Multi-Agent Group Chat** — Round-robin discussions with Redis-backed sessions
- **Skill / Tool Pool** — Centralized MD-file managed capabilities
- **Knowledge Base** — pgvector embedding + RAG (per-KB dimension 1536 / 3072)
- **Prompt Templates** — Pre-built system prompts (Pentest, SOC, IR, …) selectable from chat
- **MCP (Model Context Protocol)** — External tool servers

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
- **Human-in-the-Loop** — High-risk operations require Admin approval
- **AES-256 Encryption** — Provider API keys, env vars, agent env vars, MCP tokens, knowledge metadata
- **Prompt-injection Guardrails** — 5-layer detection
- **Redis sliding-window rate limiting** — per-user req/min, req/h, burst
- **Full Audit Trail** — Exportable to SIEM (ELK/Splunk)
- **Backup/Restore** — pg_dump + AES-256
- **Config Export/Import** — Full system JSON export
- **OpenTelemetry** — Optional OTLP tracing of HTTP / DB / LLM / Celery

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

Admin credentials are printed to console on first start (random password).

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

## WebUI Tabs (19 modules)

| Group | Tab | Description |
|-------|-----|-------------|
| CORE | 聊天 (Chat) | Master Agent chat, per-conversation prompt overrides, mode (normal/fast/expert), attachments |
| AGENTS | Sub-Agent 管理 | Register / configure remote sub-agents (OpenClaw / Hermes / Custom HTTP) |
| AGENTS | AI Provider | OpenAI, Anthropic, MiniMax, xAI, custom OpenAI-compatible endpoints |
| FEATURES | Skill Pool | Manage Skills + Tools as MD files with permission levels |
| FEATURES | Prompt 模板 | Reusable system prompts (Pentest Auditor, SOC L2, IR, …) |
| FEATURES | 知识库 | pgvector embedding + document upload + RAG search |
| FEATURES | 群聊室 | Multi-agent round-robin discussions |
| FEATURES | N8N | Workflow management + LLM-generated workflows |
| FEATURES | Webhook | Bi-directional HMAC-signed webhooks |
| FEATURES | 治理合规 (Governance) | GRC: frameworks, audits, evidence, AI-assisted assessment |
| OPS | 定时任务 | Celery beat scheduled jobs |
| OPS | MCP | Model Context Protocol server management |
| OPS | 环境变量 | AES-256 encrypted env vars |
| OPS | 安全 | RBAC + encryption status |
| OPS | Token 消耗 | Per-user/provider usage tracking |
| OPS | 备份 | pg_dump + AES-256 backup/restore |
| OPS | 审计日志 | Full HTTP + agent execution audit trail |
| OPS | 用户管理 | RBAC role and user management |
| OPS | 设置 | Master Agent global config (model/temperature/prompt) |

## API

All API endpoints are under `/api/v1/`. Key routes:

- `POST /api/v1/chat` — Submit task to Master Agent
- `POST /api/v1/groupchat/sessions` — Multi-agent panel discussion
- `POST /api/v1/schedule` — Create scheduled task
- `GET /api/v1/audit/export` — Export SIEM-format logs
- `POST /api/v1/backup` — Trigger backup
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
```

## License

MIT
