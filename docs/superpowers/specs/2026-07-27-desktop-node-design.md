# CyberGuard 桌面节点技术方案

状态：**详细规格（部分条目已被上层决策取代）** · 2026-07-27

> ## ⚠️ 权威性说明
>
> 本文是**详细规格**：协议字段、界面规格、平台细节以此为准。
>
> 但**架构决策、里程碑、不变量以 `docs/desktop/` 为准**。本文写于早期，后续多轮决策未全部回灌，如遇冲突：
>
> | 主题 | 权威来源 |
> |---|---|
> | 架构与包划分 | `docs/desktop/01-ARCHITECTURE.md` |
> | 技术选型 | `docs/desktop/02-TECH-STACK.md` |
> | 里程碑与出口判据 | `docs/desktop/03-ROADMAP.md` |
> | 不变量与设计哲学 | `docs/desktop/04-INVARIANTS.md` |
> | 已定决策 | `docs/desktop/05-DECISIONS.md` |
>
> 已知本文被取代的条目：§4.1 包划分（现为两个包，见 DEC-014）、§5 子 agent 工作区隔离（已改判，见 DEC-012）、§7 里程碑（M0a 已拆分）。

---

## 0. 定位

桌面节点**不是** CyberGuard 的单机版，也不是从现有仓库切出来的子集。它是**单仓库内的一个新应用（`apps/desktop/`）+ 一个新的 `backend_type`**，通过已有的 Gateway 协议接入服务端，作用是把 agent 的执行位置从中心服务器搬到分析师的终端上。

> 仓库拓扑为 monorepo，见 DEC-001。本文早期版本写作"新仓库"，已修正。

它存在的唯一理由是：**有些事只能在分析师那台机器上干。**

| 只能在节点侧 | 必须留服务端 |
|---|---|
| 内网段扫描、抓包（服务器路由不到分析师所在 VPN 段） | 审批队列（HITL 的意义在于批准者 ≠ 操作者） |
| 本地取证材料（pcap / 内存镜像 / GB 级日志，传不动也不合规） | WORM 审计链、SIEM 导出（不可篡改的前提是不在被审计者机器上） |
| MCP STDIO（本来就是本地进程协议） | RBAC / SSO / GRC 治理 |
| 终端、文件系统、剪贴板 | 定时任务（笔记本会合盖） |
| 离线 / 涉密内网场景 | 组织级知识库、Episodic 经验库 |

**Episodic memory 明确留在服务端。** 分析师 A 摸索出的有效打法应该让 B 直接召回到——这是相对 pi / codex / grok-build 这类单机 CLI 工具的结构性优势，它们的记忆天然是孤岛。不要主动放弃。

---

## 1. 总体架构

```
┌──────────────── 分析师终端 ────────────────┐
│  Electron 壳（托盘 / 原生通知 / 模态弹窗）    │
│    └─ React WebUI 单工作台（见 §3.6）        │
│         ↕ JSONL over stdin/stdout           │
│  Python sidecar（PyInstaller onedir）        │
│    ├─ agent-core（复用服务端同一个包）        │
│    ├─ 本地会话（树状 JSONL 文件）             │
│    ├─ 策略引擎（sandbox × approval 双旋钮）   │
│    └─ 工具隔离层（Seatbelt / bwrap+seccomp）  │
└──────────────┬──────────────────────────────┘
               │ HTTPS · X-Api-Key
               │ poll / report / heartbeat / manifest / execute-tool
┌──────────────▼──────────────────────────────┐
│  CyberGuard 服务端（现有，几乎不动）           │
│  策略下发 · 审批 · 审计 · Episodic · GRC      │
└─────────────────────────────────────────────┘
```

三个关键决策：

**壳选 Electron，不选 Tauri。** 需要管理 Python 子进程生命周期（Node 侧几十行 JS vs Tauri 侧写 Rust sidecar）；需要本地 spawn MCP STDIO 进程；WebUI 用了 Tailwind v4 的 `@property` / `oklch`，在旧版 WebKitGTK 上有兼容风险。体积劣势被"反正要打包整个 Python 运行时"稀释。

**壳与 sidecar 之间走 stdin/stdout JSONL，不开 localhost 端口。**（借鉴 pi RPC 模式）同机其他进程无法连接，随机 token 鉴权这个问题从存在性上消失。对一个跑在有域凭据的员工终端上、能执行 shell 的产品，这个差别是实质性的。

