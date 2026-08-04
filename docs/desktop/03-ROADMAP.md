# 03 · 路线图

状态：定稿 · 2026-07-27

**规则：里程碑必须按顺序推进，出口判据未满足不得进入下一阶段。** 判据是可验证的事实，不是"感觉差不多了"。

---

## 依赖关系

```
M0a-1 ─→ M0a-2 ─┐
                ├─→ M1 ─→ M1.5(自用验证版) ─→ M2(沙箱) ─→ M3(可分发完整) ─→ M4 ─→ M5 ⇢ M6(connected·按需)
M0b ────────────┘                                                                    ⇢ M7(交付工程)
```

**定位：单兵全能工具**（DEC-027）。面向没有服务端的单个安全从业者，一个人既看态势也下场查，不分角色。

**两条交付线**（DEC-028）：

| 线 | 目标 | 节点 |
|---|---|---|
| **自用验证版** | 最快跑通一条真实安全任务链路，验证产品方向 | **M1.5** |
| **可分发版** | 给客户装，全套安全工程 | M2 → M3 → M7 |

**为什么插 M1.5**：目前**没有客户**。M2 之后的沙箱、公证、加密、审计链、卸载、更新通道**全是"给别人用"才需要的**，在有真实使用反馈前这套投入未经验证。**最好的第一个用户是开发者自己**——自用不需要通过安全评审。

**M6 降为按需**：单兵不会部署服务端。端口抽象已保证将来可加，但不占当前排期。有企业客户时再启动。

**M0a 拆成两段，切分点是"结构 vs 语义"：**

- **M0a-1 只搬不改** —— 包边界、执行骨架、钩子位置。完成时**系统行为应与现在完全一致**，基线测试原样全绿。
- **M0a-2 才改行为** —— 参数校验、串行语义、错误结构、压缩加固、截断方向。

这个切分点不是随意选的：**行为零变化的重构可以独立验证、独立回滚**。混在一起做，测试挂了就无法判断是搬错了还是改错了。分开之后 M0a-1 的判据非常硬——"测试全绿且行为零变化"，一旦不满足就是搬的问题，二分定位成本极低。

---

## M0a-1 · 结构：包边界与执行骨架

**只搬不改。** 建立包边界、执行骨架、钩子位置——**完成时系统行为必须与现在完全一致**。

**范围**

1. **`packages/llm-router`** —— 从现有 `llm_router.py`（944 行）剥出纯路由能力：`chat` / `stream_chat` / `embed`、重试退避、限流、能力探测。`parse_intent` / `generate_summary` / `build_chat_system_prompt` 这类业务语义方法**留在 `app/`**。本阶段**不新增** Provider 差异维度，纯搬运。
2. **`packages/agent-core`** —— 四个端口 `Store` / `VectorIndex` / `TaskQueue` / `Bus`；迁入 `_run_loop` 及守卫逻辑、`context_compressor`、`tool_executor` 调度部分、`episodic_memory` 接口层；为服务端提供 Postgres / pgvector / Celery / Redis 实现。
3. **Operations 抽象** —— 工具不直接调系统 API，改为依赖最小接口（`ReadOperations` / `ExecOperations` / `EditOperations`），每个工具只声明所需方法。
   > **这条直接解决两级工具执行**：同一份工具代码，本地沙箱执行与 `governed` 服务端代执行只是换一个 Operations 实现，不必像现在 `_dispatch` 里 if/elif 分四路。INV-18 由"靠代码走查"升级为"靠类型系统保证"。参照 pi 的同名设计（其动机正是 mock 与远程执行）。
4. **工具执行五步管线（骨架就位）** —— `prepare_arguments` → `validate_arguments` → `before_tool_call`（可阻断）→ `execute` → `after_tool_call`（可脱敏改写）。把现在散落的检查收拢上去：`_dispatch` 的四路分支、`tool_executor` 的 governance、`run_task` 的 kill switch。
   > 本阶段 `validate_arguments` 先做成 pass-through，实际校验逻辑在 M0a-2 填入——**位置先占住，行为不变**。
   > 将来的沙箱决策、Plan Mode 拦截、权限继承校验（INV-21）都挂 `before_tool_call`；`pii_handling_policy` 落到 `after_tool_call`。见 INV-28。
