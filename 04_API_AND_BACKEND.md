# API 与 Backend 设计

## 1. 数据库 Schema（PostgreSQL）

所有表由 Alembic 管理（`alembic/versions/001_initial.py`），部分表由 SQLAlchemy 模型在运行时创建：

```sql
-- 用户与 RBAC
users (id, username, email, hashed_password, role, is_active, full_name, last_login, created_at, updated_at)
roles (id, name, permissions_json, description, created_at)

-- Sub-Agent 配置与执行
agent_configs (id, agent_name, backend_type, provider_id, endpoint_url, env_vars_encrypted,
               system_prompt, description, is_active, permission_level, associated_skills,
               metadata_json, created_at, updated_at)
agent_executions (id, execution_id, agent_id, status, input_data, output_data,
                  error_message, started_at, completed_at, created_at)

-- Skill / Tool Pool（独立表，结构相同）
skills (id, name, description, md_content, version, category, permission_level,
        requires_approval, is_active, metadata_json, created_at, updated_at)
tools  (id, name, description, md_content, version, category, permission_level,
        requires_approval, is_active, metadata_json, created_at, updated_at)

-- AI Provider 管理
providers (id, name, provider_type, api_key_encrypted, base_url, api_version,
           models, is_active, metadata_json, created_at, updated_at)

-- 知识库
knowledge_bases (id, name, description, embedding_model, rerank_model, is_active,
                 metadata_encrypted, metadata_json, created_at, updated_at)
documents (id, kb_id, filename, content_chunks_json, file_hash, file_size, mime_type,
           metadata_json, created_at, updated_at)

-- MCP
mcp_servers (id, name, transport_type, command, args, env_vars_encrypted, url,
             auth_token_encrypted, headers_json, description, is_active, timeout_seconds,
             process_id, metadata_json, created_at, updated_at)
mcp_tools (id, server_id, tool_name, description, input_schema_json, category,
           is_active, last_used_at, use_count, required_permission, created_at)

-- 环境变量（AES-256 加密）
env_vars (id, key, value_encrypted, value_type, description, is_active, created_at, updated_at)

-- Token 用量追踪
token_usage_logs (id, provider_id, provider_name, model_name, prompt_tokens,
                  completion_tokens, total_tokens, call_count, date_str, created_at)

-- 审计日志
audit_logs (id, user_id, agent_id, action, input_hash, output_hash, request_id, timestamp)

-- 审批流（Human-in-the-Loop）
approval_requests (id, request_id, user_id, action_type, action_description, agent_id,
                   payload_json, risk_level, urgency, status, decision_by,
                   decision_comment, expires_at, created_at, decided_at)

-- 定时任务
schedules (id, name, cron_expr, task_type, payload_json, is_active, last_run_at,
           next_run_at, created_by, created_at, updated_at)

-- 群聊会话（多 Agent 圆桌讨论，存 Redis；表已废弃）
-- group_chat_messages 表已在 migration 005 中删除（room chat 功能下线）

-- 对话历史
conversations (id, conversation_id, user_id, title, messages_json, provider_id,
               model, created_at, updated_at)

-- N8N 集成
n8n_configs (id, name, base_url, api_key_encrypted, is_active, metadata_json, created_at, updated_at)

-- Master Agent 全局配置
master_agent_config (id, model, temperature, system_prompt, intent_parser_prompt,
                     summarizer_prompt, updated_at)

-- 备份记录
backups (id, filename, file_path, file_size, backup_type, status, created_by, created_at)

-- Webhook（双向，migration 006）
webhooks (id, name, direction, description, is_active,
          incoming_token_hash, outgoing_url, outgoing_secret_encrypted, outgoing_events,
          last_triggered_at, trigger_count, success_count, failure_count, last_error,
          created_at, updated_at)

-- Prompt 模板库（migration 007）
prompt_templates (id, name, description, content, category, is_active,
                  created_at, updated_at)

-- 治理 / GRC（migration 008-009，灵感来自 ciso-assistant-community）
gov_frameworks (id, urn, name, version, description, locale, ref_url, is_active,
                created_at, updated_at)
gov_requirements (id, framework_id, parent_id, urn, ref_id, name, description,
                  depth, order_index, is_assessable, typical_evidence)
gov_assessments (id, name, description, framework_id, scope, status, start_date,
                 due_date, owner_user_id, created_at, updated_at)
gov_requirement_assessments (id, assessment_id, requirement_id, status, score,
                              observation, ai_recommendation, ai_assessed_at,
                              updated_at, updated_by_user_id)
gov_evidences (id, requirement_assessment_id, name, description, kind, file_path,
               url, body, mime_type, size_bytes, uploaded_by_user_id, uploaded_at)
```