**agent 内核复用服务端代码，不重写。** `_run_loop` 里的循环守卫参数指纹归一化、预算耗尽撤工具而非报错、反思器两次纠偏上限、压缩时丢弃孤儿 tool 消息——每一条背后都是一次线上问题，绝不能在节点侧重写一遍。

---

## 2. 协议层：复用现有 Gateway

### 2.1 已经能用的部分

`app/routers/gateway.py` 提供了 OpenClaw 节点协议骨架。桌面节点复用鉴权和任务模型，但桌面协议的完整字段与状态机以 `docs/desktop/09-GATEWAY-PROTOCOL.md` 为准：report、heartbeat、LLM capability、MCP manifest 和 episodic recall 都需要扩展。

| 端点 | 用途 | 复用情况 |
|---|---|---|
| `GET /gateway/poll` | 取待处理任务，pending → delivered | 直接用 |
| `POST /gateway/report` | 回报结果 | **需扩展，见 2.2** |
| `POST /gateway/heartbeat` | 保活，更新 `openclaw_last_seen` | **需扩展，见 2.2** |
| `GET /gateway/manifest` | 下发 skills / tools / mcp_tools | 直接用 |
| `POST /gateway/execute-tool` | 受管工具由服务端代执行 | 直接用，见 2.3 |

鉴权沿用 `X-Api-Key` + `AgentConfig.api_key_hash`（SHA-256）。

`AgentConfig` 里的治理字段已经齐了，节点侧直接消费，不用新建表：`autonomy_tier`、`allowed_categories`、`auto_execute_min_confidence`(0.85)、`escalate_to_human_below`(0.60)、`pii_handling_policy`、`kill_switch_enabled`、`requires_approval_rules`、`governed`。

新增一个 `backend_type = "desktop"`，`kind` 沿用 `external`。`master.py::_routable` 里加上 desktop 免 `endpoint_url`（与 openclaw 同理）。

### 2.2 需要扩展的部分

**`ReportRequest` 目前只有 `{message_id, result: str}`**——一个纯文本字段。桌面节点的执行发生在服务端看不见的地方，审计链会在这里断掉。这是必须补的。

```
POST /gateway/report
{
  "message_id": int,
  "status": "completed" | "failed" | "aborted" | "paused",
  "result": str,
  "error": str | null,
  "tool_call_log": [{name, args_digest, exit_code, duration_ms, sandbox_mode}],
  "plan": {...} | null,            // Plan Mode 的最终批准版本
  "artifacts": [{sha256, kind, size, retention_days}],
  "policy_events": [               // 沙箱拒绝、提权申请、trust 决策
    {type, detail, ts}
  ],
  "node_attestation": {sandbox_impl, os, node_version}
}
```

`GatewayMessage` 表相应加 `status` 的 `aborted` / `paused` 两个取值，以及 `report_json` 列存上述结构。

**`heartbeat` 目前只返回 `{success, timestamp}`**，是纯上行保活。桌面节点需要它变成**双向控制通道**——服务端没有别的办法中断一个正在跑的节点任务：

```
POST /gateway/heartbeat
→ { "running": [execution_id...], "paused": [...], "node_caps": {...} }
← { "control": [{"execution_id": "...", "op": "abort"|"steer"|"pause",
                 "payload": "..."}],
    "kill_switch": bool }
```

这样 `kill_switch_enabled` 才真正对节点生效（现在 `is_halted` 只在服务端派发前起作用，管不住已经下发的任务）。

**能力声明**：manifest 是服务端 → 节点的单向下发，缺少节点 → 服务端的能力上报。节点在首次 heartbeat 时提交 `node_caps`：

```
{
  "sandbox_impl": "seatbelt" | "bwrap+seccomp" | "win-restricted-token" | "none",
  "max_sandbox_mode": "read-only" | "workspace-write" | "danger-full-access",
  "network_zones": ["10.1.0.0/16", "vpn-corp"],
  "local_tools": ["nmap", "tcpdump", "volatility"],
  "mcp_servers": [...]
}
```

服务端据此决定派不派高危任务下来。`sandbox_impl == "none"` 的节点（比如老旧 Linux 无 bwrap）**只允许接 read-only 任务**。

### 2.3 两级工具执行（现有设计的直接延伸）

manifest 里已经有一个很好的机制：`command_template=None if agent.governed else t.command_template`。受管 agent 拿不到命令模板，必须回调 `/gateway/execute-tool` 走 `broker_execute` 的完整 gatekeeper。

桌面节点直接沿用这个二分：