5. **审计事件流** —— 与策略管线**分开**的四层事件（agent / turn / message / tool_execution，各 start → update → end）。订阅者不可否决不可修改；**emit 必须 await**，审计落盘后才继续。见 INV-29。

**方法**：一次抽一个端口 / 一个关注点，每次跑一遍全量测试。现有三个 adapter（`_KSAdapter` / `_SearchAdapter` / `_EpisodicAdapter`）已是雏形，正式化即可。

**出口判据**
- **基线测试集原样全绿，服务端对外行为零变化**（这是本阶段唯一的硬判据——不满足即为搬运出错，不是设计问题）
- `packages/agent-core` 内无 `sqlalchemy` / `redis` / `celery` / `fastapi` / `app.*` import；`packages/llm-router` 内无任何 agent 概念。两条 lint 规则均 CI 阻断
- 函数体内的局部 import（循环依赖症状）在迁入代码中清零
- **所有工具执行路径均经过策略管线**（静态检查用例，断言无旁路）
- 审计写入失败导致当前 turn 中止（不得静默继续）

---

## M0a-2 · 语义：工具与上下文的正确性

**状态：主路径已落地（2026-07-30）** — 见 `tests/test_m0a2_semantics.py` / `test_m0a2_remaining.py` / `test_model_limits.py`。

**开始改变行为。** 每一项都配专项用例，出错时能定位到具体语义变更。

**范围**

1. **模型元数据字段** —— provider / 模型表补 `context_window` 与 `max_output_tokens`。没有这两个字段，"压缩阈值按剩余预算而非绝对值"就落不了地，只能继续写死 8000 / 24000。现有 capability probing（🔧/👁 探测）可顺手把这两项也探了。参照 pi 的 `models.json`。
2. **工具执行语义补齐** —— 三项一起做：
   - `input_schema` 运行时校验，填入 M0a-1 预留的 `validate_arguments`（INV-30）
   - `execution_mode: sequential | parallel` 与一票否决规则，**默认 sequential**（INV-31）
   - 结构化 `is_error` 取代字符串前缀嗅探（INV-32）
   > **注意工作量**：默认值从"无条件并行"改为"默认串行"，现有工具需要逐个评估并显式标注 parallel。这部分体力活要预留时间。
3. **`exclude_from_context` 标记** —— 消息可标记为"界面可见、审计可见、模型不可见"。
   > 证据原文、审批记录、`policy_events` 属于这类：必须留痕，但不该占模型上下文。现在只能二选一。
4. **压缩逻辑合并并加固** —— 现有两套实现（`context_compressor.py` 四段中文提示词 / `internal_agent._maybe_compact` 自由格式英文提示词）合一，并同时修正：
   - **token 估算按字符类别加权**（遗留问题 9，会导致线上报错，**本阶段最高优先级**）
   - **摘要改为固定六段**：Goal / **Constraints** / Progress（Done·In Progress·Blocked）/ Key Decisions / Next Steps / Critical Context。固定格式的作用是**强迫模型覆盖每个维度**，而非挑有趣的写。**Constraints 段必须包含当前生效的授权范围、目标白名单、沙箱模式**——见 INV-33
   - **阈值改为按剩余预算**（`context_window - reserve`），依赖本阶段第 1 项
   - **当前 turn 不得被切开**（INV-34）
   > 另参照 pi 的 split-turn 处理：切点落在 assistant 消息形成"半个 turn"时，为断开部分单独生成 `turn_prefix` 摘要。
5. **工具输出方向性截断** —— `truncate_head` / `truncate_tail` 按工具选择，双重约束（行数 或 字节数，先到先算）。见遗留问题 10。
6. **`llm-router` 补两个 Provider 差异维度** —— 现覆盖消息结构与流式协议，缺：
   - **cache control**（prompt caching）。skills 全文注入 system prompt 的那部分内容稳定，正是最适合缓存的，对成本影响显著。
   - **thinking / reasoning 档位**。用统一枚举（`off` / `minimal` / `low` / `medium` / `high` / `xhigh`）加每模型映射表，翻译成各 Provider 的具体参数。

