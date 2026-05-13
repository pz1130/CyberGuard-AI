# CyberGuard AI Agent Platform - System Design Document (English)

## 1. Project Overview
- **System Name**: CyberGuard AI Agent Platform (CG-AAP)
- **Purpose**: A secure, controllable and extensible multi-agent AI system for company cybersecurity operations, threat hunting, incident response and policy making.
- **Core Architecture**: Master Agent orchestration + Sub-Agent execution + WebUI centralized management
- **Key Features**: RBAC, Human-in-the-Loop approval workflow, AES-256 encryption, full audit trail, real-time group chat, scheduled tasks (Celery), Skill/Tool Pool, RAG Knowledge Base, N8N workflow integration, prompt injection guardrails, Redis rate limiting, OpenTelemetry tracing
- **User Scale**: ≤5 concurrent users, configurable Sub-Agents

## 2. High-Level Architecture
```
User → WebUI (Custom React/Vite/TypeScript)
  → FastAPI Backend (REST + WebSocket)
    → Master Agent (LangGraph StateGraph)
      → Redis (Celery task queue + WebSocket pub/sub + rate limiting + JWT blacklist)
      → PostgreSQL (all persistent state, AES-256 encrypted secrets)
      → Sub-Agents (configurable: remote via HTTP endpoint, or local LLM fallback)
      → LLM Router (OpenAI-compatible API, any provider)
    → Knowledge Base (embedding via LLM Router + vector similarity search)
    → N8N Integration (workflow generation + management via N8N REST API)
    → OpenTelemetry (optional OTLP tracing of HTTP, LLM, DB, Celery)
```

## 3. Components

- **WebUI**: Custom React + Vite + TypeScript application with Chinese/English i18n, dark/light theme, monospace cyberpunk design. NOT an OpenWebUI fork. (detailed in 05_WEBUI_DESIGN.md)
- **Master Agent**: LangGraph `StateGraph` state machine for intent parsing, task decomposition, sub-agent routing, group chat moderation, validation, summarization, and Human-in-the-Loop approval.
- **Sub-Agents**: Configurable via WebUI (agents page). Each has a `backend_type` (openclaw, hermes, general, or custom) and an optional remote endpoint URL. If no endpoint is configured, the local LLM executor is used as fallback. Agent types used for routing: `threat_intel`, `log_anomaly`, `vuln_scanner`, `remediation`, `compliance`, `osint`, `n8n_workflow`, `general`.
- **LLM Router**: Custom router using `openai` Python SDK (`AsyncOpenAI`) against any OpenAI-compatible endpoint. Provider configs (including AES-256 encrypted API keys) are stored in PostgreSQL. Supports model selection, temperature override, `<think>` tag stripping, token usage recording, and OpenTelemetry spans.
- **Skill/Tool Pool**: Both Skills and Tools are stored in PostgreSQL with Markdown content, version, permission level, and approval flag. Managed from the Skills tab in WebUI.
- **Knowledge Base**: Documents stored in PostgreSQL. Embedding via LLM Router's `/embeddings` endpoint (OpenAI-compatible). Similarity search done in-process (cosine similarity over stored vectors).
- **N8N Integration**: CRUD for N8N workflow configurations, LLM-generated workflow JSON from natural language, and direct N8N REST API management (list/create/update/delete workflows).
- **Celery Workers**: Background task execution using Celery with Redis as broker and result backend.
- **Other Modules**: Scheduled Tasks (Celery-based), MCP server management, Environment Variables (AES-256 encrypted in DB), Security/RBAC, Token Usage monitoring, Backup (local), Audit Log (full chain, exportable), User Management (RBAC), Conversation History, Human-in-the-Loop Approval, Master Agent Config, Prompt Injection Guardrails, Redis Rate Limiting, OpenTelemetry Tracing.

## 4. RBAC Design
- Pre-defined roles: `admin`, `operator`, `analyst`, `viewer`, `auditor`
- JWT-based authentication with access + refresh tokens; token revocation via Redis blacklist
- Human-in-the-Loop: High-risk agent operations create a pending `ApprovalRequest` in DB; admin approves/rejects via REST API or WebUI. Waits up to 1 hour before expiring.
- Per-endpoint permission enforcement via `require_permission()` FastAPI dependency

