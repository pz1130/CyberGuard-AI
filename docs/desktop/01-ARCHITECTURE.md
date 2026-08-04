# 01 · 整体架构

状态：定稿 · 2026-07-27 · 详细规格见 `../superpowers/specs/2026-07-27-desktop-node-design.md`

---

## 1. 产品边界

> ⚠️ **本节已按 DEC-022 / DEC-027 重写。** 早期版本写的是"桌面节点是服务端的执行卫星，不是单机版"，并把 Episodic 经验库划归服务端——**两条都已作废**。

**定位：单兵全能工具。** 面向**没有服务端**的单个安全从业者——独立顾问、中小企业安全负责人、大企业里有 SIEM 有工单但没有平台的个人。一个人既看态势也下场查，**不分角色**。

**standalone 必须自洽完整，connected 只做增强**（INV-37）。

### 为什么价值只对"没有服务端的人"成立

Web 端 21 个 Tab 功能不减。对**已部署** CyberGuard 的客户，桌面端的增量价值接近于零——打开浏览器就有全部审批、GRC、审计。"不用部署"归零、"数据不出本机"不成立（数据本就在服务端）、"本地 MCP"服务端网络位置往往更好。剩下的只有免登录与托盘常驻，撑不起独立形态的开发成本。

### standalone 必备 vs connected 增强

| standalone 必须自己有 | connected 才能提供（原理上单机做不到） |
|---|---|
| 本地经验库、本地会话树、本地审批（标注 `approval_type: self`） | **职责分离审批**（批准者 ≠ 操作者，拓扑决定） |
| 审计哈希链（tamper-evident） | **不可篡改审计**（日志不在被审计者机器上） |
| 带凭据 MCP、本地知识库、Provider 配置 | **跨人共享**（经验、技能、知识、事件上下文） |
| 内置 SOP 技能集、报告生成、态势聚合 | **组织级合规态势**（多部门控制项、跨团队证据） |
| 本地工具执行 + 沙箱、证据浏览器、Plan Mode | **强制策略**（中心下发形成可审计的受控状态） |

> **服务端不是技术必需品，是合规与协作必需品**（DEC-023）。单机版卖生产力，服务端卖可证明的合规性。

### 桌面端能做而 Web 端做不到的

内网段扫描与抓包（服务器路由不到用户所在网段）、本地取证材料（pcap / 内存镜像 / GB 级日志）、MCP STDIO 本地 spawn、终端与文件系统访问、离线环境。

---

## 2. 进程与数据流

```
┌──────────────────── 分析师终端（macOS）────────────────────┐
│                                                            │
│  Electron Main                                             │
│    ├─ 窗口 / 托盘 / 原生通知 / 模态弹窗                      │
│    ├─ sidecar 生命周期（启动 · 健康检查 · 退出清理 · 崩溃重启）│
│    └─ 节点密钥（Electron safeStorage → Keychain）           │
│         ↕ IPC (contextBridge)                              │
│  Electron Renderer                                          │
│    └─ React 单工作台（ui-shared 组件）                       │
│         ↕ JSONL over stdin/stdout ← 不开监听端口             │
│  Python Sidecar（PyInstaller onedir）                       │
│    ├─ agent-core（与服务端同一个包）                         │
│    ├─ 策略引擎（sandbox_mode × approval_policy）             │
│    ├─ 本地会话（树状 JSONL + SQLite 索引）                   │
│    └─ 工具隔离层 → sandbox-exec + .sbpl                     │
│                                                            │
└────────────────────────┬───────────────────────────────────┘
                         ┆ HTTPS · X-Api-Key · 仅出向
                         ┆ **可选**（connected，M6 按需）
                         ┆ 策略拉取 / 审批上收 / 审计上报 / 经验同步 / 控制通道
┌────────────────────────▼───────────────────────────────────┐
│  CyberGuard 服务端（现有，独立产品线）                        │
│  职责分离审批 · 不可篡改审计 · 跨人共享 · 组织视图 · 强制策略   │
└────────────────────────────────────────────────────────────┘
```

