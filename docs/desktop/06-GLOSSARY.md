# 06 · 术语表

状态：活文档 · 2026-07-27

统一命名，避免同一概念在代码、文档、界面里出现三种叫法。**新增术语请追加到此处。**

---

## 角色与拓扑

**节点（node / desktop node）**
运行在分析师终端上的桌面客户端。经 Gateway 接入服务端，`backend_type = "desktop"`。不是"客户端"、不是"单机版"、不是"agent"。

**服务端（server）**
现有 CyberGuard 平台。负责策略下发、审批、审计、治理、Episodic 经验库。

**Master Agent**
服务端的 LangGraph 编排器（`app/agents/master.py`）。做意图解析、任务分派、结果汇总。

**内部 Agent（internal agent）**
服务端进程内运行的工具循环执行器（`InternalAgentRunner`）。`AgentConfig.kind = "internal"`。

**外部 Agent（external agent）**
经 HTTP 或 Gateway 接入的远端执行者，含 OpenClaw 节点与桌面节点。`kind = "external"`。

---

## 协议

**Gateway 协议**
服务端与外部节点之间的既有协议：`poll` / `report` / `heartbeat` / `manifest` / `execute-tool`，`X-Api-Key` 鉴权。

**manifest**
服务端 → 节点的能力下发：分配给该 agent 的 skills / tools / mcp_tools。

**node_caps**
节点 → 服务端的能力上报（随 heartbeat）：`sandbox_impl`、`max_sandbox_mode`、`network_zones`、`local_tools`、`mcp_servers`。

**governed（受管）**
`AgentConfig.governed = true`。此类 agent 的工具不下发 `command_template`，必须回调 `/gateway/execute-tool` 由服务端代执行并过完整 gatekeeper。

**两级工具执行**
本地执行（节点沙箱内）与服务端代执行（`governed`）的二分。见 INV-18。

**`desktop.v1`**
桌面节点协议版本号。与 OpenClaw 的最小协议**并存但不混用**——服务端不得把旧 OpenClaw 的自由文本 `result` 当成桌面的结构化审计。权威定义见 `09-GATEWAY-PROTOCOL.md`。

**provisioning secret**
管理员创建 `backend_type=desktop` 的 AgentConfig 时生成的一次性配对密钥。**只显示一次**，服务端只存 hash，节点写入 Keychain 后不得回报。

**`credential_ref`**
manifest 中指向 Keychain 条目的引用（如 `keychain://cyberguard/provider/corp-local-1`）。**只能是引用，不能是密钥本身**（INV-02）。

**`report_id` / `command_id` / `request_id`**
三类幂等键。`request_id` 用于所有写操作重试去重；`report_id` 用于上报去重；`command_id` 用于控制命令去重。

**audit buffer**
`.cyberguard/audit-buffer/`，append-only。上报失败时的本地暂存，有上限，打满时停止派发新的高风险任务并告警（INV-36）。

---

## 两种 Profile（易混）

**LLM Profile** —— **首版必需**
出网档位：`local_only`（仅本机或企业内网 Provider）/ `approved_remote`（云端 Provider，须用户显式启用 + 界面告警 + 审计）。随 manifest 下发，含 `base_url`、模型元数据、`credential_ref`。见 DEC-017、09 §6.3。

**操作 Profile** —— **二期候选**
"日常调查" / "应急响应已授权"这类一键切换整套沙箱模式 + 审批策略的预设。参照 codex config profiles。

> 两者都叫 Profile，但一个管**数据出网**、一个管**操作权限档位**。命名时务必带前缀，不要单说 "Profile"。

**RPC 通道**
壳与 sidecar 之间的 stdin/stdout JSONL 协议。**不是**面向用户的命令行——`prompt` / `steer` / `abort` 是界面调用的内部命令，不是用户敲的。

---

## 包与分层

**`packages/llm-router`**
纯 Provider 抽象包。`chat` / `stream_chat` / `embed`、重试退避、限流、能力探测、模型元数据。**不含任何 agent 概念。**

**`packages/agent-core`**
部署无关的 agent 内核包。循环 + 守卫 + 压缩 + 四个端口。**不认识 Postgres / Redis / Celery / FastAPI。**

**`packages/ui-shared`**
Web 与桌面共用的纯展示层。**不依赖 agent 概念。**

**端口（port）**
`Store` / `VectorIndex` / `TaskQueue` / `Bus`。服务端与节点注入不同实现。

