# CyberGuard AI - WebUI

React + TypeScript + Vite SPA for the CyberGuard AI Agent Platform.

## Quick Start

### Development

```bash
npm install
npm run dev
```

Open **http://localhost:3000**

The administrator account is created only when explicit `BOOTSTRAP_ADMIN_*`
values are supplied to the backend. No built-in or logged password exists.

### Production Build

```bash
npm run build
npm run preview
```

The production build is served by the Docker container on port 8080 (proxied to 3000 in docker-compose).

## Architecture

- `src/App.tsx` — Root component with tab-based routing
- `src/pages/` — One React component per page/tab
- `src/components/` — Shared components (Sidebar, Header)
- `src/api/client.ts` — API client (fetch wrappers for all endpoints)
- `src/i18n/` — i18next translations (Chinese / English)
- `vite.config.ts` — Vite config with API proxy to FastAPI backend

The Vite dev server proxies `/api/*` → `http://localhost:8000/api/v1/*` and `/ws/*` → `ws://localhost:8000/ws/*`.

## Pages

| Page | Description |
|------|-------------|
| Chat | Master Agent conversation interface |
| AI Provider 管理 | Configure LLM providers (OpenAI, Anthropic, custom) |
| Sub-Agent 管理 | Register and manage remote sub-agents |
| Skill / Tool Pool | Manage available skills and tools as MD files |
| Knowledge Base | Upload and query documents with embeddings |
| MCP | Model Context Protocol servers and tools |
| 环境变量 | Encrypted environment variables for agents |
| 安全 | RBAC, encryption status, security settings |
| Token 消耗 | Track API token usage per user/provider |
| 备份 | pg_dump + AES-256 backup/restore |
| 审计日志 | Full audit trail of all operations |
| 用户管理 | RBAC user and role management |
| Governance | Assessments, evidence, approvals, kill switch, and metrics |