## 2. REST API 端点（所有路径前缀 `/api/v1`）

所有 API 使用 FastAPI + RBAC 中间件（`require_permission()` 依赖）。

### 认证
```
POST /api/v1/auth/login         → 用户名密码登录，返回 access + refresh token
POST /api/v1/auth/refresh       → 刷新 access token
POST /api/v1/auth/logout        → 注销（加入 Redis 黑名单）
GET  /api/v1/auth/me            → 获取当前用户信息
```

### 用户管理
```
GET    /api/v1/users            → 用户列表（Admin）
POST   /api/v1/users            → 创建用户（Admin）
GET    /api/v1/users/{id}       → 获取用户
PUT    /api/v1/users/{id}       → 更新用户
DELETE /api/v1/users/{id}       → 删除用户
```

### Sub-Agent 管理
```
GET    /api/v1/agents           → Agent 列表
POST   /api/v1/agents           → 创建 Agent
GET    /api/v1/agents/{id}      → 获取 Agent
PUT    /api/v1/agents/{id}      → 更新 Agent
DELETE /api/v1/agents/{id}      → 删除 Agent
POST   /api/v1/agents/{id}/execute → 手动执行 Agent 任务
```

### AI Provider 管理
```
GET    /api/v1/providers        → Provider 列表
POST   /api/v1/providers        → 创建 Provider（API key AES-256 加密存储）
GET    /api/v1/providers/{id}   → 获取 Provider
PUT    /api/v1/providers/{id}   → 更新 Provider
DELETE /api/v1/providers/{id}   → 删除 Provider
POST   /api/v1/providers/{id}/test → 测试连通性
```

### Skill / Tool Pool
```
GET    /api/v1/skills           → Skill 列表（可按 type=tool 过滤 Tool）
POST   /api/v1/skills           → 创建 Skill/Tool
GET    /api/v1/skills/{id}      → 获取 Skill/Tool
PUT    /api/v1/skills/{id}      → 更新 Skill/Tool
DELETE /api/v1/skills/{id}      → 删除 Skill/Tool
```

### 知识库
```
GET    /api/v1/knowledge                    → 知识库列表
POST   /api/v1/knowledge                    → 创建知识库
GET    /api/v1/knowledge/{id}               → 获取知识库
DELETE /api/v1/knowledge/{id}               → 删除知识库
POST   /api/v1/knowledge/{id}/upload        → 上传文档
GET    /api/v1/knowledge/{id}/documents     → 文档列表
DELETE /api/v1/knowledge/{id}/documents/{doc_id} → 删除文档
POST   /api/v1/knowledge/{id}/search        → 向量相似度搜索
```

### 聊天 & 对话
```
POST /api/v1/chat               → 发送消息（经 Master Agent 处理，支持 provider_id/model 选择）
GET  /api/v1/conversations      → 对话历史列表
POST /api/v1/conversations      → 创建对话
GET  /api/v1/conversations/{id} → 获取对话详情
PUT  /api/v1/conversations/{id} → 更新对话（标题/消息）
DELETE /api/v1/conversations/{id} → 删除对话
```

### 群聊（Multi-Agent 圆桌讨论，REST）
```
POST   /api/v1/groupchat/sessions                       → 创建会话（选 agent + 初始 prompt）
GET    /api/v1/groupchat/sessions/{session_id}          → 查询会话状态
POST   /api/v1/groupchat/sessions/{session_id}/message  → 追加一条用户消息（不跑 round）
POST   /api/v1/groupchat/sessions/{session_id}/round    → 跑一轮（每个 agent 各发言一次）
POST   /api/v1/groupchat/sessions/{session_id}/complete → 自动跑到 max_rounds 或共识
DELETE /api/v1/groupchat/sessions/{session_id}          → 取消会话
```
Session 状态持久化在 Redis，不再使用 Postgres 表。原本基于 WebSocket 的人对人 ROOM CHAT
已在 2026-05-12 版本中下线（详见 alembic 005）。