**Operations 抽象**
工具依赖的最小系统接口（`ReadOperations` / `ExecOperations` / `EditOperations`），而非直接调系统 API。**两级工具执行靠注入不同实现区分**——节点侧不注入本地 `ExecOperations`，`governed` 工具在类型层面就无法本地执行。

**headless 模式**
sidecar 不启动 Electron 壳、直接喂 stdin 输出 JSON 的运行方式。用于沙箱用例集、自动化剧本、CI 回归。

---

## 执行与控制

**agent 循环（run loop）**
`_run_loop`：LLM 调用 → 工具分发 → 结果回灌的迭代过程。

**steer**
运行中向循环追加一条用户消息以调整方向，不中断执行。

**abort**
立即中断运行中的循环，状态可恢复。

**循环守卫（loop guard）**
按"工具名 + 归一化参数"指纹计数，识别原地重复。归一化用 `json.dumps(..., sort_keys=True)`，防止 key 顺序变化绕过检测。

**反思器（reflector）**
检测到循环后注入的纠偏提示，上限两次，超限中止。

**工具预算（tool call budget）**
单次运行的工具执行硬上限。耗尽时**撤掉工具列表逼模型基于已有信息作答**，而非直接报错。

**策略管线（policy pipeline）**
工具执行的五个步骤：`prepare_arguments` → `validate_arguments` → `before_tool_call` → `execute` → `after_tool_call`。**有干预能力**——`before_tool_call` 可阻断，`after_tool_call` 可脱敏改写。与审计事件是两套机制，不得合并。

**审计事件（audit event）**
四层事件流（agent / turn / message / tool_execution，各 start → update → end）。订阅者是**纯消费者**——不可否决、不可修改。**emit 必须 await**，审计落盘后才继续。

**`execution_mode`**
工具声明 `sequential` 或 `parallel`。**一票否决**：一批调用中任一声明 sequential，整批串行。**默认 sequential。**

**`is_error`**
工具结果的结构化失败标记。取代字符串前缀嗅探（`startswith("ERROR")`）。

**`exclude_from_context`**
条目标记：**界面可见、审计可见、模型不可见**。用于证据原文、审批记录、`policy_events`。

**压缩（compaction）**
上下文超阈值时把早期消息换成结构化摘要，保留尾部若干条。切点必须落在合法消息边界，不得产生孤儿 tool 消息，且不得切断当前 turn。

**六段摘要**
压缩摘要的固定格式：Goal / **Constraints** / Progress（Done·In Progress·Blocked）/ Key Decisions / Next Steps / Critical Context。固定格式的作用是强迫模型覆盖每个维度。**Constraints 段必须含当前授权范围、目标白名单、沙箱模式**（INV-33）。

**方向性截断**
`truncate_head`（保头，适合读文件）与 `truncate_tail`（保尾，适合命令输出与日志）。双重约束：行数 **或** 字节数，先到先算。

---

## 策略与权限

**双旋钮**
两个正交维度：`sandbox_mode`（技术上能做什么）× `approval_policy`（何时必须停下来问人）。取代原先 `permission_level` 单一维度。

**sandbox_mode**
`read-only` / `workspace-write` / `danger-full-access`。

**approval_policy**
`untrusted`（多数动作要批）/ `on-request`（越界才问）/ `never`（不打断，受 `autonomy_tier` 限制）。

**writable_roots**
`workspace-write` 下允许写入的根目录白名单。其内的保护性路径仍强制只读，见 INV-03。

**保护性元数据**
`.cyberguard/`、`.git`、原始证据目录。任何模式下对 agent 只读。

**提权申请（escalation）**
命令因沙箱被拒时生成的、带完整上下文的审批请求。批准后不带沙箱重试，并在 `policy_events` 留痕。

**Trust Gate**
决定是否加载某目录内的本地配置 / 技能 / 上下文文件。与沙箱是**两件不同的事**：沙箱管"工具能做什么"，trust 管"要不要加载这里的东西"。

---

## 计划与记忆

**Plan Mode**
执行前产出结构化计划，分析师可审阅 / 批准 / 评论 / 改写，然后才执行。计划本身是审计证据。

**blast radius（影响范围）**
计划中受影响的主机数、网络区域等。界面必须可视化，不能只给 CIDR 文本。

**Episodic 经验**
服务端 `agent_episodes` 表：任务向量 + 打法（工具序列）+ 结果。跨分析师共享。**节点不建本地副本。**

**个人偏好层**
节点本地的轻量记忆（惯用工具、报告格式）。与 Episodic 分层，互不污染。

**artifact（工件）**
agent 产出的结构化报告文件。带 sha256 与保留期，上报服务端存证。**不生成公网 URL。**

