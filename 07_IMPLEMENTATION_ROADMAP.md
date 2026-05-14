# 实施路线图（优先级与里程碑）

> **状态更新（2026-05-14）**: 下方里程碑 1-4 均已完成。Milestone 5 进行中。
> 2026-05 期间额外新增三大模块：Prompt 模板库、双向 Webhook、治理合规（GRC），
> 详见文末"已超出原始路线图的额外功能"小节。

## Milestone 1 - MVP 基础框架 ✅ 已完成
- [x] WebUI 自研 React/Vite/TypeScript 应用 + 所有 Tab 布局（16 个）
- [x] AI Provider 配置（WebUI + API，AES-256 加密存储 API key）
- [x] Master Agent LangGraph 基本状态机（START → PARSE → ROUTE → SUMMARIZE → END）
- [x] JWT 登录认证（access + refresh token + Redis 黑名单）
- [x] Mock 模式（`MOCK_MODE=true`，无需真实 API key 演示）

## Milestone 2 - Sub-Agent 与核心功能 ✅ 已完成
- [x] Sub-Agent 配置管理（WebUI + CRUD API）
- [x] 远程 Sub-Agent 执行（HTTP endpoint）+ 本地 LLM fallback
- [x] Skill / Tool Pool（PostgreSQL 存储，Markdown 内容编辑，WebUI 管理）
- [x] 知识库（文档上传、向量 embedding、cosine 相似度搜索）
- [x] LLM Router：OpenAI-compatible，多 Provider，token 用量追踪

## Milestone 3 - 高级功能 ✅ 已完成
- [x] 实时群聊室（WebSocket + Redis Pub/Sub）
- [x] 定时任务（Celery + Redis broker）
- [x] RBAC 用户管理（5 种角色，per-endpoint 权限检查）
- [x] 对话历史（Conversations API + 本地持久化）
- [x] N8N 集成（自然语言生成工作流 JSON + N8N REST API 管理）
- [x] 环境变量管理（AES-256 加密存储在 DB）
- [x] MCP Server 管理（stdio/HTTP transport，工具发现）
- [x] Master Agent 全局配置（model/temperature/prompt，WebUI 可调）

## Milestone 4 - 安全与运维 ✅ 已完成
- [x] AES-256 加密（API keys、env vars、MCP tokens、知识库元数据）
- [x] 审计日志（全量 HTTP + agent execution，带 input/output hash）
- [x] Token 消耗监控（每次 LLM 调用自动记录，WebUI 可视化）
- [x] Human-in-the-Loop 审批流（DB 持久化，等待 admin 决策，最长 1 小时）
- [x] Prompt Injection 防护（5 层检测，`app/core/guardrails.py`）
- [x] Redis 滑动窗口速率限制（per-user，分钟/小时/并发三重限制）
- [x] OpenTelemetry 链路追踪（FastAPI + SQLAlchemy + Celery + LLM spans）
- [x] K8s 部署清单（`k8s/` 目录：namespace/configmap/secret/deployment/service/ingress/HPA）
- [x] 备份（本地文件下载）

## Milestone 5 - 优化与交付（进行中）
- [x] 配置导出 JSON（`/api/v1/config/export`）
- [x] 健康检查端点（liveness/readiness/startup 三探针）
- [x] 冒烟测试（`tests/test_smoke_api.py`）
- [ ] S3 / 阿里云 OSS 备份（API 预留，未实现）
- [ ] 邮件通知（定时任务完成 / 高危审批提醒）
- [ ] Sub-Agent 执行结果流式输出（当前为 batch）
- [ ] Sanitization pass（guardrails 中 `sanitized` 字段占位，未实现内容过滤）
- [ ] 完整集成测试套件
- [ ] 部署指南文档

## 已超出原始路线图的额外功能

以下功能在原始设计文档中未规划，但已实现：

| 功能 | 说明 |
|------|------|
| N8N 集成 | 自然语言 → N8N 工作流 JSON，并直接管理 N8N 实例 |
| osint / n8n_workflow agent_type | 意图路由新增两个类型 |
| OpenTelemetry | 完整 OTLP tracing，覆盖 HTTP/DB/LLM/Celery |
| JWT refresh token + Redis 黑名单 | 比原设计更完善的 token 管理 |
| Master Agent Config 动态配置 | 运行时调整 model/temperature/prompt 无需重启 |
| `<think>` 标签过滤 | LLM Router 自动剥离 reasoning 模型的思考标签 |
| MOCK_MODE | 无 API key 情况下完整演示所有 UI 功能 |
| AUTO_APPROVE | 开发/测试环境跳过 Human-in-the-Loop |
| 对话历史持久化 | Conversations CRUD API + WebUI |
| Provider 预置种子数据 | 生产启动时自动填充默认 Provider 配置 |
| Prompt 模板库 | 系统 prompt 复用，9 条 cyber-ops 默认模板，Chat 下拉填入（migration 007） |
| 双向 Webhook | Incoming token+SHA256 / Outgoing HMAC-SHA256 / 订阅 `approval.required` 等事件（migration 006） |
| 治理 / GRC 模块 | Framework + Requirement 树 + ComplianceAssessment + Evidence；预置 ISO 27001 + NIST CSF 2.0；AI 建议证据 / 判定状态 / 生成审计报告（migration 008-009） |
| pgvector 知识库 | 替换原 in-process cosine 相似度搜索；按 KB 配置 1536 / 3072 维（migration 003-004） |
| PDF / DOCX 文档摄取 | 知识库自动解析多种文档格式上传 |
| OpenClaw 单 prompt 上线 | sub-agent 上线流程简化为单 prompt 加 key 旋转 |