- **本地执行**：只在节点上有意义的工具（本地扫描、本地文件解析、MCP STDIO）。节点侧在沙箱内跑，结果和 `policy_events` 上报。
- **服务端代执行**：`governed=true` 的工具，节点只发 `/gateway/execute-tool`，实际执行和审批全在服务端。适合需要中心凭据或中心审计的动作。

这条边界是产品安全性的核心，不要模糊掉。

---

## 3. P0 — 必须有

没有这几项，安全团队不会批准这个客户端进企业终端。

### 3.1 双旋钮权限模型（借鉴 codex）

现在 `permission_level: low/medium/high` 一个维度同时表达"能力"和"审批时机"，所以才有 `internal_agent.execute` 里 `permission_level == "high"` 直接整个 agent 拒绝执行的粗暴逻辑。拆成两个正交维度：

| `sandbox_mode` | 含义 |
|---|---|
| `read-only` | 只读文件系统，无网络 |
| `workspace-write` | 可写工作目录 + /tmp，`writable_roots` 与 `network_access` 可配 |
| `danger-full-access` | 无限制 |

| `approval_policy` | 含义 |
|---|---|
| `untrusted` | 绝大多数动作都要批 |
| `on-request` | 沙箱内自由跑，越界时才问 |
| `never` | 不打断（仅限 `autonomy_tier` 允许时） |

映射到现有治理字段：`autonomy_tier` 决定 `approval_policy` 的上限，`allowed_categories` 收敛可用工具集，`escalate_to_human_below` 仍然是置信度阈值。`permission_level` 保留但降级为兼容字段。

**代码改动点**：`app/models/agent.py` 加 `sandbox_mode` / `approval_policy` 两列；`internal_agent.py` 的 `permission_level == "high"` 早退分支改为按 `approval_policy` 决策；`tool_executor.execute_tool` 的 governance 判断接入新字段。服务端和节点共用同一套策略解析逻辑（放进 agent-core）。

### 3.2 OS 级沙箱（借鉴 codex）

桌面端丢了 `tool-runner` 容器隔离，必须由 OS 机制补上。

- **macOS**：Seatbelt，`sandbox-exec` **必须硬编码 `/usr/bin/sandbox-exec` 绝对路径，不走 PATH 查找**（防 PATH 注入）。
- **Linux**：bubblewrap 建立文件系统/命名空间视图 → `PR_SET_NO_NEW_PRIVS` → seccomp 过滤器。bwrap 不可用时降级 Landlock，再不行则声明 `sandbox_impl: none` 并只接 read-only。
- **Windows**：受限令牌 + ACL。
- seccomp 无条件禁：`ptrace`、`process_vm_readv/writev`、`io_uring_*`；受限网络模式下只放行 `AF_UNIX`。

**保护性元数据强制只读**：即使在可写根之内，`.cyberguard/`（节点密钥、下发的策略、待上报审计缓冲）、`.git`、以及**原始证据目录**都强制只读。这条是硬要求——被 prompt 注入的 agent 第一件事就是改自己的策略文件和擦审计。

**沙箱失败的升级路径**：命令因沙箱被拒时，不是直接报错，而是生成一条带完整上下文的提权申请，走 3.3 的审批流；批准后不带沙箱重试。这条要在 `policy_events` 里留痕。

#### 3.2.1 首发平台：macOS

**决策：首发 macOS。Windows 与 Linux 推迟，不在本期范围内。**

macOS 是三个平台里沙箱摩擦最小的——单次 `sandbox-exec` 调用加一份 `.sbpl` 策略即可，系统版本单一，无发行版碎片问题。选它做首发能最快跑通端到端架构（RPC 通道、Gateway 接入、Plan Mode、单工作台 UI 全部与平台无关）。

但 macOS 有几个必须在 M1 之前想清楚的平台特性：

**TCC 权限是最大的隐性阻塞。** macOS 的 Transparency / Consent / Control 机制要求应用访问 `~/Desktop`、`~/Documents`、`~/Downloads`、外接卷等位置前必须获得用户授权，否则**读取会静默失败**。对一个取证工具这是致命的——分析师把 pcap 放在 `~/Downloads`，agent 报"文件不存在"，排查半天才发现是 TCC。

应对：首次启动引导用户授予**完全磁盘访问权限**（Full Disk Access），并在 §3.6.3 ③ 节点状态栏里显式显示 TCC 授权状态；未授权时证据浏览器直接给出明确提示，而不是让 agent 去撞。

