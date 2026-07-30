# CLAUDE.md

本仓库的工作约定。**每次开始任务前先读本文件，以及 `docs/desktop/04-INVARIANTS.md`。**

---

## 这是什么

CyberGuard 是网络安全领域的多 Agent 平台。仓库内有**两个产品形态**，共享同一套 agent 内核：

1. **服务端平台**（已上线，`app/` + `webui/`）—— FastAPI + LangGraph + Postgres/pgvector + Redis + Celery + React 后台。负责策略、审批、审计、治理、经验库。
2. **桌面端**（建设中，`apps/desktop/`）—— Electron + React + Python sidecar。**单机自洽、完整可用**；服务端连接是可选增强（DEC-022）。

**定位：单兵全能工具**（DEC-027）。面向**没有服务端**的单个安全从业者——一个人既看态势也下场查，不分角色。Web 端 21 个 Tab 功能不减，对已部署客户桌面端无增量价值；**桌面端的价值只对没有服务端的人成立**。

**standalone 必须自洽完整，connected 只做增强**（INV-37）。`connected` 降为**按需**——单兵不会部署服务端，M6 不占当前排期。

**两条交付线**（DEC-028）：**自用验证版**（M1.5，禁止分发，砍掉沙箱/公证/加密，最快验证产品方向）与**可分发版**（M2→M3→M7，全套安全工程）。

首发平台 **macOS**。Windows / Linux 推迟至二期。

---

## 仓库布局（目标态）

```
app/                     服务端 FastAPI 应用（现有，勿大改）
  agents/                LangGraph Master Agent
  services/              业务服务层
  routers/               HTTP 路由（含 gateway.py —— 节点协议）
  models/ schemas/ core/
packages/
  llm-router/            【新】纯 Provider 抽象（Python），不含任何 agent 概念
  agent-core/            【新】部署无关的 agent 内核（Python），服务端与节点共用
  ui-shared/             【新】共享 React 组件 / i18n / 主题，不依赖 agent 概念
apps/
  desktop/               【新】Electron 壳 + 渲染层 + Python sidecar
webui/                   服务端 21-Tab 管理后台（逐步依赖 ui-shared）
tests/                   既有基线测试 —— 重构的安全网，不许绕过
docs/
  desktop/               桌面节点规划文档 —— 架构决策 / 里程碑 / 不变量的**权威来源**
    00-README.md         索引与阅读顺序
    04-INVARIANTS.md     设计哲学 + 42 条硬约束（开工前必读）
    09-GATEWAY-PROTOCOL.md  **可选**连接态协议（M6 才需要）
    10-DEV-SETUP.md      **开发环境的坑**（TCC 授权失效、签名、EDR）——动手前先读
    11-OPEN-QUESTIONS.md **故意没定的事**，含各自阻塞的里程碑
  superpowers/specs/     功能设计文档，命名 YYYY-MM-DD-<name>-design.md
                         其中 2026-07-27-desktop-node-design.md 是详细规格，
                         与 docs/desktop/ 冲突时**以后者为准**
```

---

## 设计哲学（遇到文档没覆盖的情况时，按这五条推导）

安全 agent 与编码 agent 的前提是反的：**动作大量不可逆**、**输入天然敌对**（处理的是攻击者写的样本与日志）、**agent 自身是高价值目标**、**产出要向第三方举证**。

- **P1 · 默认拒绝**，能力靠显式授予
- **P2 · 不可逆动作前置审批**，审批对象是意图而非结果
- **P3 · 能力变更是特权操作**（新工具 / 新技能 / 新权限一律过人；agent 只能提议）
- **P4 · 权限主体数量最小化**（每多一个，审计成本上一台阶）
- **P5 · 降级必须显式可见**（功能性失败可 best-effort；**安全边界失败必须响**，不许 `except: pass`）

完整推导见 `docs/desktop/04-INVARIANTS.md` 第一部分。

## 硬性约束（违反即回退）

完整清单见 `docs/desktop/04-INVARIANTS.md`（42 条）。最常被无意违反的十五条：