### 定时任务
```
GET    /api/v1/schedule         → 定时任务列表
POST   /api/v1/schedule         → 创建定时任务
GET    /api/v1/schedule/{id}    → 获取定时任务
PUT    /api/v1/schedule/{id}    → 更新定时任务
DELETE /api/v1/schedule/{id}    → 删除定时任务
POST   /api/v1/schedule/{id}/run → 立即触发执行
```

### MCP
```
GET    /api/v1/mcp/servers      → MCP Server 列表
POST   /api/v1/mcp/servers      → 添加 MCP Server
PUT    /api/v1/mcp/servers/{id} → 更新 MCP Server
DELETE /api/v1/mcp/servers/{id} → 删除 MCP Server
POST   /api/v1/mcp/servers/{id}/connect → 连接/发现工具
GET    /api/v1/mcp/tools        → 所有 MCP Tool 列表
```

### 环境变量
```
GET    /api/v1/envvars          → 变量列表（值不可见，仅显示 key）
POST   /api/v1/envvars          → 创建变量（value AES-256 加密）
PUT    /api/v1/envvars/{id}     → 更新变量
DELETE /api/v1/envvars/{id}     → 删除变量
```

### Token 用量
```
GET /api/v1/token-usage         → Token 用量汇总（按 Provider/Model/日期）
GET /api/v1/token-usage/daily   → 每日明细
```

### 审批流（Human-in-the-Loop）
```
GET  /api/v1/approvals          → 审批请求列表
GET  /api/v1/approvals/{id}     → 获取审批详情
POST /api/v1/approvals/{id}/decide → 审批决策（approve / reject）
```

### 审计日志
```
GET /api/v1/audit               → 审计日志列表（支持分页过滤）
GET /api/v1/audit/export        → 导出 SIEM 格式（JSON / CSV）
```

### 备份
```
GET  /api/v1/backup             → 备份记录列表
POST /api/v1/backup             → 触发本地备份
GET  /api/v1/backup/{id}/download → 下载备份文件
DELETE /api/v1/backup/{id}      → 删除备份
```

### 系统配置
```
GET  /api/v1/config/export      → 导出全系统 JSON 配置
POST /api/v1/config/import      → 导入配置
```

### Master Agent 配置
```
GET /api/v1/master-config       → 获取 Master Agent 全局配置
PUT /api/v1/master-config       → 更新配置（model/temperature/prompt）
```

### N8N 集成
```
GET    /api/v1/n8n/configs      → N8N 实例配置列表
POST   /api/v1/n8n/configs      → 添加 N8N 实例
PUT    /api/v1/n8n/configs/{id} → 更新配置
DELETE /api/v1/n8n/configs/{id} → 删除配置
POST   /api/v1/n8n/configs/{id}/test → 测试连通性
GET    /api/v1/n8n/configs/{id}/workflows → 列出工作流
POST   /api/v1/n8n/configs/{id}/workflows → 创建工作流
POST   /api/v1/n8n/generate     → LLM 生成 N8N 工作流 JSON（不自动部署）
```

### 任务状态
```
GET /api/v1/tasks               → Celery 任务状态列表
GET /api/v1/tasks/{task_id}     → 获取任务状态
```

### Prompt 模板库（migration 007）
```
GET    /api/v1/prompt-templates             → 列表（可按 ?category= 过滤）
POST   /api/v1/prompt-templates             → 创建
GET    /api/v1/prompt-templates/{id}        → 获取
PUT    /api/v1/prompt-templates/{id}        → 更新
DELETE /api/v1/prompt-templates/{id}        → 删除
```
category ∈ {`system`, `intent_parser`, `summarizer`, `general`}。启动时按 name 幂等
seed 9 条常用模板（Pentest Auditor、SOC L2、IR Coordinator、Vuln Triage 等）。

