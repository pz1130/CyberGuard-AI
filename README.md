# CyberGuard AI Agent Platform

A secure, controllable, and extensible multi-agent AI system for cybersecurity operations — threat hunting, incident response, vulnerability scanning, and policy compliance.

## Architecture

```
User → WebUI (React SPA) → FastAPI (Master Agent / LangGraph)
                                    ↓
                           Sub-Agent Executors
                                    ↓
                    ┌───────────────┼───────────────┐
                 OpenClaw        Hermes          Custom HTTP
                  (Remote)       (Remote)        (Remote)
```

## Features

- **Master Agent** — LangGraph state machine for intent parsing, task decomposition, and summary
- **5 Sub-Agent Types** — Threat Intelligence, Log Anomaly, Vulnerability Scanner, Remediation Advisor, Compliance Checker
- **Group Chat** — Real-time WebSocket multi-agent discussions
- **Skill / Tool Pool** — Centralized MD-file managed capabilities
- **Knowledge Base** — Third-party embedding API with reranking
- **RBAC** — 5 pre-defined roles: Admin, Operator, Analyst, Viewer, Auditor
- **Human-in-the-Loop** — High-risk operations require Admin approval
- **AES-256 Encryption** — Sensitive env vars, backup files, knowledge metadata
- **Full Audit Trail** — Exportable to SIEM (ELK/Splunk)
- **Scheduled Tasks** — Cron-based with APScheduler
- **MCP (Model Context Protocol)** — External tool servers
- **Backup/Restore** — pg_dump + AES-256, S3/OSS support
- **Config Export/Import** — Full system JSON export

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

## WebUI Tabs

| Tab | Description |
|-----|-------------|
| 🗣️ 对话 | Master Agent chat interface |
| 🤖 Sub-Agent 管理 | Register/configure remote sub-agents |
| 🔌 AI Provider 配置 | OpenAI, Anthropic, custom endpoints |
| 🧠 Skill Pool | Manage agent capabilities as MD files |
| 🔧 Tool Pool | Manage tools with permission levels |
| 📚 知识库 | Document embedding and RAG queries |
| 👥 群聊室 | Real-time multi-agent WebSocket chat |
| ⏰ 定时任务 | Cron-scheduled task management |
| 🔌 MCP | Model Context Protocol servers |
| ⚙️ 环境变量 | Encrypted key/value for agents |
| 🛡️ 安全 | RBAC, encryption status |
| 📊 Token 消耗 | Per-user/provider usage tracking |
| 💾 备份 | pg_dump + AES-256 backup/restore |
| 📋 审计日志 | Full operation history |
| 👤 用户管理 | RBAC role and user management |

## API

All API endpoints are under `/api/v1/`. Key routes:

- `POST /api/v1/chat` — Submit task to Master Agent
- `WS /ws/groupchat/{room_id}` — Real-time group chat
- `POST /api/v1/schedule` — Create scheduled task
- `GET /api/v1/audit/export` — Export SIEM-format logs
- `POST /api/v1/backup` — Trigger backup
- `POST /api/v1/config/export` — Full system JSON export

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