1. **凭据永不进沙箱。** 工具进隔离层，域凭据 / API key / 节点密钥留宿主。
2. **`.cyberguard/`、原始证据目录在任何沙箱模式下对 agent 只读。** 被注入的 agent 第一件事就是改策略和擦审计。
3. **审批超时 = 拒绝。** 不是超时用默认值。
4. **职责分离审批按运行态分级。** connected 走服务端、界面无批准按钮；standalone 降级为本地确认但**必须标注 `approval_type: self`**，不得与职责分离审批混同记录（INV-06 / INV-38）。
5. **沙箱能力必须是平台无关的声明式描述。** Seatbelt / `.sbpl` 的任何假设不得泄漏到上层逻辑。
6. **全量对话与证据不出本机**，只上报审计事件、结果摘要、artifact 哈希。
7. **节点不做子 agent spawn。** 并行止于同一 agent 上下文内的工具并行，不产生新权限主体（INV-22）。
8. **跨 agent 派发必须校验权限继承**，目标权限不得高于当前上下文（INV-21）。
9. **敌对来源内容不得驱动特权动作。** 工具输出 / MCP 返回 / 扫描结果**默认不可信**——不得改变已批准约束、不得触发能力变更、作为结论依据时须标注可溯源（INV-39）。
10. **策略管线与审计事件是两套机制，不许合并。** 管线可阻断可脱敏；事件纯观察、不可否决、**emit 必须 await**（INV-28 / INV-29）。
11. **工具参数必须过 schema 校验才执行**；**有副作用的工具默认串行**；**错误必须结构化**，不许靠字符串前缀判断（INV-30 / 31 / 32）。
12. **压缩不得丢失授权边界。** 摘要固定六段，Constraints 段必须含当前授权范围、目标白名单、沙箱模式（INV-33）。
13. **节点不接收任意 shell 命令字符串。** 结构化命令（可执行文件 + 固定参数 + schema 校验的变量参数 + 本地白名单）；需要 shell 语义的走集中代执行（INV-35）。
14. **standalone 必须自洽完整。** 核心工作流不得依赖服务端存在（INV-37）。
15. **安全降级必须显式标注，不得伪装。** 本地确认 ≠ 职责分离审批；本地哈希链 ≠ WORM；用户能关的开关 ≠ 安全边界（INV-38）。

---

## 技术栈（不要擅自替换）

详见 `docs/desktop/02-TECH-STACK.md`。要点：

- 桌面壳 **Electron**（非 Tauri，理由见 DECISIONS-002）
- 渲染层复用 React 19 + Vite + Tailwind v4，不引入新 UI 框架
- 壳 ↔ sidecar 走 **stdin/stdout JSONL，不开监听端口**
- sidecar 打包用 **PyInstaller onedir**（不是 onefile）
- Python ≥ 3.11，包管理 `uv`；TS 侧 npm workspaces
- 本地存储：会话为树状 JSONL + SQLite 索引；**本地经验库必须建**（standalone 无服务端可查，见 INV-11）
- 带凭据 MCP 走 Keychain 独立 slot，每个 server 只能访问自己的 slot

---

## 工作流约定

**改动前**：先确认对应的设计文档存在。新功能按既有惯例在 `docs/superpowers/specs/` 建 `YYYY-MM-DD-<name>-design.md`，写完设计再写代码。

**测试**：`pytest -q`（需 Postgres+pgvector，见 README）。重构 `packages/agent-core` 时，每抽一个端口跑一次全量，**不允许出现"先红后绿"跨越多次提交**。

**迁移**：`alembic -c alembic.ini upgrade head`。改模型必须配迁移。

**提交粒度**：一个端口 / 一个界面 / 一个协议字段为一次提交。不要把服务端重构和桌面端新功能混在一个提交里。

**改动已定结论前**：`docs/desktop/05-DECISIONS.md` 的决策带稳定性标记（🔒 稳定 / ⚖️ 较稳 / 🚧 未定 / ⛔ 已作废）。
- 🔒 与 ⚖️ 的结论**不要自行推翻**。发现新材料与之冲突时，**先说明"这会推翻 DEC-xxx，要不要为此改"**，等人决定，不要直接改文档或代码。
- 🚧 的部分**尚未定稿**。所有故意未定的事项登记在 `docs/desktop/11-OPEN-QUESTIONS.md`，遇到时**先查那里再问**——很可能是主动推迟的，不是漏写。

