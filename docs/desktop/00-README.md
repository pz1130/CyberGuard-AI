# CyberGuard 桌面节点 · 规划文档索引

本目录是桌面节点的 high-level 规划。**开工前按顺序读完，实施细节在各里程碑内决定。**

| 文档 | 作用 | 什么时候读 |
|---|---|---|
| `01-ARCHITECTURE.md` | 产品边界、进程模型、共享包、界面形态 | 开工前必读 |
| `02-TECH-STACK.md` | 选型与禁用清单 | 开工前必读；引入新依赖前复查 |
| `03-ROADMAP.md` | 里程碑与出口判据 | 每个阶段开始与结束时 |
| `04-INVARIANTS.md` | **不得违反的硬约束** | 开工前必读；每次涉及权限/审批/数据边界时复查 |
| `05-DECISIONS.md` | 已定决策与理由 | 想推翻某个设计前必读 |
| `06-GLOSSARY.md` | 统一术语 | 命名时 |
| `07-FEATURE-MATRIX.md` | **服务端 × 桌面端功能对照** | 想给桌面端加功能前必查 |
| `08-MEMORY.md` | 四层记忆的存储、读写路径、离线降级 | 涉及会话 / 经验 / 偏好时 |
| `09-GATEWAY-PROTOCOL.md` | **可选**连接态协议（M6 才需要） | 做 connected 相关功能前必读 |
| `10-DEV-SETUP.md` | **开发环境的坑**（TCC 授权、签名、EDR） | **动手前先读，能省大量排查时间** |
| `11-OPEN-QUESTIONS.md` | **故意没定的事**（含阻塞的里程碑） | 觉得某处没写清楚时先查这里 |
| `12-M1.5-GOLDEN-PATH.md` | **自用验证的唯一验收场景**（告警分诊闭环） | M0a 定边界时读；进 M1.5 前必读 |
| `13-M2-EXIT-CHECKLIST.md` | **M2 沙箱出口判据对照与逃逸套件** | 做/验收 M2 时；出口签字前 |
| `14-EDR-MDM.md` | **EDR/MDM 白名单与行为画像** | 交付 / 客户安全评审前 |
| `15-NOTARIZATION-AND-UNINSTALL.md` | **公证说明 + 卸载/导出** | 发布与卸载前 |

配套：
- 仓库根 `CLAUDE.md` —— 工作约定与常犯错误清单
- `../superpowers/specs/2026-07-27-desktop-node-design.md` —— 详细设计规格（协议字段、界面规格、平台细节）

---

## 三十秒版本

一个装在 macOS 上的 Electron 客户端，**单机自洽、完整可用**。定位是**单兵全能工具**——面向没有服务端的单个安全从业者，一个人要覆盖告警分诊、漏洞评估、事件调查、取证分析、合规检查、报告输出。取向**广而不深**。

数据来源靠 MCP 连外部系统（SIEM、云平台、漏扫、工单），不依赖任何服务端。

Web 端 21 个 Tab 功能不减。**对已部署 CyberGuard 的客户，桌面端没有增量价值**——它的价值只对"没有服务端的人"成立。

如果将来有企业客户，可**按需**配对进入 `connected`，获得职责分离审批、不可篡改审计、跨人共享、组织视图、强制策略五项单机做不到的能力。

**先做自用验证版**（M1.5，禁止分发）——目前没有客户，最好的第一个用户是开发者自己。

## 读之前先看稳定性

这套文档是分十几轮长出来的，中间有过多次修正。**不是所有结论都同等可靠**，`05-DECISIONS.md` 顶部有分级：

| 标记 | 含义 | 可否作为定论 |
|---|---|---|
| 🔒 | 从未改动，多条独立理由支撑 | **可以** |
| ⚖️ | 改过一次或新定不久，改后理由更硬 | 基本可以 |
| 🚧 | 明确会变，或对应文档尚未按新方向重写 | **不要**，等冻结 |
| ⛔ | 结论作废，保留原论证作记录 | 看取代它的那条 |

**已知未冻结的事项全部登记在 `11-OPEN-QUESTIONS.md`**，每条注明卡在哪、需要什么输入、哪个里程碑之前必须定。觉得文档某处没写清楚时，**先查那里**——很可能是故意留的，不是漏的。

**变更约定**：读到可能推翻已定结论的新材料时，**先说明"这会推翻 X，要不要为此改"，不要直接改完再通知**。

---

## 最容易走偏的五个地方

1. **把 standalone 做成残废。** 核心工作流不得依赖服务端存在（INV-37）。standalone 一残，"单机可用 + 可选连接"就退化成"服务端的卫星"。
2. **在节点侧重写 agent 循环。** 那些守卫逻辑每条都是一次线上问题换来的，重写等于归零。见 DEC-006。
3. **让沙箱的平台细节渗进上层。** `.sbpl` 只能存在于 macOS 实现模块内，否则二期加平台要重来。见 INV-15。
4. **把审批做成本地弹窗就完事。** 涉及职责分离的必须走服务端，节点界面上不出现批准按钮。见 INV-06。
5. **让安全降级伪装成完整能力。** 本地确认不是职责分离审批，本地哈希链不是 WORM，用户能关的开关不是安全边界——必须显式标注（INV-38）。

---

## 当前状态

**M0a–M5 功能主路径 + M7 交付工程主路径已落地**（分支 `security-enhance`；**禁止分发**直至 Developer ID 真公证）

**已落地**

- **M0a** 完成：`packages/llm_router` + `packages/agent_core`
- **M1–M1.5**：Electron + JSONL sidecar + live LLM 路径 + MCP stdio
- **M2**：Seatbelt 双旋钮、host_* 沙箱工具、TCC 探测、逃逸套件（evidence/secrets 只读 + 网络探针；见 `13-M2-EXIT-CHECKLIST.md`）
- **M3–M5**：Keychain secrets、审计哈希链、本地经验库、敌对来源、会话加密/crypto-shred、SOP progressive disclosure、Plan Mode、Trust Gate、证据/断网恢复
- **M7 工程**：加密导出 / 卸载 / 更新验签 / EDR·公证文档 + `electron-builder` 骨架 + 应用内导出/卸载 UI
- **服务端遗留 #1–#10**：会话锁、progressive skills、INV-13/21/23/25、episodes prune、截断方向等（见 `CHANGELOG.md`）
- headless：`./apps/desktop/scripts/headless_demo.sh` · Electron：`cd apps/desktop && npm run dev`

**仍外部 / 按需**

- Developer ID **真实**公证与 Gatekeeper 双击安装
- 客户环境 EDR 白名单实机勾选
- M6 connected（有企业客户再启）
- M0b `ui-shared` 抽取（未排期）
- M2 判据 12：本机 `codesign:dev` + 一次 FDA 授权  
**仍待外部条件**：Developer ID 真实公证与 Gatekeeper 双击装、EDR 实机勾选、M6 connected（按需）。  
**无证书可跑**：`cd apps/desktop && npm run pack:check`。

## 文档权威性

`docs/desktop/` 是**架构决策、里程碑、不变量**的权威来源。

`../superpowers/specs/2026-07-27-desktop-node-design.md` 是**详细规格**（协议字段、界面规格、平台细节），写于早期，部分条目已被本目录取代——该文件顶部有说明。**冲突时以本目录为准。**