> 虚线表示**可选**：standalone 下这条链路不存在，产品仍然完整（INV-37）。

三个进程边界，三条不同性质的通道：

**Main ↔ Renderer**：标准 Electron IPC，`contextIsolation: true`、`nodeIntegration: false`，只经 `contextBridge` 暴露白名单方法。

**Renderer ↔ Sidecar**：JSONL over stdin/stdout。选它而非 localhost HTTP 是安全决策——**同机其他进程无法连接，随机 token 鉴权这个问题从存在性上消失**。对一个跑在有域凭据的员工终端上、能执行 shell 的产品，这个差别是实质性的。

**Sidecar ↔ 服务端**：HTTPS 出向，`X-Api-Key`。节点**不监听任何端口**，服务端无法主动推送，控制指令搭 heartbeat 响应回传。LLM 默认由 sidecar 通过节点允许的 Provider 调用；原始 Provider 凭据不经 Gateway 下发。

---

## 3. 复用现有 Gateway 协议

`app/routers/gateway.py` 提供了 OpenClaw 节点协议骨架；桌面节点复用其鉴权和任务模型，但不能把当前协议当作完整的桌面协议。桌面接入前必须按 `09-GATEWAY-PROTOCOL.md` 扩展 report、heartbeat、LLM capability、MCP manifest 和 episodic recall。

**权威字段以 `09-GATEWAY-PROTOCOL.md` 为准**，下表只说明改动性质。所有请求均须携带 `protocol_version` / `node_id` / `request_id`，写操作须幂等——**没有任何端点是原样可用的**。

| 端点 | 改动性质 |
|---|---|
| `GET /gateway/poll` | 扩展：任务项加 `policy_snapshot_id` / `llm_profile_id` / `manifest_version` |
| `GET /gateway/manifest` | **重构**：加版本 + 有效期 + 内容 hash；本地工具改为结构化命令（可执行文件 + 固定参数 + 沙箱声明）；新增 LLM Profile 与无密钥 STDIO MCP |
| `POST /gateway/execute-tool` | 沿用（`governed` 工具的服务端代执行），加通用字段与幂等 |
| `POST /gateway/report` | **重构**为结构化上报（状态机 / tool_call_log / artifacts / policy_events / node_attestation），按 `report_id` 去重 |
| `POST /gateway/heartbeat` | **重构**为双向控制通道（`node_caps` 上报 + `control` 指令下发），控制命令按 `command_id` 幂等 |
| `POST /gateway/episodic/recall` | **新增**：组织经验只读召回（DEC-019） |

> 早期版本曾表述为"服务端主体零改动"——**已不成立**。桌面协议是 `desktop.v1`，与 OpenClaw 的最小协议并存但不混用（DEC-020、09 §11）。

治理字段已在 `AgentConfig` 齐备，节点直接消费，不新建表：`autonomy_tier`、`allowed_categories`、`auto_execute_min_confidence`、`escalate_to_human_below`、`pii_handling_policy`、`kill_switch_enabled`、`requires_approval_rules`、`governed`。

### 两级工具执行

manifest 里 `command_template=None if agent.governed else t.command_template` 已经实现了关键二分，桌面节点直接沿用：

- **本地执行**——只在节点上有意义的工具（本地扫描、文件解析、MCP STDIO）。在沙箱内跑，结果与 `policy_events` 上报。
- **服务端代执行**——`governed=true` 的工具。节点只发 `/gateway/execute-tool`，执行与审批全在服务端。适合需要中心凭据或中心审计的动作。

**这条边界是产品安全性的核心，不要模糊掉。**

---

## 4. 共享代码的三个包

参照 pi 的四层划分（`pi-ai` / `pi-agent-core` / `pi-coding-agent` / `pi-tui`）——每层独立可用，UI 层对其余包零依赖。

### 分层规则：管依赖方向，不管调用深度

**强制的是依赖方向单向向上、无循环**——底层永远不知道上层的存在。

**不强制"上层只能引用相邻下层"。** `apps/desktop` 可以直接 import `llm-router` 的原子类型，不必经 `agent-core` 转发——某些基础类型本就该统一在一个地方。pi 的文档明确把"严格分层"列为要避开的反模式，照做会得到一个层层转发的类型地狱。

