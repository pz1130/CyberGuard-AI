# 08 · 记忆设计

状态：定稿 · 2026-07-27

桌面节点的记忆是**分层**的，不是单一机制。四层各有存储位置、生命周期与读写路径，**不要混用**。

---

## 1. 四层总览

| 层 | 存哪 | 生命周期 | 谁写 | 里程碑 |
|---|---|---|---|---|
| **会话** | 节点本地：树状 JSONL + SQLite 索引 | 长期，可 fork | 节点 | M1 |
| **上下文压缩** | 进程内 → 作为条目写回会话 | 单次运行 | `agent-core` | M1（复用） |
| **经验（Episodic）** | **本地向量库**；connected 时叠加服务端共享库 | 跨会话 | 本地蒸馏；上传须逐条确认 | M3 |
| **个人偏好** | 节点本地：`MEMORY.md` + 主题文件 | 长期，定期 pruning | 节点 | 二期 |

---

## 2. 会话层

### 结构

本地 **append-only JSONL**，每条带 `id` / `parent_id`，构成树而非线性列表。SQLite 只存元数据索引（标题、时间、分支关系、token 统计），**不存消息正文**。

```
{"id": "...", "parent_id": "...", "type": "message"|"tool_call"|"tool_result"
                                        |"compaction"|"branch_summary"|"plan",
 "role": "...", "content": ..., "ts": "..."}
```

### 三条精确规则（参照 pi）

1. **节点只记 `parent_id`，父节点不维护子列表。** 这是 append-only 不可变的关键——有子列表就意味着写入时要回头改父节点。
2. **用一个 `leaf_id` 标记当前会话末端。** 追加 = 写新条目 + 移动 `leaf_id`，O(1)。
3. **回溯只移动指针，不删节点。** 分叉就是把 `leaf_id` 往回移，之后的追加自然形成新分支。**所有历史分支永久保留在磁盘上**——这正是取证场景需要的。

加载时从 `leaf_id` 向 root 遍历收集条目，再按类型分发重建线性上下文。

### 为什么是树

从任意历史点分叉重跑——"换个模型重试这一步"、"对比两条调查路径"在应急响应里是高频操作。`parent_id` 一旦存在，fork 就是免费的。

### 条目类型分三组

| 组 | 类型 | 说明 |
|---|---|---|
| **产生消息** | `message` / `custom_message` / `compaction` / `branch_summary` | 参与重建模型上下文 |
| **影响状态** | `model_change` / `policy_change` | 不产生消息，但改变后续行为 |
| **纯元数据** | `label` / `session_info` / `plan` / `policy_event` | 仅供界面与审计 |

**`model_change` 对取证有独立价值**——"这一步是用哪个模型跑的"是会被审计问到的问题，不能只记在全局配置里。`policy_change` 同理（沙箱模式或审批档位中途变更必须留痕）。

### `exclude_from_context` 标记

条目可标记为**界面可见、审计可见、模型不可见**。

证据文件原文、审批记录、`policy_events` 属于这一类：必须留痕，但不该占模型上下文。没有这个标记就只能二选一——要么撑爆上下文，要么完全不留痕。

### 与服务端的区别

服务端是 `conversations.messages_json` 整块 TEXT 的 read-modify-write（多 worker 下有无锁并发丢消息问题，见 `03-ROADMAP.md` 遗留问题 1）。**节点侧从第一天就用对的结构，不要照抄服务端实现。**

### 关键约束

**append-only 意味着压缩不是原地重写。** 压缩产生一条 `compaction` 类型的新条目（记录被压缩的区间与摘要），原始消息保留在文件里。加载时按条目类型重建有效上下文。

理由：取证场景下"agent 当时到底看到了什么"必须可回溯。压缩掉就查不回来，等于自毁证据链。

---

## 3. 上下文压缩层

**直接复用 `packages/agent-core` 的实现，与服务端同一份代码，不单独做。**

行为：阈值触发（按模型上下文窗口减预留，而非写死绝对值）→ 保留尾部若干条 → 中间段交 LLM 生成结构化摘要 → 切点只落在合法消息边界，绝不切在 tool result 中间、不产生孤儿 tool 消息。

