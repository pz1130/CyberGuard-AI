# 09 · 连接态（connected）协议基线

状态：**可选能力的协议基线** · 方向待按 DEC-025 重写

> ## ⚠️ 定位已变更（DEC-022 / DEC-025）
>
> **本协议是可选的。** 桌面端在 `standalone` 下完整可用，不依赖本文任何端点（INV-37）。本文描述的是 `connected` 运行态——即客户已部署 CyberGuard 服务端并选择配对时的增强能力。
>
> **交互方向已反转。** 原文按"服务端派单 → 节点执行 → 上报"编排（继承自 OpenClaw）。standalone-first 之后，**任务由用户在本地发起，节点是主动方，服务端是策略与存证的提供方**。因此：
>
> | 原要素 | 新形态 |
> |---|---|
> | §4 任务状态机、§5 poll 派单 | **基本不需要**，待重写 |
> | §6 manifest 下发工具/技能 | 降为可选叠加（standalone 自带内置集） |
> | §8 report | 保留，语义从"任务结果回报"改为**审计事件上报** |
> | §7 heartbeat 控制通道 | 保留（L3 远程控制） |
> | §9 episodic recall | 保留，与本地库结果**合并**而非替代 |
> | `execute-tool` 代执行 | 保留但可选——价值是"服务端能到而节点到不了的网络位置" |
>
> **需新增的两章**：策略拉取（L1 收紧，取本地与服务端更严者）、审批上收（本地确认升级为服务端审批队列）。
>
> 重写前，下文的**字段结构、幂等约束、凭据边界、离线队列**仍然有效，可直接沿用。

---

## 1. 目标与边界

Gateway 只负责控制面和审计面（**且仅在 connected 下存在**）：

- 派发任务、下发非敏感能力描述、接收状态和结构化结果；
- 提供远程 abort / steer / pause 控制；
- 提供组织经验的只读召回；
- 不传输完整本地会话、原始证据或 Provider 原始密钥。

节点与服务端之间只有出向 HTTPS。节点不监听端口，不接受 LAN 自动发现或 P2P 连接（INV-07 / INV-09）。

**服务端策略只能收紧不能放宽**，与本地策略取更严者；**不得要求上传全量会话**（L2 明确不做）；**脱管由服务端按心跳超时判定**——不依赖节点主动上报断开（INV-41 / DEC-023）。

## 2. 身份与注册

### 2.1 初始注册

节点由管理员在服务端创建 `backend_type=desktop` 的 AgentConfig，获得一次性 provisioning secret。安装向导把 secret 写入 Electron `safeStorage` / macOS Keychain，之后只发送 `X-Api-Key`，不写入配置文件、localStorage 或日志。

Provisioning secret 只显示一次。服务端只保存 hash；节点不得把 secret 回报给服务端。

### 2.2 轮换与撤销

服务端必须支持：

- 管理员主动轮换；
- 节点重新配对；
- AgentConfig 停用后立即拒绝所有 Gateway 请求；
- 轮换完成前旧 key 可短暂并行，完成后旧 key 立即失效；
- 轮换、撤销、重新配对全部写入服务端审计。

M3 继续兼容 `X-Api-Key`。后续如引入短期 session token，不得改变“节点不监听端口”和“密钥只在 Keychain”的约束。

## 3. 通用约束

所有 JSON 请求必须包含：

```json
{
  "protocol_version": "desktop.v1",
  "node_id": "stable-node-id",
  "request_id": "uuid"
}
```

服务端返回 `protocol_version`、`request_id` 和 `server_time`。未知的必需版本或能力必须显式失败，不得静默按旧语义执行。

所有写操作必须支持 `request_id` 幂等。网络超时后节点可以重试，但服务端不得重复创建任务、重复记录 report 或重复执行控制命令。

## 4. 任务状态机

```text
pending → delivered → running → completed
                              ├→ failed
                              ├→ aborted
                              └→ paused → running
```

以下规则固定：

- 节点 poll 成功后才允许 `pending → delivered`；
- 节点开始 agent loop 才报告 `running`；
- 断网或合盖只能进入 `paused`，不得伪装成 completed；
- abort 是终态；重复 abort 必须幂等成功；
- report 只允许当前节点、当前 message_id 和当前 execution_id 提交；
- 终态不可被后续普通 report 覆盖。

## 5. Poll

```http
GET /api/v1/gateway/poll
X-Api-Key: ...
```

返回：

```json
{
  "protocol_version": "desktop.v1",
  "messages": [
    {
      "message_id": 123,
      "execution_id": "uuid",
      "task": "investigate ...",
      "created_at": "...",
      "policy_snapshot_id": "...",
      "llm_profile_id": "...",
      "manifest_version": "..."
    }
  ],
  "has_manifest": true
}
```

任务正文可以包含调查目标和已批准的约束，但不得包含服务端 Provider 原始密钥或不必要的组织级秘密。

## 6. Manifest

```http
GET /api/v1/gateway/manifest
X-Api-Key: ...
```