## 5. Security Design
- Sensitive data (API keys, env vars, agent env vars, knowledge base metadata, MCP tokens): AES-256 encryption via `app/core/security.py`
- JWT access tokens (24h default) + refresh tokens (7d) with Redis-backed revocation blacklist
- Prompt injection guardrails (`app/core/guardrails.py`): 5-strategy detection (pattern matching, markup injection, soft-reject patterns, structural anomaly scoring, optional LLM classification)
- Redis sliding window rate limiting: per-user per-minute, per-hour, and concurrency burst limits
- Audit log: every HTTP request and agent action is logged with input/output hashes
- Sub-Agent containers can be isolated in Docker; all communication is HTTP (can add HTTPS via Nginx)
- Mock mode (`MOCK_MODE=true`) for demo without real API keys

## 6. Data Model (Key Tables)
```
users (id, username, email, hashed_password, role, is_active, full_name, last_login, created_at, updated_at)
roles (id, name, permissions_json, description, created_at)
agent_configs (id, agent_name, backend_type, provider_id, endpoint_url, env_vars_encrypted, system_prompt, description, is_active, permission_level, associated_skills, metadata_json, ...)
agent_executions (id, execution_id, agent_id, status, input_data, output_data, error_message, ...)
skills (id, name, description, md_content, version, category, permission_level, requires_approval, is_active, ...)
tools (id, name, description, md_content, version, category, permission_level, requires_approval, is_active, ...)
knowledge_bases (id, name, description, embedding_model, rerank_model, metadata_encrypted, ...)
documents (id, kb_id, filename, content_chunks_json, file_hash, file_size, mime_type, ...)
audit_logs (id, user_id, agent_id, action, input_hash, output_hash, request_id, timestamp)
providers (id, name, provider_type, api_key_encrypted, base_url, api_version, models, is_active, metadata_json, ...)
mcp_servers (id, name, transport_type, command, args, env_vars_encrypted, url, auth_token_encrypted, ...)
mcp_tools (id, server_id, tool_name, description, input_schema_json, required_permission, ...)
env_vars (id, key, value_encrypted, value_type, description, is_active, ...)
token_usage_logs (id, provider_id, provider_name, model_name, prompt_tokens, completion_tokens, total_tokens, call_count, date_str, ...)
```
Additional tables (created at runtime by models): `approval_requests`, `schedules`, `conversations`, `n8n_configs`, `master_agent_config`, `backups`. (The legacy `groupchat_rooms` / `groupchat_messages` tables were dropped in migration 005 when the human room chat feature was removed; multi-agent group chat sessions persist in Redis only.)

## 7. Main Workflows
- **Normal task**: User → chat API → Master Agent → LLM intent parse → route to Sub-Agents (parallel) → validate results → LLM summarize → response
- **Multi-Agent Group Chat**: User selects N sub-agents + initial prompt → `POST /api/v1/groupchat/sessions` → each round every agent responds in sequence → session state cached in Redis → REST polled by WebUI
- **High-Risk / Human-in-the-Loop**: Agent execution flags `needs_approval` or output contains risk keywords → `ApprovalRequest` created in DB → admin decides via REST/WebUI → execution resumes or aborts
- **Scheduled Tasks**: Celery beat + Redis; tasks run in worker process; email notification on completion (if configured)
- **N8N Workflow Generation**: User describes goal in natural language → LLM generates N8N workflow JSON → optionally auto-deployed to connected N8N instance

## 8. Non-Functional Requirements
- **Deployment**: Docker Compose (single node) + Kubernetes manifests available (`k8s/`)
- **Message Queue / Background Tasks**: Celery + Redis
- **Database**: PostgreSQL (asyncpg driver)
- **LLM/Embedding**: OpenAI-compatible API (any provider); model routing via DB-stored provider configs
- **Backup**: Local file download (S3/OSS planned but not yet implemented)
- **Observability**: OpenTelemetry (optional OTLP export); structured audit logs
- **Configuration Export**: Full system JSON export via `/api/v1/config/export`
- **Mock Mode**: `MOCK_MODE=true` enables full UI demo without real LLM API keys