**fork 时的分支摘要**：切换到另一分支时，对被放弃分支的工作生成 `branch_summary` 条目注入新分支上下文，避免重复劳动（借鉴 pi 的 branch summarization）。

---

## 4. 经验层（Episodic）

> ⚠️ **本节已按 DEC-022 反转。** 原设计是"节点不建本地向量库，经验留服务端"——那是 standalone-first 之前的结论，已作废。

### 位置：standalone 建本地库，connected 叠加共享库

| 运行态 | 形态 |
|---|---|
| `standalone` | **必须建本地经验库**。没有服务端可查，不建等于没有经验积累 |
| `connected` | 本地库仍在（个人经验）+ 服务端共享库（组织经验），两层分工不混 |

`VectorIndex` 端口的单机实现必须是**真正的本地向量库**，不是委托给服务端的薄壳。sidecar 依赖清单要相应重算——节点侧现在需要嵌入能力。

### 读路径：召回

`standalone`：查本地库。**断网必须可用**，这是 INV-37 的一部分。

`connected`：本地库 + 服务端 `POST /api/v1/gateway/episodic/recall`（协议见 09 §9），结果合并后注入"过往成功经验（参考）"段落。服务端侧请求只含任务摘要、agent scope、`top_k`、LLM profile；**节点不得提交任意 SQL、embedding 或 `agent_id` 覆盖值**。

### 写路径

`standalone`：本地蒸馏、本地入库。

`connected`：本地照常入库；**上传服务端必须可选、逐条显式确认、且经脱敏**（INV-11）。不得做成自动同步——本地经验里可能含客户敏感信息与调查细节。服务端侧的写入仍由服务端在收到 report 后蒸馏完成，节点不直接写共享库。

### 跨模式污染防护

经验条目必须带 **`source_trust`**（`trusted` / `hostile`）——按**内容来源可信度**标记，不是按模式。

召回 `hostile` 来源的经验时，**只取结构化字段**（工具序列、成功标记、耗时），**不取自由文本 `outcome`**。

理由：operator 的经验蒸馏自扫描结果，其中可能含攻击者构造的内容。经验库是跨会话共享的，会**绕过 INV-39 的会话隔离**把污染内容带进 advisory 的审批上下文。自由文本是注入载体，结构化字段不是。

见 INV-39 与 `../superpowers/specs/2026-07-29-mode-switching-design.md` §4。

### 离线降级：no-op

召回失败（服务端不可达、embedding 失败、库损坏）→ **降级为空，不中断运行**。

这个性格继承现有 `app/services/episodic_memory.py`：embed 失败、DB 失败、表不存在，全都只记日志不抛。agent 拿不到历史经验照样能跑，只是少了先验。

> 注意与 INV-25 的分界：经验召回属**功能性降级**，可以静默 no-op；沙箱初始化、策略加载、审计写入属**安全边界**，失败必须响。两者不可混用同一套错误处理。

### 顺带修复的服务端缺口

现有 `_maybe_record_episode` 硬编码 `success=True`，**失败经验一条不存**——而 `agent_episodes.success` 字段和召回侧的 `WHERE success = true` 都已预留好，等于半个功能闲置。安全场景里"这条路走不通"的价值不低于成功路径。

---

## 5. 个人偏好层（二期）

### 只存什么

分析师的个人习惯：惯用工具、报告格式偏好、对工作方式的反馈、外部系统引用。

### 明确不存什么

代码模式、架构细节、文件路径、命令历史、Git 记录——**这些现查即可，写进记忆只会过期和污染上下文**。（借鉴 claude-code-best 的"不存清单"。）

### 结构与限额

`MEMORY.md` 作索引 + 主题文件（如 `report_style.md`、`tool_preferences.md`）。索引限额：200 行 / 25KB，单条 < 150 字符。

### 整合与淘汰

四阶段：orientation（扫已有）→ signal gathering（从会话收新信号）→ consolidation（并入已有主题）→ pruning（删过期、压回限额）。

触发：手动命令随时可跑；自动触发需同时满足开关开启、距上次 ≥24 小时、≥N 个新会话。

### 与组织经验分层

个人偏好是"这个人怎么工作"，组织经验是"这类任务怎么做"。**两层互不污染**，个人偏好不上报服务端。

---

## 5.5 memory 与 skill 的分工

借 Hermes 的定义，边界很清楚，直接采用：