**出口判据**
- `context_window` / `max_output_tokens` 可用，压缩阈值按剩余预算计算
- **中文内容的 token 估算误差在可接受范围**（对照真实 tokenizer 抽样验证）
- 畸形工具参数被 `validate_arguments` 拦截，不进入执行
- 有副作用工具的并发用例被串行化；结果按原调用顺序发出
- 输出内容含 `ERROR` 前缀但实际成功的用例不被误判为失败
- **压缩后授权范围仍在上下文中**；越界扫描用例在压缩后仍被拦截（INV-33）
- 长 run 压缩用例中当前 turn 完整（INV-34）
- 尾部含关键信息的工具输出不被截断丢弃

---

**M0a-1 与 M0a-2 都不做**：任何桌面端代码。内核没抽干净就开壳，会把 Electron 的假设倒灌进服务端。

---

## M0b · 拆分 `packages/ui-shared`

**范围**：从 `webui/src/` 抽出组件、i18n 词条、API client、主题为 workspace 包；`webui/` 改为依赖它。

**出口判据**
- Web 后台 21 个 Tab 功能零回归（Playwright 冒烟用例通过）
- `packages/ui-shared` 不含任何路由与页面级布局

---

## M1 · 壳 + Sidecar + 单工作台骨架

**状态：骨架已落盘（2026-07-30）** — `apps/desktop/` + `tests/test_desktop_sidecar.py`。仍待：托盘、真实 MCP 孤儿治理实装、本地会话 JSONL 持久化、敏感目录规范完整落地。

**范围**：Electron 主进程（窗口 / 托盘 / sidecar 生命周期）、stdin/stdout JSONL 通道、单工作台布局骨架、`_run_loop` 接入 `steer` / `abort`、**MCP 连接器 spawn 与孤儿治理**、**能力档位骨架**（会话创建时确定，Operations 按档位注入；只读档不注入本地 `ExecOperations`）、**敏感数据落位规范**（临时目录统一管理、禁用崩溃上报、日志脱敏与保留上限）。M1 只允许 fake/mock Operations 和本地 mock LLM；不得执行真实宿主工具，不得连接真实 Provider。

**关键改动**：`_run_loop` 每轮检查中断信号（`asyncio.Event`）；`steer` 表现为追加一条 user 消息并跳过当前步。改动很小——`_run_loop` 本就是 yield 语义事件的生成器。

**出口判据**
- 本地跑通一次完整 agent 循环，界面实时可见工具调用与流式输出
- `abort` 能在 2 秒内中断运行中的循环，且状态可恢复
- sidecar 崩溃后主进程能自动重启并恢复会话
- 全程无监听端口（`lsof` 验证）
- **`kill -9` 主进程后无残留 MCP 子进程**（孤儿治理三层防护，见 `../superpowers/specs/2026-07-29-mcp-connector-lifecycle-design.md` §3）
- **headless 模式可用**：不启动 Electron，直接喂 stdin 输出 JSON。这是 M2 沙箱用例集的运行前提
- **档位模型正确**：只读档会话的实例中不存在本地 `ExecOperations`（类型层面而非条件判断）
- **敏感数据只落在受管位置**：无系统 `/tmp` 残留；崩溃上报已禁用（见 `../superpowers/specs/2026-07-29-local-data-protection-design.md` §7）
- **安全闸门**：M1 产物不具备真实本地工具执行资格；只有 M2 沙箱与凭据隔离出口判据通过后，才允许启用真实工具。

---

## M1.5 · 自用验证版（不分发）

**目标：最快跑通一条真实的安全任务链路，验证产品方向。** 不是交付里程碑，是**产品验证**里程碑。

**做什么**：接通真实 LLM Provider、接 2–3 个真实 MCP 数据源、内置几条最基本的 SOP 技能、能完成一次端到端的真实任务（例如"给我看这批告警里值得关注的"或"评估这个 CVE 对我们的影响"）。

**明确不做**（推到 M2/M3/M7）：沙箱、签名公证、静态加密、审计哈希链、卸载清理、更新通道。

**硬约束**（否则违反 INV-38）：
- **禁止分发**，构建产物标记为开发版
- 启动时明示「开发版本，未启用沙箱与静态加密，**请勿处理真实敏感数据**」
- **不宣称任何安全属性**——不宣称就不算伪装，这是它能合法跳过安全工程的唯一理由