### Webhook（双向，migration 006）
```
GET    /api/v1/webhooks                       → Webhook 列表
POST   /api/v1/webhooks                       → 创建（direction=incoming|outgoing）
PUT    /api/v1/webhooks/{id}                  → 更新
DELETE /api/v1/webhooks/{id}                  → 删除
POST   /api/v1/webhooks/{id}/regenerate-token → 重置 incoming token（仅 incoming）
POST   /api/v1/webhooks/{id}/test             → 触发一次测试 POST（仅 outgoing）
POST   /api/v1/webhooks/incoming/{token}      → 公网接收端（无需鉴权，按 token hash 查表）
```
- Incoming: token 仅在创建/regenerate 时明文返回一次；DB 中存 SHA-256 hash
- Outgoing: 订阅 `outgoing_events` (e.g. `["approval.required"]`)，事件触发时并发 POST 到 `outgoing_url`，可选 HMAC-SHA256 `X-CyberGuard-Signature` 头
- 内置事件：`approval.required`（高危操作创建 ApprovalRequest 时触发）

### 治理 / GRC（migration 008-009）
```
# Frameworks（控制目录）
GET    /api/v1/governance/frameworks                       → 列表
GET    /api/v1/governance/frameworks/{id}                  → 详情（含 requirements）
GET    /api/v1/governance/frameworks/{id}/requirements     → 要求清单
POST   /api/v1/governance/frameworks/import                → 导入 JSON 格式自定义框架
DELETE /api/v1/governance/frameworks/{id}                  → 删除（若被审计引用则 409）

# Assessments（一次审计实例）
GET    /api/v1/governance/assessments                      → 列表（含 progress 统计）
POST   /api/v1/governance/assessments                      → 创建（自动为可评估 req 建 RA 行）
GET    /api/v1/governance/assessments/{id}                 → 详情
PUT    /api/v1/governance/assessments/{id}                 → 更新
DELETE /api/v1/governance/assessments/{id}                 → 删除
GET    /api/v1/governance/assessments/{id}/requirements    → 列出每条 req 的 assessment

# Requirement assessments + Evidence
PUT    /api/v1/governance/req-assessments/{id}                       → 更新 status/score/observation
POST   /api/v1/governance/req-assessments/{id}/evidence              → 新增证据（kind=text|url|file）
DELETE /api/v1/governance/evidence/{id}                              → 删除证据

# AI 辅助
POST   /api/v1/governance/req-assessments/{id}/ai-suggest-evidence   → LLM 列出建议证据
POST   /api/v1/governance/req-assessments/{id}/ai-assess             → LLM 判定合规状态（preview/apply）
POST   /api/v1/governance/assessments/{id}/ai-report                 → LLM 生成 markdown 审计报告
```
启动时 seed ISO/IEC 27001:2022 Annex A（93 控制 / 514 typical_evidence 条目）和
NIST CSF 2.0（106 subcategories / 547 typical_evidence 条目）。每次启动按 urn 匹配
**无条件覆盖**内置框架的 `typical_evidence`，方便维护者改清单后重启即生效。

### 健康检查
```
GET /health         → Liveness probe（仅检查进程存活）
GET /health/ready   → Readiness probe（检查 PostgreSQL + Redis）
GET /health/started → Startup probe
```

## 3. WebSocket

当前版本无 WebSocket 端点。原本的 `/ws/groupchat/{room_id}` 人对人房间聊天已在
2026-05-12 版本中删除——单 operator 部署场景下没有实际用途，多 Agent 协作改用上面的
REST + Redis 会话方案。

## 4. 安全与中间件

- 所有请求经过 `audit_middleware`（`app/main.py`）记录 HTTP 操作到 `audit_logs` 表
- Chat 接口集成 `check_prompt()` 进行 prompt injection 检测
- Rate limiting 通过 `rate_limit_dependency()` FastAPI 依赖注入（Redis 滑动窗口，30 req/min，500 req/h，5 并发）
- 全局异常处理器屏蔽内部错误细节，生产环境只返回 500 generic message
