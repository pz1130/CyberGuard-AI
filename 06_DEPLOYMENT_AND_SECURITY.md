# 部署与安全细节

## 1. Docker Compose 核心服务

`docker-compose.yml` 中定义的服务：

| 服务 | 说明 |
|------|------|
| `api` | FastAPI + LangGraph 主应用（端口 8000） |
| `webui` | React/Vite 前端（Nginx，端口 3000） |
| `postgres` | PostgreSQL 16（端口 5432） |
| `redis` | Redis 7（端口 6379，密码保护） |
| `celery_worker` | Celery worker，4 并发，处理后台任务 |
| `flower` | Celery 任务监控 UI（端口 5555，可选） |

Sub-Agent 容器可选，用户可在本地独立部署后，在 WebUI 的 Sub-Agent 管理页面配置端点 URL。

**Kubernetes** 部署清单位于 `k8s/` 目录（namespace、configmap、secret、deployment、service、ingress、HPA）。

## 2. 环境变量（.env）

```dotenv
# 必填 - 安全密钥（两者都必须设置，不能使用默认值）
ENCRYPTION_KEY=<32字节 hex AES 密钥，用于加密 API keys / env vars>
SECRET_KEY=<JWT 签名密钥>

# 数据库
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/cyberguard

# Redis
REDIS_URL=redis://:password@redis:6379/0
REDIS_PASSWORD=<Redis 密码>

# CORS
CORS_ORIGINS=["http://localhost:3000","https://your-domain.com"]

# Master Agent 默认配置（可被 DB 中的 master_agent_config 表覆盖）
MASTER_AGENT_MODEL=gpt-4o
MASTER_AGENT_TEMPERATURE=0.7

# Sub-Agent 配置
SUB_AGENT_TIMEOUT=30
SUB_AGENT_MAX_RETRIES=2

# 运行模式
ENVIRONMENT=production  # development | production
MOCK_MODE=false         # true = 不调用真实 LLM，全部返回 mock 响应（演示用）
AUTO_APPROVE=false      # true = 跳过 Human-in-the-Loop（仅开发/测试用）

# LLM Provider 配置（可选 - 也可在 WebUI 的 Providers 页面配置）
LITELLM_CONFIG={"providers": [{"name": "openai", "api_key": "sk-...", "base_url": "https://api.openai.com/v1", "models": ["gpt-4o"]}]}

# JWT
ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24小时

# OpenTelemetry（可选）
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=cyberguard
OTEL_TRACES_SAMPLER=parentbased_always_on  # always_on | traceidratio | parentbased_always_off
```

## 3. 通信方式

- **前端 → 后端**: HTTP REST + WebSocket，Nginx 反向代理
- **后端 → Sub-Agent（远程）**: HTTP（初期不加密，生产环境可通过 Nginx 加 HTTPS）
- **后端 → Redis**: Redis 协议（明文，建议内网隔离）
- **后端 → PostgreSQL**: asyncpg（明文，建议内网隔离）
- **Celery Worker → Broker**: Redis
- **OpenTelemetry**: OTLP/gRPC 到 collector（可选）

## 4. 安全实现清单

### 加密
- [x] 敏感数据全部 AES-256 加密：API Keys（providers.api_key_encrypted）、环境变量（env_vars.value_encrypted）、Sub-Agent 环境变量（agent_configs.env_vars_encrypted）、知识库元数据（knowledge_bases.metadata_encrypted）、MCP token（mcp_servers.auth_token_encrypted）
- [x] AES 密钥由 `ENCRYPTION_KEY` 环境变量管理，不可使用默认值（`app/core/security.py` 强制校验）

### 身份验证
- [x] JWT 认证（HS256），access token（24h）+ refresh token（7d）
- [x] Token 吊销黑名单：Redis sorted set（`token:blacklist`），自动按 TTL 清理
- [x] bcrypt 密码哈希
- [x] 默认 admin 账号首次启动自动创建（username: admin，密码由 `DEFAULT_ADMIN_PASSWORD` 配置）

### 访问控制
- [x] RBAC 角色：admin / operator / analyst / viewer / auditor
- [x] 每个端点通过 `require_permission()` 依赖强制检查角色权限（`app/core/rbac.py`）

### 速率限制
- [x] Redis 滑动窗口：30 req/min、500 req/h（可通过 `RATELIMIT_REQUESTS_PER_MINUTE` / `RATELIMIT_REQUESTS_PER_HOUR` 环境变量调整）
- [x] 并发限制：每用户最多 5 个并行请求（`RATELIMIT_BURST`）

### Prompt 安全
- [x] 5 层 prompt injection 检测（`app/core/guardrails.py`）：
  1. 直接注入模式（instruction override、jailbreak 前缀、recursive injection）
  2. Markup 注入（HTML/XML tags、Markdown links、code fence）
  3. 软拒绝模式（system 伪装、role-play 前缀）
  4. 结构异常评分（Shannon 熵、控制字符比例、高重复率）
  5. LLM 二次分类（可选，对中等风险模糊输入）
- [ ] Sanitization pass（sanitized 字段预留，功能待实现）

### 审计
- [x] 全量 HTTP 请求审计（audit_middleware 中间件）
- [x] Sub-Agent 每次执行记录（含 input/output hash）
- [x] 审计日志可导出（JSON / CSV），支持 SIEM 接入

### Human-in-the-Loop
- [x] 高危操作创建 `approval_requests` DB 记录
- [x] Master Agent 等待 admin 决策（最长 1 小时，超时自动拒绝）
- [x] Admin 通过 REST API 或 WebUI 审批
- [x] `AUTO_APPROVE=true` 可跳过（仅开发/测试环境使用）

### 可观测性
- [x] OpenTelemetry tracing（FastAPI + SQLAlchemy + Celery + LLM calls），可选 OTLP 导出
- [x] 结构化 logging（Python logging 标准库）
- [x] `/health`、`/health/ready`、`/health/started` 三个探针端点（适配 K8s）

### Sub-Agent 隔离
- [x] 每个 Sub-Agent 在独立 Docker 容器中运行（用户自行部署）
- [x] Agent env vars 通过 AES-256 加密存储，执行时解密注入

## 5. 本地快速启动

```bash
# 1. 复制 .env 模板
cp .env.example .env
# 2. 编辑 .env：设置 ENCRYPTION_KEY 和 SECRET_KEY

# 3. 启动所有服务
docker compose up -d

# 4. 运行数据库迁移（首次）
docker compose exec api alembic upgrade head

# 5. 访问 WebUI
open http://localhost:3000
# 默认账号: admin / admin123（首次登录后请立即修改密码）
```

## 6. 生产部署注意事项

1. **必须**修改 `ENCRYPTION_KEY` 和 `SECRET_KEY` 为随机 64 字节 hex 字符串
2. **必须**修改默认 admin 密码
3. 建议在 Nginx 层添加 HTTPS（TLS termination）
4. Redis 和 PostgreSQL 建议只暴露在内网，不对外
5. 建议启用 OpenTelemetry 并接入监控平台（Grafana/Jaeger/DataDog）
6. K8s 部署时使用 `k8s/00-secret.yaml` 管理密钥（不要 hardcode 到 configmap）