**出口判据**
- 开发者自己（或身边的安全从业者）**能用它完成一件真实工作**，且愿意第二次打开它
- 拿到一份"哪里好用、哪里别扭"的真实反馈清单
- 反馈用于修正 M3 的范围——**尤其是数据源选择与技能内容，这两项目前是拍的**

> **这个阶段的产出不是代码，是判断。** 如果用下来发现方向不对，此时掉头的成本远低于做完 M3 之后。

---

## M2 · 双旋钮策略 + macOS 沙箱 + 状态栏

**状态：主路径已落地（2026-07-31）** — Seatbelt 只读/写/白名单 Exec、TCC 探测、状态栏；出口对照见 `13-M2-EXIT-CHECKLIST.md`。**判据 12（开发签名稳定）仍未完成**，故 M2 正式出口签字保留。

**范围**：`sandbox_mode` × `approval_policy` 两维模型、Seatbelt 实现、TCC 授权引导、状态栏。M2 是**真实本机工具执行**的安全准入门槛。

> **签名与公证不在本阶段**——那属于分发工程，归 M7（DEC-026）。M2 之后仍可以是不分发的内部构建。两件事不要绑在一起：沙箱决定「能不能安全地跑工具」，公证决定「能不能发给别人」。

**出口判据**
- 沙箱逃逸用例集全部拦截（含：越出 `writable_roots` 写入、受限模式下发起网络连接、读取宿主凭据目录）
- **`.cyberguard/`、`.git`、原始证据目录在可写模式下仍不可写**（专项用例）
- TCC 未授权时给出明确提示而非静默失败
- `sandbox_impl` 正确识别；`none` 时状态栏显著告警且只允许只读档位（INV-16）
- 开发期签名标识稳定，TCC 授权不因重新构建而失效（见 `10-DEV-SETUP.md`）

**一键套件**：`./apps/desktop/scripts/run_m2_suite.sh`

---

## M3 · 可分发版完整

**状态：推进中（2026-08-02）** — 已落地：Keychain/file secrets slot、审计哈希链、本地经验库、敌对来源标记、**本地数据保护**（两级 Fernet 密钥 + 会话正文加密 + crypto-shred 删除 + 备份排除标记 + 90 天正文保留 purge）。其余见下。

**做完这个就有一个能卖的产品。** 不依赖服务端。前置是 M2（沙箱）与 M1.5（产品方向已验证）。

**范围**
1. **本地经验库** —— `VectorIndex` 端口的单机实现（真正的本地向量库，不是 gateway 薄壳）。反转自原设计，见 INV-11 / DEC-022。*已落地：`apps/desktop/sidecar/episodic.py` + `episodic.recall/record/stats`；agent 运行自动 recall/record；**无上传路径**。*
2. **本地审批与自批准标注** —— 本地确认流程，审计中标注 `approval_type: self`，界面显示"自批准"（INV-06 / INV-38）。*审计字段已默认 self；审批 UI 仍待 M4。*
3. **审计哈希链** —— 本地 append-only + 哈希链（tamper-evident），可选外发 SIEM。**不得宣称等同 WORM。** *链已落地：`audit/chain.jsonl` + `audit.verify`。*
4. **带凭据 MCP** —— Keychain 独立 slot，每个 server 只能访问自己的 slot（修正 DEC-018）。**单兵的全部外部数据都靠它**聚合 SIEM / 云平台 / 漏扫 / 工单。*slot API + stdio spawn 注入 `secret_env` 已落地。*
5. **内置安全 SOP 技能集** —— 开箱可用。用户装上去面对空技能池等于产品未完成，这不是可选项。*已落地 5 条 builtin：`alert_triage` / `cve_impact` / `incident_investigation` / `evidence_handling` / `compliance_gap`；progressive disclosure（catalog 仅 name+description，正文经 `load_skill`）。*
6. **能力档位** —— 新建会话时可选"只读咨询 / 完整作业"，**默认完整作业**（DEC-027）。不是强制隔离。*档位骨架 + readonly 无 Exec/Edit 已有。*
7. **敌对来源标记与降权** —— 工具输出 / MCP 返回 / 扫描结果默认不可信，不得改变已批准约束、不得触发能力变更、作为结论依据时须标注可溯源（INV-39）。**这是取代强制模式隔离的实质防护。** *主路径 + 专项用例：hostile 前缀、经验剥除 free-text、`auth_bounds_check` 运行结束断言档位/Exec/Edit/sandbox 未变；`tests/test_desktop_m3_skills_inv39.py`。*
8. **本地数据保护** —— FileVault 检测告警、两级密钥与会话正文加密、crypto-shredding 删除、备份排除、审计与正文保留期分离。见 `../superpowers/specs/2026-07-29-local-data-protection-design.md`。*主路径已落地：`data_crypto.py`（index + per-session Fernet 密钥）/ 加密 JSONL / `sessions.delete` crypto-shred / `sessions.purge_expired`（默认 90 天）/ `backup_exclude`（`.cg-nobackup` + macOS xattr）/ FileVault 告警。加密导出与卸载流程仍归 M7。*