**类型逐层扩展，不修改底层**：底层定义原子类型（`Tool` / `Message` / `Model`）→ 中层扩展（`AgentTool` 加 `execute` 与 `execution_mode`）→ 上层再扩展（加 UI 渲染、权限、prompt 片段）。每层只加自己需要的。

### `packages/llm-router`（Python）

纯 Provider 抽象：`chat` / `stream_chat` / `embed`、重试退避、限流、能力探测、模型元数据（`context_window` / `max_output_tokens`）。**不含任何 agent 概念。**

现有 `llm_router.py`（944 行）混了两类东西——纯路由能力，与 `parse_intent` / `generate_summary` / `build_chat_system_prompt` 这类**业务语义**方法。后者属产品层，桌面节点用不到，**留在 `app/`**。

> 模型元数据不是可选项：设计中"压缩阈值按剩余预算而非绝对值"（`contextTokens > contextWindow - reserveTokens`）依赖 `context_window` 字段。没有它只能继续写死 8000 / 24000，换个模型不是浪费就是必炸。

### `packages/agent-core`（Python）

服务端与节点共用的 agent 内核。**不认识 Postgres / Redis / Celery / FastAPI**，只认识四个端口：

| 端口 | 服务端实现 | 节点实现 |
|---|---|---|
| `Store` | Postgres + SQLAlchemy | 树状 JSONL 文件 + SQLite 索引 |
| `VectorIndex` | pgvector | **本地向量库**（standalone 必须自建；connected 时叠加服务端召回。反转自原设计，见 INV-11 / DEC-022） |
| `TaskQueue` | Celery + Redis | APScheduler |
| `Bus` | Redis pub/sub | 进程内 asyncio 原语 |

进包的代码：`internal_agent.py` 的 `_run_loop` 及守卫逻辑、`context_compressor.py`、`llm_router.py`、`tool_executor.py` 的调度部分、`episodic_memory.py` 的接口层。

**不用碰**：`app/routers/*`、`app/models/*`、governance、webui。

> 现有那三个 adapter（`_KSAdapter` / `_SearchAdapter` / `_EpisodicAdapter`）注释写着 "Mockable from tests via monkeypatch"，已是端口思维雏形——只是各自 `AsyncSessionLocal()` 开 session，半只脚踩在 Postgres 上。正式化即可，不是从零设计。

**为什么必须复用而不是节点侧重写**：`_run_loop` 里的循环守卫参数指纹归一化（`sort_keys=True`）、预算耗尽时撤工具而非报错、反思器两次纠偏上限、压缩时丢弃孤儿 tool 消息——每一条背后都是一次线上问题。重写等于把这些全部归零，然后一条条重新踩回来，且不知道漏了哪几条。

### `packages/ui-shared`（TypeScript）

Web 后台与桌面端共用：聊天气泡、Markdown 渲染、Monaco、i18n 词条、主题、API client 类型。

**不得依赖任何 agent 概念**（参照 pi-tui 对其余 pi 包零依赖）——纯展示层，业务状态由各自应用层注入。

路由与布局各自独立——Web 端是 21-Tab 后台，桌面端是单工作台。这样避免桌面端演化成一份快速腐化的 fork。

### 策略管线与审计事件：两套机制，不得合并

参照 pi 的划分——**管线钩子有干预能力，事件系统是纯观察**。混为一谈会导致要么审计能篡改结果，要么策略无法拦截。

**策略管线**（五步，可否决）

```
prepare_arguments → validate_arguments → before_tool_call → execute → after_tool_call
                    ↑ schema 校验         ↑ 可阻断                    ↑ 可脱敏/改写
```

沙箱决策、Plan Mode 拦截、kill switch、权限继承校验（INV-21）挂 `before_tool_call`；`pii_handling_policy` 落到 `after_tool_call`——这个字段现在在调用链上层层透传却没有统一执行点。

