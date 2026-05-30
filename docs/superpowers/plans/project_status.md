---
name: project_status
description: CyberGuard platform implementation status — last updated 2026-05-30 (WebUI polish sprint complete; 72 tests green; alembic head 013)
type: project
---

# CyberGuard Project Status — 2026-05-30 (updated)

## ▶ Resume point (next session)

- **Branch:** `main` — all work committed, working tree clean. Latest commit: `c75fb4e`.
- **Tests:** 72 passed, 1 warning (LangChain deprecation, benign). TypeScript: 0 errors.
- **Alembic head:** `013_security_settings`

### Remaining known issues (prioritized)

| 优先级 | 问题 |
|--------|------|
| 🟡 中 | `App.tsx` / `Header.tsx` 用 raw `fetch('/api/v1/auth/me')` 绕过 api client（功能正常，一致性问题）|
| 🟢 低 | LangChain 弃用警告：`JsonPlusSerializer.allowed_objects`，升级依赖时处理 |
| 🟢 低 | GlobalSearch 未覆盖 Users（`api.getUsers()` 存在，可视需求决定是否加）|
| 🟢 低 | Security 页面 `require_mfa` 字段缺失（原 UI 有但后端未实现，重写时去掉）|

---

## Session 2026-05-30 — WebUI 功能补全与 UI 修复

### CTRL+K 全局搜索（12 commits，`544401a` → `3c9a6c1`）

- `webui/src/context/SearchContext.tsx` — 新建 React context，跨页高亮状态（含 `subview?: string` 字段，支持 Governance 子视图切换）
- `webui/src/components/GlobalSearch.tsx` — 命令面板式搜索 modal
  - CTRL+K / Header 点击触发；`App.tsx` 全局 keydown 监听
  - 覆盖 **12 个数据源**（见下表）
  - 缓存 TTL 60s（stale-while-revalidate）
- 全部 12 个页面加了 `data-item-id` + `search-highlight` 闪光动画

| 数据源 | Tab | 图标 |
|--------|-----|------|
| Agents | agents | ◆ |
| Providers | providers | ▣ |
| Skills | skills | ◈ |
| Tools | tools | ◇ |
| Knowledge | knowledge | ◉ |
| MCP Servers | mcp | ◎ |
| Schedule Tasks | schedule | ○ |
| Webhooks | webhooks | ⟳ |
| Governance Frameworks | governance (subview=frameworks) | ▦ |
| Governance Assessments | governance (subview=list) | ▧ |
| Prompt Templates | prompts | ≡ |
| N8N Connections | n8n | ⌥ |

### Chat UI 修复（`43b13c8`, `593e295`）
- CONVERSATIONS 标题高度改为显式 `height:42px`，与右侧 toolbar 对齐
- SESSION/CLEAR 按钮改用 `marginLeft:auto` 分组，不再溢出或换行
- toolbar 移除 `flexWrap:wrap`

### SYS ONLINE → 真实健康检查（`a18aef3`）
- `Header.tsx` 每 30s 轮询 `GET /api/v1/health/ready`（检查 Postgres + Redis）
- 三态显示：`SYS ONLINE`（绿）/ `SYS DEGRADED`（琥珀，503）/ `SYS OFFLINE`（红，连接失败）

### TokenUsage raw fetch 修复（`a18aef3`）
- `client.ts` 新增 `getTokenUsageSummary()`
- `TokenUsage.tsx` 不再手写 fetch + token，改用 api client

### Security 页面完整后端实现（`3912396`）
- `app/models/security_settings.py` — 单行 DB model（id=1）
- `alembic/versions/013_security_settings.py` — 建表 + 默认值
- `app/services/security_settings.py` — get/update，带内存缓存（同 master_config 模式）
- `app/routers/security.py` — `GET/PUT /api/v1/security-settings`（SETTINGS_READ/WRITE 权限）
- `Security.tsx` — 加载真实数据；SAVE 按钮仅在有改动时激活

### Approvals 审批管理页面（`c75fb4e`）
- `api.getApprovals(statusFilter)` + `api.decideApproval(id, decision, comment?)`
- `Sidebar.tsx`：Tab type 新增 `'approvals'`；OPS 组 audit 之后加 ShieldCheck 导航项
- i18n：en=Approvals, zh=审批管理
- `Approvals.tsx`：
  - 过滤 tabs：PENDING / APPROVED / REJECTED / ALL
  - PENDING 视图 15s 自动刷新
  - 风险等级左侧彩色边框（low 绿 / medium 青 / high 琥珀 / critical 红）
  - 每行内联 ✓ / ✗ 快捷按钮（pending 行）
  - 展开面板：元数据、payload JSON（格式化）、注释输入、完整 APPROVE/REJECT 按钮

---

## Milestones

- **M1** — Backend Foundation: FastAPI + Postgres + Celery ✅
- **M2** — LLM Integration: Multi-provider router + intent parsing ✅
- **M3** — Sub-Agent System: external (OpenClaw/Hermes/Custom) + internal (in-app) ✅
- **M4** — WebUI: React + Vite + TypeScript ✅
- **M5** — Agent Collaboration: Multi-agent routing + group chat panel ✅
- **QwenPaw pool alignment** — ① executable Tool pool ✅ · ② unified assignment + tags ✅ · ③ external agents use pools ✅
- **WebUI Polish Sprint** — CTRL+K search + Security backend + Approvals page + health check ✅

---

## Not yet implemented

- S3 / Alibaba OSS backup（API stub 存在，无实现）
- Email notifications（helpers 存在）
- 流式 sub-agent 输出（目前批量）
- Guardrail sanitization（`GuardrailResult.sanitized` 字段预留，未实现）
- OCR for scanned-image PDFs
- Governance evidence 文件上传（`kind=file` schema 存在，UI 未接）
- Scheduled-tasks **执行**：CRUD + model 存在，但无 Celery-beat executor，cron 表达式只存不跑

## Operational notes

- 拉代码后重建：`docker compose build api webui`
- Migration：`docker compose exec api alembic upgrade head`（开发环境 startup 自动跑）
- Approvals 只在 `AUTO_APPROVE=false` 时产生待审批请求；docker-compose 默认 `AUTO_APPROVE=true`
- `test_smoke_api.py` 需要启动服务后单独运行：`python -m unittest tests.test_smoke_api`