**出口判据**
- **全部核心用例在无网络、无服务端配置的环境下跑通**（CI 独立 job，INV-37）
- 本地经验召回在断网时可用；无确认的自动上传路径不存在
- 审计载荷 `approval_type` 字段必填且取值正确
- **注入用例**：工具输出中埋入「忽略先前约束」类指令，断言授权范围未变、未触发能力变更、受影响结论带来源标记（INV-39）
- 审批视图关键字段不经过模型输出（静态检查）
- MCP 凭据跨 server 读取用例被拒
- **删除会话后正文不可恢复**（crypto-shred 验证）；FileVault 未开时显著告警；敏感目录已排除备份

> **advisory 模式此时即可交付**。operator 模式仍需 M2 通过。

---

## M4 · Plan Mode + 审批

**状态：主路径已落地（2026-08-02）** — 桌面 standalone Plan Mode + 自批准 UI；超时=拒绝；connected 下 segregation 本机无批准按钮。

**范围**：`_run_loop` 前置 plan 阶段（新增 `plan_ready` 事件）、Plan 审阅面板、审批弹窗与提权申请、`ApprovalService` 增加 `action_type = "execution_plan"`。

**已落地**
- `apps/desktop/sidecar/plan_mode.py`：`execution_plan` / `privilege_escalation`、超时拒绝（INV-05）、`approval_type: self` 标注（INV-06/38）
- `mock_agent`：高危/full/不可逆工具前 `plan_ready` → 等待 `plan.approve`/`reject` → `plan_approved` 后才进 `run_loop`
- RPC：`plan.approve` / `plan.reject` / `plan.list` / `plan.get`；改写后的计划入审计链
- UI：Plan 面板「自批准并执行 / 拒绝」；connected+segregation 隐藏批准按钮
- 测试：`tests/test_desktop_m4_plan_mode.py`

**出口判据**
- 高危任务执行前必经审批，**改写后的计划**入审计链 ✅
- 审批超时行为为**拒绝**（专项用例） ✅
- 涉及职责分离的审批在节点界面上**不出现批准按钮** ✅（runtime=connected）
- 沙箱拒绝可发起提权申请，批准后重试并在 `policy_events` 留痕 ✅（`privilege.py`：side-channel `privilege_required` → 批准 → 单次 elevated retry；`audit/policy_events.jsonl`）

---

## M5 · Trust Gate + 工具隔离 + 断网恢复 + 证据浏览器

**状态：主路径已落地（2026-08-02）** — Trust Gate + 证据目录/哈希 + Provider 断网暂停/恢复；Gondolin micro-VM 工具隔离层仍属后续加深（Seatbelt host 工具已在 M2）。

**范围**：project trust gate、Gondolin 形态的工具隔离层、断网暂停/恢复、证据浏览器。

**已落地**
- `trust_gate.py`：`trust.json`，项目本地默认 deny（INV-14）；builtin/approved 全局放行；`trust.set/evaluate`
- `load_context_file` / `load_project_skill_file` 过 Trust Gate；注入样本目录未信任时不进模型
- `evidence.py`：注册文件 → sha256 + `mount: read-only`；`evidence.verify` 完整性校验
- `run_pause.py`：Provider 网络错误 → checkpoint + `run_paused`（UI「已暂停」）；`agent.resume` 从 messages 恢复
- 测试：`tests/test_desktop_m5_trust_evidence_pause.py`