现在的治理检查是散的：`_dispatch` 的四路分支、`tool_executor` 的 governance、`run_task` 的 kill switch。将来还要加更多，继续散下去必漏。统一后**可以静态验证"每条路径都过了策略检查"**——安全评审的硬通货。见 INV-28。

**审计事件**（四层，纯观察）

`agent` / `turn` / `message` / `tool_execution`，每层 start → update → end。订阅者**不可否决、不可修改**。

**emit 必须 await**，按订阅顺序逐一等待——审计落盘后才继续下一步。fire-and-forget 的审计是个洞：任务已经推进，审计可能从未写入。见 INV-29。

### Operations 抽象：两级工具执行的实现方式

工具不直接调系统 API，而依赖最小接口（`ReadOperations` / `ExecOperations` / `EditOperations`），每个工具只声明所需方法。

**这条直接解决 §3 的两级工具执行**：同一份工具代码，本地沙箱执行与 `governed` 服务端代执行**只是换一个 Operations 实现**，不必像现在 `_dispatch` 里 if/elif 分四路各写各的。

副作用是 INV-18（两级边界不得模糊）从"靠代码走查"升级为"靠类型系统保证"——节点侧不注入本地 `ExecOperations`，`governed` 工具在类型层面就无法本地执行。

---

## 5. 桌面端界面形态

分析师在节点上只做一件事——**调查**。配置管理、治理审计、用户权限留在 Web 端。所以是**单工作台**，不是多标签后台。

```
┌─ 节点状态栏 ────────────────────────────────────────────────┐
│ ● 已连接 │ 沙箱: seatbelt │ TCC: 已授权 │ Profile: 日常调查 │ 待上报 3 │
├──────────┬─────────────────────────────┬───────────────────┤
│ 会话树    │  对话流 / 执行流              │  上下文面板         │
│          │                             │  ├ 当前 Plan       │
│ ├ 调查 A  │  [用户] 排查 10.1.2.0/24     │  ├ 工具状态         │
│ │ ├ 分支1 │  [Plan] 4 步 · 待批准 →      │  └ 已挂载证据       │
│ │ └ 分支2 │  [执行] nmap ▶ 流式输出…     │                   │
│ └ 调查 B  │                             │                   │
├──────────┴─────────────────────────────┴───────────────────┤
│ 托盘常驻 · 系统原生通知                                       │
└─────────────────────────────────────────────────────────────┘
```

五个新界面（规格见 spec §3.6.3）：Plan 审阅面板、实时执行视图、节点状态栏、审批弹窗与提权申请、证据浏览器。

现有 21 个模块的取舍见 spec §3.6.2。要点：聊天 / MCP / 工具池 / 技能池 / 设置 / Token 消耗进桌面端；用户管理、GRC、审批队列、完整审计日志、Webhook、N8N、定时任务、群聊室不进。

---

## 6. 首发平台 macOS 的架构影响

**TCC 权限**：macOS 要求访问 `~/Desktop`、`~/Documents`、`~/Downloads`、外接卷前获得授权，否则**读取静默失败**。对取证工具是致命体验问题——分析师把 pcap 放下载目录，agent 报"文件不存在"。首启必须引导授予完全磁盘访问，状态栏常显授权状态。

**抓包权限**：`/dev/bpf*` 默认不可读（Wireshark 装 ChmodBPF 的原因）。首版把抓包类工具标为 `governed` 走服务端代执行，**不装特权守护进程**——那会大幅抬高安全评审门槛，不值得在 M1 付这个成本。

**沙箱**：`sandbox-exec` + `.sbpl`，路径**硬编码 `/usr/bin/sandbox-exec`，不走 PATH 查找**（防 PATH 注入）。该接口被标记 deprecated 多年但仍是 Chrome、codex 在用的方案，短期可靠；放在端口接口后，为将来切换 Endpoint Security Framework 留余地。

**签名公证**：必须 Hardened Runtime + notarization。与 PyInstaller、子进程 spawn 有冲突，需申请 `allow-unsigned-executable-memory` 等 entitlements——这些**本身会削弱应用自身完整性保护**，须在安全评审材料中主动披露。
