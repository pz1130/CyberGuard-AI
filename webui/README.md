# CyberGuard AI - WebUI

Single-page application (SPA) for the CyberGuard AI Agent Platform.

## Quick Start

### 1. Start the FastAPI backend
```bash
cd ..
uvicorn app.main:app --reload --port 8000
```

### 2. Start the WebUI server
```bash
python server.py
```

Then open **http://localhost:3000**

Default login: `admin` / `admin123`

## Architecture

- `index.html` — Complete SPA (HTML + CSS + JS, no build step)
- `server.py` — Python HTTP server with API proxy to FastAPI

The server proxies `/api/*` requests to `http://localhost:8000/api/v1/*`.

## Features

| Page | Status |
|------|--------|
| 🗣️ Chat (Master Agent) | ✅ Live |
| 🖥️ AI Provider 管理 | ✅ CRUD |
| 🤖 Sub-Agent 管理 | ✅ CRUD + Test |
| 🧠 Skill / Tool Pool | ✅ CRUD |
| 📚 Knowledge Base | 🚧 Coming soon |
| 👥 群聊室 | 🚧 Coming soon |
| ⏰ 定时任务 | 🚧 Coming soon |
| 🔌 MCP | 🚧 Coming soon |
| ⚙️ 环境变量 | 🚧 Coming soon |
| 🛡️ 安全 | 🚧 Coming soon |
| 📊 Token 消耗 | 🚧 Coming soon |
| 💾 备份 | 🚧 Coming soon |
| 📋 审计日志 | 🚧 Coming soon |
| 👤 用户管理 (RBAC) | 🚧 Coming soon |