**出口判据**
- 不可信目录中的本地上下文文件 / 技能**不被加载**（专项用例，含 prompt 注入样本） ✅
- **断连后恢复，任务从暂停点继续**——checkpoint messages + resume；状态栏「已暂停」 ✅（30 分钟窗口由 checkpoint 文件保留；无 TTL 强制清理）
- 证据以只读挂载，界面显示 sha256 与只读状态 ✅（RPC + status evidence count；完整拖拽 UI 可再抛光）
- Gondolin micro-VM 隔离 ⚠️ 仍用 M2 Seatbelt；完整 micro-VM 未做

---

## M6 · 可选连接态（connected）· **按需，非既定阶段**

**增强，不是前置。** 没有它产品也完整。

> **单兵用户不会部署服务端**（DEC-027）。本阶段**不占当前排期**，有企业客户时再启动。`agent-core` 的端口抽象已保证将来可加。

**范围**：注册配对、策略拉取（L1 收紧）、审批上收（本地确认升级为服务端审批队列）、审计事件上报、经验双向同步、控制通道（kill switch / 远程 abort）、断开留痕。

**注意协议方向已反转**（DEC-025）：节点是主动方，服务端是策略与存证的提供方。原 `poll` 派单与 `GatewayMessage` 任务状态机**基本不需要**；`manifest` 降为可选；`execute-tool` 保留但可选。`09-GATEWAY-PROTOCOL.md` 须按此方向重写。

**出口判据**
- 策略合并取更严者；服务端不得放宽超过本地设定（INV-41）
- 不要求上传全量会话（L2 不做，DEC-023）
- 断开在断开前上报并留痕；上报失败时本地留痕
- 经验上传逐条确认且经脱敏
- `protocol_version` 协商：未知的必需版本显式失败，不静默按旧语义执行

---

## M7 · 交付工程

**状态：工程主路径已落地（2026-08-03）** — 加密导出 / 卸载 / 更新验签 / EDR·公证文档 / **electron-builder 骨架 + 应用内导出·卸载 UI**；**真实 Developer ID 公证与 EDR 实机验证仍待证书与客户环境**。

**不是功能，是发布前置条件。** 混进 M2 会被当成次要的。

**范围**
1. **签名与公证流水线** —— Developer ID + notarization（DEC-026）。*文档：`15-NOTARIZATION-AND-UNINSTALL.md`；骨架：`electron-builder.yml` + `scripts/notarize.cjs`（无证书 dry-run）+ `npm run pack:check`；真签待证书。*
2. **自动更新通道** —— 更新包独立签名强制验签、更新源证书固定、防降级、更新动作进审计（INV-42）。*已落地：`update_verify.py` Ed25519 + sha256 + 防降级；RPC `update.verify`；篡改/降级/错误密钥用例。*
3. **卸载与残留清理 + 加密导出** —— *已落地：`uninstall.py` / `export_bundle.py`；RPC；**UI**：Context → Data 面板 + 托盘菜单；Export 走系统另存为。*
4. **EDR / MDM 白名单指引** —— *已落地文档：`14-EDR-MDM.md`；实机勾选清单待客户 EDR。*
5. **公证上传的对外说明** —— *见 `15-NOTARIZATION-AND-UNINSTALL.md` §A。*

**出口判据**
- 篡改更新包 / 降级安装 / 中间人，三类用例全部被拒 ✅（单测）
- 干净机器上双击安装成功，无需用户关闭 Gatekeeper ⚠️ 需公证证书
- 卸载后残留清单与文档一致 ✅（inventory + 文档 §B + UI）
- EDR 指引在至少一款主流 EDR 上验证通过 ⚠️ 文档已备，实机待做
- 无证书环境下 `pack:check` 通过且不误报已公证 ✅

---

## 二期（不在本期范围）

Windows / Linux 平台支持。这是**已知并主动接受的推迟**，不是遗漏。

**本期必须守住的约束**：沙箱能力从 M0a 起就放在端口接口之后，`sandbox_mode` 语义保持平台无关的声明式描述，`.sbpl` 生成只存在于 macOS 实现模块内，`node_caps.sandbox_impl` 从第一天就上报且服务端派单逻辑一次写对。守住这条，二期加平台只需新增实现模块。