---

## 会话

**会话树**
本地 append-only JSONL，每条带 `id` / `parent_id`。支持 fork 重跑。

**fork**
从历史某点分叉出新分支继续（换模型重试、对比两条调查路径）。

**分支摘要（branch summary）**
切换分支时，对被放弃分支的工作产出的摘要，注入新分支上下文。

---

## 待确认 · 桌面端 i18n 安全面英译（T2 → T7 定稿）

> 初译供人审。确认后的译法保留在此；T7 抽审阅表时以本区为准。

| 中文 | 建议英文 | 出处 | 备注 |
|---|---|---|---|
| 运行态 | Runtime status | `statusbar.aria` | aria-label |
| 在线 | Online | `statusbar.online` | |
| 离线 | Offline | `statusbar.offline` | |
| 连接中 | Connecting | `statusbar.connecting` | |
| 沙箱 | Sandbox | `statusbar.sandbox` | |
| 权限 | Permissions | `statusbar.permission` | |
| 只读 | Read-only | `statusbar.tierReadonly` | |
| 完整 | Full | `statusbar.tierFull` | |
| 已暂停 | Paused | `statusbar.paused` | |
| 环境详情 | Environment details | `statusbar.envDetails` | |
| sidecar 未连接 | Sidecar not connected | `statusbar.sidecarOffline` | tooltip |
| sidecar 离线 | Sidecar offline | `degradation.offline.label` | |
| 本地执行进程未连接，运行已禁用 | Local execution process not connected; runs are disabled | `degradation.offline.detail` | |
| 沙箱不可用 | Sandbox unavailable | `degradation.sandbox.label` | |
| 仅允许只读档位（INV-16） | Read-only tier enforced (INV-16) | `degradation.sandbox.detail` | |
| FileVault 未开启 | FileVault is off | `degradation.filevault.label` | |
| 全盘加密未开启，本机数据在设备丢失时可被读取 | Full-disk encryption is off; local data may be readable if the device is lost | `degradation.filevault.detail` | 静态回落；sidecar `fvWarning` 走 `detailText` 不翻 |
| 磁盘访问受限 | Disk access restricted | `degradation.tcc.label` | |
| 部分目录读取会失败 | Some directories will fail to read | `degradation.tcc.detail` | sidecar `tccGuidance` 走 `detailText` 不翻 |
| 模型为 mock | Model is mock | `degradation.mock.label` | |
| 未配置真实模型，输出不可用于结论 | No real model configured; output must not be used as findings | `degradation.mock.detail` | 「不可用于结论」= 禁止，非提醒（INV-38） |
| 收起 | Dismiss | `degradation.dismiss` | 降级浮出条 |
| 调查 | Investigate | `nav.workbench` | 主入口，非 "Investigate view" |
| 证据 | Evidence | `nav.evidence` / `rail.evidence` | |
| 设置 | Settings | `nav.settings` | |
| 本次调查 | This investigation | `rail.title` | 右栏 |
| 发现 | Findings | `rail.findings` | |
| 高危 | high-severity | `rail.findings.high_*` | 复数 finding(s) |
| 能力档位 | Capability tier | `composer.tier.aria` | |
| 中止 | Abort | `composer.abort` | |
| 中途补充 | Add mid-run | `composer.steer` | steer |
| 计划审阅 | Plan review | `plan.aria` | |
| 批准 / 拒绝 | Approve / Reject | `plan.approve` / `plan.reject` | |
| 本地自批准 | local self-approve | `plan.self` | INV-38；保留 `approval_type: self` 原文 |
| 提权申请 | Privilege request | `event.privilege` | |
| 外部来源 | External source | `event.hostile` | INV-39 |
| 开始一次调查 | Start an investigation | `empty.title` | 空态 |
| 只读证据库：注册时算 sha256，校验时重算对比。正文不进模型上下文。 | Read-only evidence library: sha256 at register, recompute on verify. Body never enters model context. | `evidence.lede` | 正文不进模型（INV / 证据边界） |
| 登记文件 | Register file | `evidence.register.title` | |
| 返回调查 | Back to investigation | `evidence.back` | |
| 目录 / {n} 项 | Catalog / {count} item(s) | `evidence.catalog.*` | 复数 `_one`/`_other` |
| 校验 / 完整性 OK / 哈希不匹配 | Verify / Integrity OK / Hash mismatch | `evidence.verify*` | |
| 在 Finder 中显示 | Show in Finder | `evidence.reveal.title` | macOS 首发 |