**抓包需要 BPF 设备权限。** `/dev/bpf*` 默认不可读，这是 Wireshark 要装 ChmodBPF 辅助工具的原因。节点要么随包提供一个特权辅助工具（走 `SMJobBless` / launchd daemon），要么把抓包类工具标记为"需服务端代执行"（§2.3 的 `governed` 路径）。**建议首版选后者**——在终端上装特权守护进程会显著抬高安全评审门槛，不值得在 M1 阶段付这个成本。

**签名与公证。** 必须启用 Hardened Runtime 并做 notarization，否则用户端 Gatekeeper 拦截。注意 Hardened Runtime 与 PyInstaller、与 spawn 子进程有冲突，需要申请对应 entitlements（`allow-unsigned-executable-memory`、`allow-dyld-environment-variables`、`disable-library-validation`）——**这几项本身会削弱应用自身的完整性保护**，要在安全评审文档里主动说明，不要等客户问。

**`sandbox-exec` 的长期风险。** 该接口在 man page 中已被标记为 deprecated 多年，但至今仍是 Chrome、codex 等在用的方案，短期可靠。仍需在 §4.1 的端口抽象里把沙箱实现放在接口后，为将来切换 App Sandbox / Endpoint Security Framework 留出余地。

**架构目标**：优先 arm64，Intel 支持视客户情况决定是否出 universal binary。

### 3.3 Plan Mode：执行前审批（借鉴 grok-build）

现在 `_approval_node` 是**事后**拦截——任务跑完了，`_validation_node` 在输出里匹配到 `critical` / `emergency` 关键词才要审批。扫描早就打出去了。

Plan Mode 是执行前拦：agent 先产出结构化执行计划，分析师可以**审阅、批准、评论、或直接改写**，然后才开始执行。

```
{
  "goal": "...",
  "steps": [
    {"id": 1, "tool": "nmap", "intent": "全端口扫描 10.0.0.0/8",
     "risk": "high", "sandbox_mode": "workspace-write", "editable": true}
  ],
  "blast_radius": {"hosts": 65536, "network_zones": ["corp"]},
  "requires_approval": true
}
```

分析师把范围改成 `10.1.2.0/24`、删掉验证步骤，再放行。

额外收益：**计划本身就是审计物**——一份可存证的操作意图声明，比事后从工具日志反推"当时想干什么"强得多，对 GRC 模块是直接可用的证据项。

**代码改动点**：`_run_loop` 前置一个 plan 阶段（新增 `{"type": "plan_ready"}` 事件）；`ApprovalService` 增加 `action_type = "execution_plan"`；`report` 上报最终批准版本。

### 3.4 RPC 通道与 steer / abort（借鉴 pi）

壳与 sidecar 之间的协议形状：

- 命令：`{type, id, ...}`
- 响应统一信封：`{type: "response", command, success, data, error}`
- 事件异步流出：`agent_start` / `agent_end` / `agent_settled` / `tool_execution_update` / `bash_execution_update`
- 命令集：`prompt` / **`steer`** / `follow_up` / **`abort`** / `get_state` / `get_messages` / `new_session` / `fork` / `switch_session`

**`steer` 和 `abort` 是现在 `_run_loop` 里完全缺失的能力。** 任务一旦跑起来只能等 `max_steps` 耗尽、`tool_call_budget` 耗尽、或循环守卫放弃。分析师看着 agent 开始扫错网段，除了杀进程没有别的手段。安全场景这是刚需，而且要能从服务端经 heartbeat 控制通道触发（见 2.2）。

**代码改动点**：`_run_loop` 的 for 循环每轮检查一个 `asyncio.Event` 类型的中断信号；`steer` 表现为向 messages 追加一条 user 消息并跳过当前步。改动很小，因为 `_run_loop` 已经是 yield 语义事件的生成器。

### 3.5 审批 UI 协议（借鉴 pi Extension UI Protocol）

节点侧高危动作需要弹窗，但不能永远挂着。协议形状：

- 阻塞类：`select` / `confirm` / `input` / `editor`，发 `ui_request` 事件后阻塞等 `ui_response`
- 即发即忘类：`notify` / `setStatus`（走系统原生通知）
- **超时语义必须是"超时 = 拒绝"**（pi 是超时用默认值，安全产品不能这样）

服务端 `ApprovalService.wait_for_decision`（3600s 超时）已经是同一个模式，概念对齐即可。

**本地审批的边界**：只有**不涉及职责分离**的确认可以在本地弹窗（例如"确认对这个本地文件执行解析"）。涉及权限提升、跨主机动作、`autonomy_tier` L3 的，一律走服务端审批队列，本地只做通知。这条写死，不给配置项。

