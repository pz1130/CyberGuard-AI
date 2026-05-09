# Sub-Agent 清单、角色定义与 Prompt 模板

## 1. Sub-Agent 路由类型（agent_type）

Master Agent 的意图解析器将用户输入映射到以下 `agent_type`，用于路由到匹配的已注册 Sub-Agent，或回退到本地 LLM 执行器：

| agent_type       | 职责说明                                         |
|------------------|--------------------------------------------------|
| threat_intel     | 威胁情报收集、CVE 查询、IOC 分析、APT 追踪       |
| log_anomaly      | SIEM 日志解析、异常检测、长期行为分析            |
| vuln_scanner     | 漏洞扫描结果分析、CVE 风险评估、漏洞利用分析     |
| remediation      | 修复建议、隔离/封禁操作、行动计划                |
| compliance       | 安全策略合规检查（ISO27001、GDPR、PCI-DSS）      |
| osint            | 开源情报、侦察、资产发现、足迹追踪               |
| n8n_workflow     | 将自然语言描述转为 N8N 自动化工作流 JSON         |
| general          | 不匹配以上任何类型的通用任务                     |

## 2. Sub-Agent 注册与管理

Sub-Agent 通过 WebUI 的 **Sub-Agent 管理** 页面创建和配置，存储在 `agent_configs` 表中。每个 Agent 配置包括：

- `agent_name`：唯一名称
- `backend_type`：`openclaw` / `hermes` / `general`（或自定义字符串）
- `endpoint_url`：远程 Agent 的 HTTP 端点（留空则使用本地 LLM 执行器作为回退）
- `system_prompt`：该 Agent 的专属系统提示词（可通过 WebUI 编辑）
- `provider_id`：使用哪个 AI Provider（可覆盖全局默认）
- `permission_level`：`low` / `medium` / `high`
- `associated_skills`：从 Skill Pool 多选关联的 Skill ID 列表
- `description`、`is_active`、`metadata_json`

> **说明**: 平台初始不预设任何 Sub-Agent。管理员需要在 WebUI 的 Sub-Agent 管理页面手动创建，或通过 API (`POST /api/v1/agents`) 批量导入。

## 3. 每个 Sub-Agent 的系统 Prompt 模板（可通过 WebUI 编辑）

**通用模板结构**（每个 Agent 都可继承/覆盖）：

```
你是 CyberGuard 的专业子 Agent，专注于 {角色}。
你必须：
- 只使用已授权的 Skill 和 Tool
- 所有输出必须结构化（JSON 或 Markdown）
- 遇到高危操作时必须返回包含 "NEED_HUMAN_APPROVAL" 的响应
- 引用知识库时必须带来源标注
```

**Threat Intelligence Agent 推荐 Prompt**：
```
你是威胁情报专家，查询公开威胁情报、CVE、IOC。
输出格式必须包含：风险等级、相关 IOC、建议下一步行动。
```

**Log Anomaly Agent 推荐 Prompt**：
```
你是日志异常检测专家，分析 SIEM 日志和长期行为模式。
输出必须包含：异常类型、置信度、时间线摘要。
```

**N8N Workflow Agent 推荐 Prompt**：
```
你是 N8N 工作流生成专家。根据用户的自然语言描述，生成完整的 N8N 工作流 JSON。
只输出 JSON，不添加 markdown 代码块或额外解释。
```

其余类型的推荐 Prompt 可在 WebUI 的 Sub-Agent 管理页面动态编辑，或通过 `system_prompt` 字段通过 API 设置。

## 4. Skill/Tool 关联规则

每个 Sub-Agent 在创建时可通过 `associated_skills` 字段从 Skill Pool / Tool Pool 中多选关联。关联的 Skill 会注入到 Agent 的上下文或本地执行器的提示词中。

## 5. 本地执行器回退（Local Executor）

当 Sub-Agent 没有配置 `endpoint_url` 时，Master Agent 自动使用本地 LLM 执行器：

- 根据 `agent_type` 选择专属系统提示词
- 调用 LLM Router 完成任务（使用全局默认 Provider 或请求中指定的 `provider_id`）
- 输出格式与远程 Sub-Agent 保持一致（`{status, output, agent_id, execution_time}`）

关键词路由逻辑（无 LLM 可用时的 fallback）：

| 关键词 | 映射到 agent_type |
|--------|-------------------|
| cve, threat, malware, ioc, apt | threat_intel |
| log, siem, anomaly, detection | log_anomaly |
| scan, vuln, exploit, cve | vuln_scanner |
| fix, remediate, patch, block, isolate | remediation |
| policy, compliance, iso, gdpr, pci | compliance |
| osint, recon, footprint | osint |
| n8n, workflow, automate | n8n_workflow |
| (其他) | general |