Manifest 必须带 `manifest_version`、`issued_at`、`expires_at` 和内容 hash。节点只接受当前 AgentConfig 被批准的版本。

### 6.1 本地工具

本地工具字段至少包括：

```json
{
  "id": 7,
  "name": "nmap",
  "input_schema": {},
  "command": "/usr/local/bin/nmap",
  "fixed_args": [],
  "timeout_seconds": 60,
  "execution_mode": "sequential",
  "action_category": "observe",
  "sandbox_requirements": {
    "network_access": "declared",
    "writable_roots": []
  }
}
```

首版节点不得接收需要 shell 解释的任意命令字符串。可执行文件、固定参数和变量参数必须经过 schema 校验与本地白名单检查。

### 6.2 MCP

首版只下发无密钥 STDIO MCP：

```json
{
  "server_id": 3,
  "name": "local-parser",
  "transport": "stdio",
  "command": "/opt/cyberguard/mcp/local-parser",
  "args": ["--stdio"],
  "binary_sha256": "...",
  "timeout_seconds": 30,
  "tools": []
}
```

不得在 manifest 中出现 `env_vars_encrypted`、auth token、Provider key 或服务端数据库连接信息。带凭据的 MCP 必须使用 `governed` 服务端执行路径。

### 6.3 LLM Profile

```json
{
  "profile_id": "corp-local-1",
  "provider_type": "openai-compatible",
  "base_url": "https://llm.corp.example/v1",
  "models": [{
    "name": "security-model",
    "context_window": 128000,
    "max_output_tokens": 8192,
    "tools": true,
    "vision": false
  }],
  "egress_mode": "local_only",
  "credential_ref": "keychain://cyberguard/provider/corp-local-1"
}
```

`credential_ref` 只是 Keychain 引用，不能是密钥本身。`local_only` 只允许本机或企业内网地址；`approved_remote` 必须由用户显式启用，并产生审计事件和界面告警。

## 7. Heartbeat 与控制

```http
POST /api/v1/gateway/heartbeat
X-Api-Key: ...
```

请求：

```json
{
  "protocol_version": "desktop.v1",
  "node_id": "...",
  "request_id": "...",
  "running": ["execution-id"],
  "paused": [],
  "node_caps": {
    "sandbox_impl": "seatbelt",
    "max_sandbox_mode": "workspace-write",
    "os": "macos",
    "local_tools": ["nmap"],
    "mcp_servers": []
  }
}
```

响应：

```json
{
  "server_time": "...",
  "control": [
    {"execution_id": "...", "op": "abort", "command_id": "uuid"}
  ],
  "kill_switch": false,
  "manifest_version": "..."
}
```

控制命令按 `command_id` 幂等。`abort` 优先级最高；节点收到后必须在 2 秒内进入 aborted 或明确报告无法中断的安全错误。

## 8. Report

```http
POST /api/v1/gateway/report
X-Api-Key: ...
```

```json
{
  "protocol_version": "desktop.v1",
  "node_id": "...",
  "request_id": "...",
  "report_id": "uuid",
  "message_id": 123,
  "execution_id": "uuid",
  "status": "completed",
  "result_summary": "...",
  "error": null,
  "tool_call_log": [
    {"name": "nmap", "args_digest": "sha256:...", "exit_code": 0,
     "duration_ms": 1200, "sandbox_mode": "workspace-write"}
  ],
  "artifacts": [
    {"sha256": "...", "kind": "evidence-index", "size": 1234,
     "retention_days": 30}
  ],
  "policy_events": [],
  "node_attestation": {"sandbox_impl": "seatbelt", "os": "macos"}
}
```

`result_summary`、tool log 和 artifact 元数据不得偷偷扩大为完整会话或原始证据上传。原始证据留在节点；如未来支持上传，必须是独立的、显式批准的加密传输协议。

服务端以 `report_id` 去重，并返回：

```json
{"accepted": true, "report_id": "uuid", "message_id": 123}
```

## 9. Episodic recall

```http
POST /api/v1/gateway/episodic/recall
X-Api-Key: ...
```

请求只包含任务摘要、agent scope、top_k 和 LLM profile；响应只返回经过服务端过滤的成功经验摘要。节点不得提交任意 SQL、embedding 或 agent_id 覆盖值。

节点不直接调用 `agent_episodes`，也不调用写入接口。写入由服务端在最终 report 后完成。

## 10. 重试与离线

- GET poll、manifest、recall 可指数退避重试；
- heartbeat 可重试，但同一 `request_id` 不重复应用控制命令；
- report 超时后必须持久化到本地 append-only audit buffer；
- report buffer 有明确上限，达到上限时停止新的高风险任务并显著告警；
- 恢复联网后按序发送，服务端按 `report_id` 幂等；
- 节点显示“已暂停”和待上报数量，不得静默丢失。

## 11. 兼容策略

现有 OpenClaw 节点继续使用旧的 `result: string` report 形态。桌面节点必须声明 `protocol_version=desktop.v1`，服务端不得把旧 OpenClaw 的自由文本字段当成桌面结构化审计。