| | 存什么 | 何时在上下文 |
|---|---|---|
| **memory** | 小的、持久的事实（偏好、环境事实、约定） | **始终在** |
| **skill** | 较长的过程（怎么做某类任务） | **仅相关时加载**（progressive disclosure） |

这条定义解决了现有系统里一个长期含糊：skills 全文注入 system prompt、episodic 走向量召回，两者的职责边界从未定义过。

**采用 progressive disclosure**：system prompt 只放 skill 的名称 + 一行描述，模型判断需要时用工具取回正文。现有 `SkillLoader.get_skill_by_name` 已具备条件，暴露成工具即可（属 `03-ROADMAP.md` 遗留问题 3）。

### 但不采用自动学习闭环

Hermes 会在任务完成后**自动创建 skill 文件并立即可用**，还允许 agent 用 `skill_manage` 中途 patch 自己的技能。

**这条在安全产品里不能要**——agent 自己写技能、自己加载、自己执行，等于自我提权加持久化后门；一次成功的 prompt 注入可以留下一条永久生效的技能。

正确形态：agent **提议**技能（附来源 episode 与证据）→ 待审队列 → **人工批准后**才进技能池。与 Plan Mode 是同一哲学（P2 / P3），只是审批对象从"执行计划"换成"能力变更"。

见 INV-20、DEC-013。

---

## 6. 其余记忆性数据（非记忆层，勿混淆）

| 数据 | 性质 | 位置 |
|---|---|---|
| **Skills** | 内置 SOP 集 + 用户创建（草稿→批准）；connected 时叠加组织下发 | `skills/` 生效集、`skills/drafts/` 草稿（**不参与 system prompt 装配**） |
| **知识库** | 本地语料；connected 时可查组织库 | 本地库 |
| **策略快照** | 本地策略；connected 时与服务端策略取更严者 | `.cyberguard/policy.json`，对 agent 强制只读（INV-03） |
| **审计缓冲** | 待上报事件（仅 connected 需要） | `.cyberguard/audit-buffer/`，对 agent 强制只读 |

---

## 7. 本地存储布局

```
~/Library/Application Support/CyberGuard/
  .cyberguard/            ← 对 agent 强制只读（INV-03）
    policy.json           服务端下发的策略快照
    audit-buffer/         待上报审计事件
  sessions/
    <session-id>.jsonl    树状会话正文（append-only）
    index.db              SQLite 元数据索引
  episodic/               ← 本地经验库（向量索引 + 元数据）
  skills/
    builtin/              内置安全 SOP 集（随安装包发布，只读）
    approved/             已批准生效的技能
    drafts/               草稿，**不参与 system prompt 装配**
  memory/                 ← 二期
    MEMORY.md             个人偏好索引
    <topic>.md            主题文件
  cache/
    manifest.json         connected 时下发的组织技能 / 工具快照
```

**技能优先级**：内置 > 组织下发（connected）> 本地已批准。同名冲突时高优先级胜出并告警（与 INV-27 方向一致）。

**节点密钥不在此处** —— 走 Electron `safeStorage` 进 Keychain（INV-02）。

---

## 8. 不做清单

| 不做 | 原因 |
|---|---|
| **自动**上传本地经验到服务端 | 须逐条显式确认且经脱敏（INV-11）。~~原"不建本地向量库"已反转~~ |
| 节点直接写服务端 `agent_episodes` | connected 下写入路径须唯一且可审计，见 §4 |
| 压缩时原地重写会话文件 | 破坏可回溯性与证据链，见 §2 |
| 个人偏好上报服务端 | 两层分工，避免污染组织经验 |
| 全量对话上报 | INV-10，只上报审计事件、摘要、哈希 |
| 草稿技能参与 system prompt 装配 | 未批准的能力不得生效（INV-20） |

---

## 9. 未决问题

以下留待实施期决定，**不要默认实现**：

1. **个人偏好跨机同步**：分析师用两台终端时如何处理。当前设计是各机独立，未同步。
2. **会话文件的保留策略**：取证会话可能包含敏感内容，本地保留多久、是否加密静态存储、如何安全删除。
3. **`branch_summary` 的成本控制**：每次 fork 都调一次 LLM，频繁分叉时的开销上限。