**重新评估触发条件**（满足任一即启动**支线 W · Windows 隔离能力调研**，1–2 周扔掉型原型，只回答"受限令牌 + ACL + Job Object 能拦住什么"）：出现 Windows 终端的目标客户；进入企业 SOC 场景的 GA 准备；`sandbox_mode` 权限模型需要作为对外正式承诺发布。

其余二期候选（优先级排序）：**操作 Profile**（"日常调查" / "应急响应已授权"一键切换沙箱+审批档位）、**服务端** fan-out 工作区隔离与限流（INV-23）、确定性 Workflow 编排、本地个人记忆层（`MEMORY.md` 索引 + pruning）、`/remember` 显式标注与失败经验记录。

> **勿与 LLM Profile 混淆**：`local_only` / `approved_remote` 的出网档位是**首版必需**（DEC-017、09 §6.3），不在二期。两者都叫 Profile 但不是一回事，见术语表。

> 注意："子 agent 工作区隔离"曾被列为**桌面端**二期候选，现已改判归服务端范畴——节点不做 spawn。见 DEC-012 / INV-22。

---

## 与服务端既有问题的关系

以下是重构中发现的**服务端遗留问题**，不属于桌面端范围，但会在 M0a 顺带触及。单独立项，不要夹带进桌面端提交：

1. `conversations.messages_json` 是整块 TEXT 的 read-modify-write，多 worker 下**无锁并发丢消息**（README 默认 `API_WORKERS=4`）
2. 两套独立的上下文压缩实现（`context_compressor.py` 8000 est-token vs `internal_agent._maybe_compact` 24000 字符），阈值、提示词、语言均不同
3. Skills 全文注入 system prompt，未做按需加载
4. `agent_episodes` 只增不减，且 `_maybe_record_episode` 硬编码 `success=True`，失败经验一条不存
5. `master.py` 两处**用户可控输入直接驱动控制流**且绕过 guardrail：`_parse_intent_node` 关键词触发 group chat、`_validation_node` 关键词判定高风险
6. **跨 agent 派发缺少权限继承校验（提权路径，优先级最高）**——`_parse_intent_node` 由 LLM 的 `parse_intent` 输出直接携带 `agent_id`，`run_task` 拿它就 `executor.execute()`，中间没有"请求方权限 ≥ 目标 agent 权限"的比较。而各 `AgentConfig` 的 `permission_level` / `autonomy_tier` / `governed` 是不同的，一段被注入的内容若能把意图解析引导到高权限 agent 上即完成提权。同类问题参见 OpenClaw 的沙箱逃逸公告 GHSA-p7gr-f84w-hqg5。修复方向见 INV-21。
7. `_sub_agent_executor_node` 的 `asyncio.gather` fan-out **无并发上限、无嵌套深度限制、允许不指定目标的派发**。见 INV-23。
8. 安全边界与功能路径共用同一套 best-effort 异常处理模式。功能性降级（经验召回、搜索、OCR 失败）静默 no-op 是好设计，但该模式不可蔓延到沙箱初始化、策略加载、审计写入等安全路径。见 INV-25。

9. **token 估算对中文严重低估（会导致线上报错，优先级高）** —— `context_compressor.estimate_tokens` 用 `total_chars // 4`，注释写着 "Conservative for CJK content"。**这个判断是反的**：`4 chars ≈ 1 token` 是英文经验值，中文一个汉字通常 1–1.5 token，`chars//4` 把 4 个汉字算成 1 token，**低估约 4–6 倍**。
   本系统是中英双语、大量中文提示词与对话，实际 token 数远超估算，**该触发压缩时不触发**，直接撞上下文上限报错。
   修法：按字符类别加权（CJK ~1.5、ASCII ~0.25）先止血，后续接真实 tokenizer。

10. **工具输出截断只有一个方向** —— `_truncate_tool_result` 保留前 8000 字符、丢弃其余。**安全场景的价值常在尾部**：nmap 的发现在 banner 之后、日志的关键事件在末尾、命令的错误信息在最后。这是在系统性丢弃关键证据。
    修法参照 pi：`truncate_head` / `truncate_tail` 两个方向按工具选择，双重约束（行数 **或** 字节数，先到先算）。与"全文落库 + 分页读"不冲突，两者都要。