---

## 当前阶段

见 `docs/desktop/03-ROADMAP.md`。现处于 **M0a-1 · 结构：只搬不改**。

> 路线图关键节点：M1（壳+骨架，mock）→ **M1.5 自用验证版（禁止分发，验证产品方向）** → M2（沙箱）→ M3（可分发完整）。**M1.5 的产出不是代码是判断**——方向不对时掉头，成本远低于做完 M3 之后。

**M1.5 唯一验收场景**（现在就按此定边界）：见 `docs/desktop/12-M1.5-GOLDEN-PATH.md` —— 告警分诊 → 只读调查 → Markdown 报告。不为 21 Tab 复刻做抽取。

范围：抽 `packages/llm_router` 与 `packages/agent_core`、建立 Operations 抽象、工具执行五步管线骨架就位（`validate_arguments` 先做 pass-through）、审计事件流。

**硬判据：基线测试集原样全绿，服务端对外行为零变化。** 当前本地可收集 365 个用例，精确数量以 CI 的 `pytest --collect-only` 为准。本阶段任何行为改变都是错误——参数校验、默认串行、结构化错误、压缩加固全部属于 M0a-2，不要提前做。测试挂了就是搬运出错，不是设计问题。

**M0a 期间不要写任何桌面端代码。** 内核没抽干净就开壳，会把 Electron 的假设倒灌进服务端。

### 服务端功能面冻结（M0a–M1.5）

- **默认不接** Web 端新 Tab / 新运营能力（GRC 扩展、新 SSO、新群聊玩法等）。
- 允许：阻塞 M0a 抽取的 bugfix、安全边界修复、基线测试维护、为包边界服务的薄适配层。
- 新想法进 `docs/desktop/11-OPEN-QUESTIONS.md`，不进主干。

### M0a-1 抽取顺序（一次一个，每步全绿）

1. ~~`packages/llm_router`：resilience + pure utils~~ ✅（业务方法仍在 `app/`；chat/stream/embed 纯路径可再迁）
2. ~~Operations 抽象 + 工具五步管线骨架（`validate_arguments` pass-through）~~ ✅
3. ~~`packages/agent_core`：run loop / compressor / compact / loop_utils~~ ✅
4. ~~审计事件流骨架（emit await，默认无订阅）~~ ✅
5. 包内 lint：`llm_router` 无 agent 概念；`agent_core` 无 `app.*` / sqlalchemy / redis / celery / fastapi（已有 AST 用例）

**M0a-1 主路径完成。** **M0a-2 语义（进行中/首批已落地）**：
- ✅ INV-30 `validate_arguments` schema 校验
- ✅ INV-31 工具默认串行（parallel 需全员 opt-in）
- ✅ INV-32 结构化 `is_error`（不再靠 `ERROR` 子串）
- ✅ 加权 token 估算 + 六段摘要 + Constraints 注入 + 当前 turn 保留（INV-33/34 基础）
- ⏳ 模型表 `context_window` / `max_output_tokens` 列与探测、方向性截断、exclude_from_context、llm-router cache/thinking

---

## 不要做的事

- 不要重写服务端。它有基线测试和 21 份设计文档，问题都是局部的。
- 不要在 M0a–M1.5 给服务端堆新功能面（见上方冻结）。
- 不要把 RBAC / SSO / 组织级 GRC / 不可篡改审计当成单机能做到的事——它们是 connected 的价值（DEC-023）。
- 不要让 standalone 依赖服务端（INV-37），也不要让本地降级伪装成完整能力（INV-38）。
- 不要做 LAN 自动发现或节点间 P2P（企业网里那是横向移动通道）。
- 不要在节点侧生成公开可访问的报告 URL。
- 不要用关键词匹配驱动控制流（现有 `master.py` 里有两处遗留问题，见 INV-13，勿模仿）。
- 不要为了"更现代"替换现有依赖。
- 不要在 M0a-1 提前做 M0a-2 语义变更（参数校验、默认串行、结构化错误、压缩加固）。
