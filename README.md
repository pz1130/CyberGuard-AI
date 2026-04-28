# CyberGuard AI Agent Platform - M1 MVP

## Overview
CyberGuard is a secure, controllable, and extensible multi-agent AI system for cybersecurity operations, threat hunting, incident response, and policy making.

## Architecture
- **Master Agent**: LangGraph state machine for intent parsing, task decomposition, and coordination
- **Sub-Agents**: Threat Intelligence, Log Anomaly, Vulnerability Scanner, Remediation Advisor, Compliance Checker
- **WebUI**: OpenWebUI fork with Chinese/English toggle
- **Database**: PostgreSQL with AES-256 encryption
- **Queue**: Redis for task queuing and WebSocket pub/sub

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Environment Setup
```bash
cp .env.example .env
# Edit .env with your configuration
```

### Docker Compose
```bash
docker-compose up -d
```

### Database Migrations
```bash
alembic upgrade head
```

### Run Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure
```
cyberguard/
├── app/
│   ├── main.py              # FastAPI application entry
│   ├── config.py            # Configuration management
│   ├── core/
│   │   ├── security.py      # AES-256 encryption utilities
│   │   ├── rbac.py          # RBAC middleware
│   │   ├── audit.py         # Audit logging middleware
│   │   ├── database.py      # Database connection
│   │   └── redis_client.py  # Redis connection
│   ├── models/
│   │   ├── user.py          # User & RBAC models
│   │   ├── agent.py         # Agent & config models
│   │   ├── skill.py         # Skill & Tool models
│   │   ├── knowledge.py     # Knowledge base models
│   │   └── audit.py         # Audit log model
│   ├── routers/
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── users.py         # User management
│   │   ├── agents.py        # Sub-agent management
│   │   ├── skills.py        # Skill/Tool pool
│   │   ├── knowledge.py     # Knowledge base
│   │   ├── tasks.py         # Task execution
│   │   ├── chat.py          # WebSocket chat
│   │   └── admin.py         # Admin operations
│   ├── services/
│   │   ├── agent_executor.py # Sub-agent HTTP executor
│   │   └── llm_router.py    # LLM model routing
│   └── agents/
│       ├── master.py        # LangGraph master agent
│       └── states.py        # Agent state definitions
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## RBAC Roles
| Role      | Permissions |
|-----------|-------------|
| Admin     | Full access + user management + encryption key management |
| Operator  | Agent management + task execution |
| Analyst   | Read access + knowledge base query |
| Viewer    | Read-only access |
| Auditor   | Audit log access only |

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/logout` - User logout
- `POST /api/v1/auth/refresh` - Refresh token

### Users
- `GET /api/v1/users` - List users (Admin)
- `POST /api/v1/users` - Create user (Admin)
- `PUT /api/v1/users/{id}` - Update user (Admin)
- `DELETE /api/v1/users/{id}` - Delete user (Admin)

### Sub-Agents
- `GET /api/v1/agents` - List configured agents
- `POST /api/v1/agents` - Register new agent
- `PUT /api/v1/agents/{id}` - Update agent config
- `DELETE /api/v1/agents/{id}` - Remove agent
- `POST /api/v1/agents/{id}/test` - Test agent connection

### Skills & Tools
- `GET /api/v1/skills` - List all skills
- `POST /api/v1/skills` - Create skill (Admin)
- `PUT /api/v1/skills/{id}` - Update skill
- `DELETE /api/v1/skills/{id}` - Delete skill

### Knowledge Base
- `GET /api/v1/knowledge/bases` - List knowledge bases
- `POST /api/v1/knowledge/bases` - Create knowledge base
- `POST /api/v1/knowledge/bases/{id}/documents` - Upload document
- `POST /api/v1/knowledge/query` - Query knowledge base

### Tasks
- `POST /api/v1/tasks` - Submit task to master agent
- `GET /api/v1/tasks/{id}` - Get task status/result
- `GET /api/v1/tasks` - List tasks

### Chat (WebSocket)
- `WS /api/v1/chat/ws` - WebSocket chat endpoint

## Security Features
- AES-256 encryption for sensitive data (env vars, backups, KB metadata)
- RBAC with permission inheritance
- Human-in-the-Loop for high-risk operations
- Full audit trail with hash verification
- JWT-based authentication

## Configuration
See `.env.example` for all environment variables.

## License
Proprietary - All rights reserved