# WebUI 页面结构与交互流程

## 技术栈

- **框架**: React 18 + Vite + TypeScript（**非 OpenWebUI fork，完全自研**）
- **样式**: 纯 CSS 变量 + CSS-in-JS inline styles，无 Tailwind/Material UI
- **设计风格**: 深色 cyberpunk 终端风，monospace 字体，绿色 accent
- **国际化**: i18next（中英文切换，`src/i18n/zh.json` + `src/i18n/en.json`）
- **API 客户端**: `src/api/client.ts`（axios 封装，自动携带 JWT）
- **WebSocket**: 原生 WebSocket（群聊）

## 左侧边栏 Tab（实际实现，共 16 个）

### CORE 分组
1. **聊天**（Chat）— 与 Master Agent 对话，支持选择 Provider/Model

### AGENTS 分组
2. **Sub-Agent 管理**（Agents）— 创建/编辑/删除 Sub-Agent 配置
3. **AI Provider 配置**（Providers）— 添加 LLM Provider（API key 加密存储）

### FEATURES 分组
4. **Skill Pool**（Skills）— Skill + Tool Pool 统一管理，Markdown 内容编辑
5. **知识库**（Knowledge）— 上传文档、向量搜索
6. **群聊室**（Group Chat）— 实时多 Agent 讨论（WebSocket）
7. **N8N**（N8N）— N8N 工作流管理 + LLM 生成工作流

### OPS 分组
8. **定时任务**（Schedule）— Celery 定时任务管理
9. **MCP**（MCP）— MCP Server 管理和工具发现
10. **环境变量**（Env Vars）— AES-256 加密的环境变量管理
11. **安全**（Security）— RBAC 与安全配置
12. **Token 消耗**（Token Usage）— 按 Provider/Model/日期统计
13. **备份**（Backup）— 本地备份下载管理
14. **审计日志**（Audit Logs）— 完整操作记录查询
15. **用户管理**（Users）— RBAC 用户管理
16. **设置**（Settings）— Master Agent 配置（model/temperature/prompt）

> **注意**: 没有独立的 "Tool Pool" Tab——Skills 和 Tools 在同一个 Skills 页面中通过类型筛选区分。

## 右上角固定元素（Header）

- CyberGuard logo + 渐变绿色品牌色
- 中文 / English 切换按钮
- 深色 / 浅色主题切换
- 当前用户信息 + 退出登录

## 登录页面

- `src/pages/Login.tsx`
- 用户名 + 密码表单
- POST `/api/v1/auth/login` → 获取 JWT token，存储在 localStorage

## 关键页面交互流程

### 聊天（Chat.tsx）
- 左侧 Provider / Model 选择器（下拉，动态从 `/api/v1/providers` 加载）
- 支持对话历史保存（Conversations API）
- 发送消息 → POST `/api/v1/chat` → 流式或批量响应展示
- Markdown 渲染（代码块高亮）

### Sub-Agent 管理（Agents.tsx）
- 列表展示所有 Agent（显示 backend_type、permission_level、状态）
- 新建/编辑弹窗：填写名称、端点 URL、系统 Prompt、关联 Skills、Provider 等
- 可手动触发执行（POST `/api/v1/agents/{id}/execute`）

### AI Provider 配置（Providers.tsx）
- 新增 Provider 弹窗：填写名称、类型、API Key、Base URL、模型列表
- API Key 不可见（后端 AES-256 加密，前端只显示掩码）
- 测试连通性按钮
- 保存后自动出现在聊天页面的 Provider 选择器中

### 群聊室（GroupChat.tsx — 多 Agent 圆桌讨论）
- 左侧勾选要参与的 sub-agent，主区写初始 prompt + 选 `max_rounds`
- 点击 START DISCUSSION → REST `POST /api/v1/groupchat/sessions` 创建会话并自动跑首轮
- 每轮调用 `/sessions/{id}/round` 让每个被选 agent 各发言一次；AUTO 按钮一键跑到 max_rounds
- 用户气泡 = 绿色 accent，agent 气泡 = 青色 cyan；按时间顺序展开
- 会话状态走 Redis，无 WebSocket（原本基于 WebSocket 的人对人 ROOM CHAT 已于 2026-05-12 下线）

### N8N（N8N.tsx）
- N8N 实例配置管理（地址 + API Key）
- 自然语言描述 → 点击"生成工作流" → LLM 返回 JSON，可直接部署到 N8N
- 列出/启用/删除已有工作流

### Human-in-the-Loop（触发时弹窗）
- 高危操作触发时，弹出审批弹窗（从 `/api/v1/approvals` 轮询）
- 显示操作描述、风险等级、请求 ID
- Admin 可批准/拒绝并填写备注

### Token 消耗（TokenUsage.tsx）
- 按 Provider 和模型分组，展示 prompt/completion/total tokens
- 日期范围筛选

## 侧边栏 Sidebar 实现细节

`src/components/Sidebar.tsx`：
- 固定左侧，顶部显示版本标签（`CYBERGUARD OS v1.0.0` + `ACTIVE` 状态徽章）
- 按分组（CORE / AGENTS / FEATURES / OPS）渲染导航按钮
- 激活 Tab 用左边框高亮 + accent 颜色
- 底部显示静态系统状态（SYS / MEM / UPTIME）