### 3.6 界面设计

桌面端是**带完整图形界面的客户端**，装载现有 React WebUI，不是 CLI、不是终端 TUI。§3.4 的 RPC 命令集（`prompt` / `steer` / `abort` …）是**界面与 Python sidecar 之间的内部通道**，不是暴露给用户敲的命令。

#### 3.6.1 形态：单一工作台，不是 21 个 Tab 的搬运

分析师在节点上只做一件事——**调查**。配置管理、治理审计、用户权限这些留在 Web 端。所以桌面端是单工作台布局，不是多标签管理后台：

```
┌─ 节点状态栏 ────────────────────────────────────────────────┐
│ ● 已连接  │ 沙箱: bwrap+seccomp │ Profile: 日常调查 │ 待上报 3 │
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

左侧会话树是 §4.5 本地 JSONL 树结构的可视化，能看到 fork 出的分支——"换个思路重跑这一步"在应急响应里是高频操作。右侧上下文面板随任务状态切换内容。

#### 3.6.2 现有 WebUI 模块的取舍

| 模块 | 桌面端 | 说明 |
|---|---|---|
| 聊天 Chat | ✅ 改造 | 核心界面，接入会话树、Plan 审阅、执行流 |
| MCP | ✅ 复用 | 桌面端才是真正 spawn 本地 STDIO 进程的地方 |
| 工具池 | ✅ 只读 | 展示 manifest 下发内容 + **本地可用性检测**（nmap 装没装） |
| 技能池 | ✅ 只读 | 展示下发的 skills；本地覆盖需先过 §4.2 trust gate |
| 设置 | ✅ 大改 | 变为节点设置：沙箱模式、审批策略、Profile 切换、节点注册 |
| Token 消耗 | ✅ 本地视图 | 只显示本节点用量 |
| 用户管理 / 安全 / 备份 | ❌ | 单机上失去意义 |
| 治理合规 GRC | ❌ | 组织级产物 |
| 审批管理（队列） | ❌ | 职责分离要求批准者 ≠ 操作者，节点只做通知 |
| 审计日志（完整） | ❌ | 不可篡改的前提是不在被审计者机器上；节点只显示本地待上报队列 |
| Webhook / N8N / 定时任务 / 群聊室 | ❌ | 服务端 24h 运行更合适 |
| 知识库 | ⚠️ 仅查询 | 管理留服务端，节点走 gateway 查 |
| AI Provider | ⚠️ 显示元数据 + 节点 Profile | 节点使用 Keychain 中的节点级凭据，不接收服务端原始密钥；云端访问须显式授权 |

#### 3.6.3 需要新做的界面

**① Plan 审阅面板（P0，对应 §3.3）** — 整个方案最重要的新界面。步骤列表逐条可编辑、可删除、可加批注；"影响范围"必须**可视化**——`10.0.0.0/8` 要一眼看出是 65536 台主机，而不是让人读一串 CIDR 文本。每步标注风险等级与将使用的 `sandbox_mode`。批准按钮旁明示"此计划将作为审计证据存证"。状态：`drafting → awaiting-approval → approved / rewritten / rejected`。

**② 实时执行视图（P0，对应 §3.4）** — 服务端现在是 SSE 推进聊天气泡；桌面端应独立成面板：工具调用逐条可展开、每条命令 stdout 流式滚动、旁边标注运行在哪个沙箱模式下、右上角常驻 abort 按钮。状态机：`pending → running → paused → awaiting-approval → completed / failed / aborted`，每个状态都要有明确的视觉区分和可用操作。

**③ 节点状态栏（P0）** — 连接状态、`sandbox_impl`（seatbelt / bwrap+seccomp / win-restricted-token / **none**）、当前 Profile、kill switch 状态、待上报队列积压数。断网时必须明确显示"已暂停，N 个任务待恢复"而非静默失败（对应 §4.4）。`sandbox_impl: none` 时状态栏必须是显著告警色。

**④ 审批弹窗与提权申请（P0，对应 §3.5）** — 原生模态 + 系统通知，带倒计时，**倒计时归零 = 拒绝**。沙箱拒绝某条命令时从这里发起提权申请，申请内容含被拒命令、拒绝原因、所需 `sandbox_mode`。涉及职责分离的一律显示为"已提交服务端审批"，本地无批准按钮。

**⑤ 证据浏览器（P1）** — 拖拽 pcap / 日志 / 内存镜像进来，显示 sha256，明确标注**只读挂载**状态。取证完整性要让分析师看得见，而不是写在文档里。

#### 3.6.4 前端代码复用策略

抽一个共享组件包，Web 端与桌面端共用：聊天气泡、Markdown 渲染、Monaco、i18n 词条、API client、主题。路由与布局各自独立（Web 端 21 Tab 后台，桌面端单工作台）。

这样 UI 迭代不用做两遍，也避免桌面端演化成一份很快腐化的 fork。

**代码改动点**：`webui/` 拆为 `packages/ui-shared`（组件与 i18n）+ `packages/web`（现有后台）；桌面端仓库依赖 `ui-shared`。这是纯前端重构，与 §4.1 的 `agent-core` 抽取相互独立，可并行。

---

## 4. P1 — 应该有

### 4.1 抽取共享内核

> **已被取代**：现为**两个包** `packages/llm-router` + `packages/agent-core`，并含 Operations 抽象、策略管线与审计事件分离。见 DEC-014 / DEC-015 / DEC-016 与 `03-ROADMAP.md` M0a-1。下文保留原始论证。

这是让节点复用服务端 agent 内核的前提，也是整个方案唯一需要动现有代码结构的地方。

包内不认识 Postgres / Redis / Celery / FastAPI，只认识四个端口：

| 端口 | 服务端实现 | 节点实现 |
|---|---|---|
| `Store` | Postgres + SQLAlchemy | 本地树状 JSONL 文件 |
| `VectorIndex` | pgvector | 走 gateway 查服务端（节点不本地建库） |
| `TaskQueue` | Celery + Redis | APScheduler（已在依赖里） |
| `Bus` | Redis pub/sub | 进程内 asyncio 原语 |

进包的代码：`internal_agent.py` 的 `_run_loop` 及其守卫逻辑、`context_compressor.py`、`llm_router.py`、`tool_executor.py` 的调度部分、`episodic_memory.py` 的接口层。

**不用碰**：`app/routers/*`、`app/models/*`、governance、webui。现有基线测试集应基本原样能跑，抽一个端口跑一遍，增量推进。Gateway 协议扩展属于 M3 的明确服务端改动，不属于共享内核抽取。

现有代码里那三个 adapter（`_KSAdapter` / `_SearchAdapter` / `_EpisodicAdapter`）注释写着 "Mockable from tests via monkeypatch"，已经是端口思维的雏形——只是每个都自己 `AsyncSessionLocal()` 开 session，半只脚还踩在 Postgres 上。正式化即可。

顺带解决一个既有问题：函数体内 `from app.core.database import get_db_context` 这类局部 import 满天飞，是循环依赖的症状，端口化会一并清理掉。

### 4.2 Project Trust Gate（借鉴 pi）

pi 把两件事分开：**沙箱管"工具能做什么"，trust 管"要不要加载这个目录里的配置、扩展、技能、提示词"**。决策存 `trust.json`，默认 ask；全局资源无条件加载，**项目本地的必须先获得信任**。

这对你的风险等级远高于 pi。分析师用节点分析的目录是什么？可疑样本、取证介质拷出的代码库、钓鱼附件解包内容——**天然是攻击者可控的**。目录里放一个构造好的指令文件，就是一条直通 agent 的 prompt 注入通道，而且绕过服务端那五层 guardrail（内容是在节点侧被拼进 system prompt 的）。

现在 skills 全从 DB manifest 下发所以安全。**但只要桌面端要支持"分析师本地自定义技能/上下文文件"，这个 gate 就是前置条件。**

### 4.3 工具隔离层：Gondolin 形态（借鉴 pi containerization）

pi 的三个方案里选 Gondolin 那个形态：**本地 micro-VM 只装工具和 shell，agent 进程留宿主机**——宿主的域凭据、VPN 证书、节点密钥不进沙箱。

对照另外两个：纯 Docker 是整个进程进容器，文档明说 "provider API keys enter the container"；OpenShell 最完备但远程沙箱不 bind-mount 宿主文件，取证材料要显式传输，GB 级 pcap 场景不合适。

原则一句话：**工具进隔离层，凭据留宿主。**

### 4.4 断网暂停 / 恢复（借鉴 claude-code-best `/goal`）

笔记本合盖、切 VPN、进机房断网——任务不能烂掉。现在 `GatewayMessage` 卡在 `delivered` 就是这个问题，服务端已经有 `cleanup_stale_executions_task` 在扫尾，说明踩过。

正确形态：节点侧本地暂停（保存完整 messages 状态到本地会话文件）→ 恢复后继续 → heartbeat 上报 `paused` 而非静默消失 → 服务端据此不误判为节点死亡。

### 4.5 本地树状 JSONL 会话（借鉴 pi）

节点侧会话存本地文件，append-only JSONL，每条带 `id` / `parent_id`。天然支持 fork 重跑——"换个模型重试这一步"、"对比两条调查路径"在应急响应里很有用。

**上报服务端的只有审计事件、结果摘要和 artifact 哈希，全量对话不出本机**——顺带解决了取证数据不该外传的合规问题。

> 服务端侧 `conversations.messages_json` 那个整块 TEXT 的 read-modify-write 并发丢消息问题（多 worker 下无锁）是独立议题，见另一份重构清单。

---

## 5. P2 — 可以有

**Config profiles（借鉴 codex）**：一份配置存多组命名预设，切换即换整套模型 + 沙箱 + 审批策略。分析师需要"日常调查"（read-only + 逐步审批）和"应急响应已授权"（workspace-write + 快速通道）两套，一键切换，**切换动作本身进审计**。比现在的全局 `AUTO_APPROVE` 开关细得多。

~~**子 agent 工作区隔离（借鉴 grok-build worktree）**~~ —— **已改判**：节点不做子 agent spawn，并行止于同上下文工具并行（DEC-012 / INV-22）。工作区隔离归**服务端 fan-out** 范畴，与并发/深度限流一并处理（INV-23）。原论证：并行 fan-out 已有，缺工作区隔离；每个子 agent 独立临时目录，**原始证据只读挂载**——取证完整性要求原始材料绝不可写（这一条仍然成立，只是落在服务端）。

**确定性 Workflow 编排（借鉴 claude-code-best `/ultracode`）**：`agent` / `pipeline` / `parallel` / `phase` 四种模式由脚本驱动，而非 LLM 自由调度。安全 SOP 本来就该是确定的——"资产发现 → 漏洞扫描 → 人工验证 → 出报告"的顺序不该每次让模型重新发挥。现在 skills 是纯提示词，可以加一层确定性编排。

**本地个人记忆层（借鉴 claude-code-best `/dream`）**：`MEMORY.md` 索引 + 主题文件 + 限额 + pruning，只存**这个分析师的个人偏好**（惯用工具、报告格式）。组织级经验仍走服务端 Episodic，两层分工明确、互不污染。

**`/remember` 显式标注（借鉴 grok-build）**：分析师一键把某次运行标为"典型案例"或"反面案例"，上报进服务端经验库。人工标注质量远高于后台自动总结。顺带补上现在 `_maybe_record_episode` 硬编码 `success=True`、**失败经验一条不存**的缺口。

---

## 6. 明确不做

**claude-code-best 的 artifacts 公开 URL**：把 HTML 报告传到公网带过期时间的地址。取证报告上公网对本产品是灾难。但"agent 产出结构化报告工件"这个模式要——带 sha256、带保留期、上报服务端存证，而不是塞在对话文本里让人复制粘贴。

**claude-code-best 的 Pipe IPC + LAN 零配置发现**：跨机器自动发现并交换任务，在企业网里是一条横向移动通道，安全团队第一个不会批。现有 gateway 星型拓扑是对的。

**节点侧本地 Episodic 向量库**：见 §0，共享经验是相对单机 CLI 工具的结构性优势，不要下放。

**RBAC / SSO / WORM 审计下放**：单机上这些失去意义，且破坏不可篡改前提。

---

## 7. 里程碑

| 阶段 | 内容 | 产出判据 |
|---|---|---|
| M0a-1 | 包边界（`llm-router` + `agent-core`）+ Operations 抽象 + 工具管线骨架 + 审计事件流 | **基线测试集全绿，行为零变化** |
| M0a-2 | 工具语义（schema 校验 / 默认串行 / 结构化错误）+ 压缩加固 + 方向性截断 + Provider 维度补全 | 各项专项用例通过 |
| M0b | 前端拆 `ui-shared`（3.6.4） | 现有 Web 端功能零回归 |
| M1 | Electron 壳 + Python sidecar + RPC 通道（3.4）+ 单工作台骨架（3.6.1） | 能在本地跑通一次 agent 循环，界面可见执行流，可 abort |
| M2 | 双旋钮策略 + **macOS Seatbelt 沙箱**（3.1 / 3.2 / 3.2.1）+ 节点状态栏（3.6.3 ③） | 沙箱逃逸用例通过；元数据只读验证；TCC 授权引导可用；签名公证通过 |
| M3 | Gateway 接入：`backend_type=desktop` + report/heartbeat 扩展（2.2） | 服务端能派任务、收结构化审计、远程 abort |
| M4 | Plan Mode（3.3）+ Plan 审阅面板（3.6.3 ①）+ 审批弹窗（3.6.3 ④） | 高危任务执行前必经审批，改写后的计划入审计链 |
| M5 | Trust gate（4.2）+ 工具隔离层（4.3）+ 断网恢复（4.4）+ 证据浏览器（3.6.3 ⑤） | 可信/不可信目录行为差异验证；断网 30 分钟后恢复继续 |

M0a 与 M0b 都是现有仓库内的重构，互相独立、可并行，且不阻塞任何东西——建议先做，用现有测试当安全网。M1 起是**同一仓库内 `apps/desktop/` 的新代码**（monorepo，见 DEC-001）。

> **里程碑已更新**：M0a 已拆为 M0a-1（结构，只搬不改）与 M0a-2（语义，开始改行为），以 `03-ROADMAP.md` 为准。

**Windows / Linux 推迟至二期**，本期不投入。这是一个**已知并主动接受的风险**，不是遗漏，见 §8。为让二期成本可控，本期必须守住一条硬约束：

> 沙箱能力从 M0a 起就放在端口接口之后，Seatbelt 的任何假设不得渗入上层逻辑。
> 具体检查项：`sandbox_mode` 语义（`writable_roots` / `network_access`）必须是平台无关的声明式描述；
> `.sbpl` 策略生成只存在于 macOS 实现模块内；§2.2 的 `node_caps.sandbox_impl` 从第一天就上报，
> 服务端据此派单的逻辑一次写对，二期加平台不用改服务端。

**重新评估触发条件**（满足任一即启动支线 W）：出现 Windows 终端的目标客户；进入企业 SOC 场景的 GA 准备；或 §3.1 权限模型需要定稿为对外承诺。

UI 工作不单独排期，而是绑定在对应功能的里程碑里：**每个 P0 能力必须连同它的界面一起验收**，否则会出现"策略引擎做完了但分析师看不到自己处在什么模式"这类半成品状态。

---

## 8. 风险

**产品攻击面变了。** 之前所有危险动作在服务端容器里，现在在一台有域凭据的员工终端上。沙箱分级不是"抄来的优点"，是准入条件——M2 不达标就不该有 M3。

**Python 跨平台打包是真痛苦。** 依赖里 `pymupdf` / `pytesseract` / `pillow` / `cryptography` 全带原生扩展，tesseract 本身还是需要单独 bundle 的外部二进制。建议节点侧 sidecar **裁剪依赖**：OCR、GRC、governance seeds、boto3、celery、flower 这些都不进节点包。

**沙箱实现的三平台差异是长期维护成本。** 尤其 Linux 发行版差异（bwrap 是否可用、内核是否支持 Landlock）。`sandbox_impl: none` 的降级路径必须从第一天就存在且被测试，否则会在客户现场变成"关掉沙箱就能用"的口子。

**首发 macOS 与目标用户平台可能错位——已知并接受的风险。** 企业 SOC 终端主体通常是 Windows，而 Windows 恰是隔离能力最弱的平台。二期若发现受限令牌 + ACL + Job Object 达不到可接受的隔离水平，Windows 节点的产品定义可能被迫收窄为"只做只读证据采集，重工具一律走 §2.3 服务端代执行"。

本期主动接受该风险，理由是优先验证架构可行性。**缓解手段是把沙箱严格约束在端口接口之后**（约束细则与重新评估触发条件见 §7），使二期的平台扩展只需新增实现模块，不触碰上层逻辑与服务端派单逻辑。

需要留意的是：这个错位一旦成真，代价不是重写代码，而是**对外承诺的调整成本**——所以在支线 W 有结论之前，§3.1 的权限模型不宜作为对客户的正式能力承诺发布。

**macOS 特有阻塞项**：TCC 授权（未授权时文件读取静默失败，对取证工具是致命的用户体验问题）、`/dev/bpf*` 抓包权限（首版建议走服务端代执行规避特权守护进程）、Hardened Runtime 所需 entitlements 会削弱应用自身完整性保护（需在安全评审文档中主动披露）。详见 §3.2.1。

**节点密钥是新的高价值目标。** `api_key_hash` 服务端存哈希没问题，但节点侧的明文密钥需要走系统钥匙串（macOS Keychain / Windows DPAPI / Linux Secret Service），不能落在配置文件里。
