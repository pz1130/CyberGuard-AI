# 桌面端完整前端设计（Workbench · Settings · Evidence）

状态：设计 · 2026-08-04 · 方案 A（现有 renderer 演进）  
前置：M0a–M5 产品路径 + M7 交付骨架已合 `main`；黄金路径工程闭环已验  
关联：`docs/desktop/01-ARCHITECTURE.md` · `03-ROADMAP.md` · `04-INVARIANTS.md` · `11-OPEN-QUESTIONS.md` §A/C

---

## 1. 目标与非目标

### 1.1 目标

做一版**完整、可日常使用**的 macOS 桌面 App 前端（Electron renderer），同时满足：

1. **单兵工作台**：会话驱动的调查主路径（执行→观察循环），不是 Web 21 Tab 运营后台。  
2. **macOS 级体验**：导航清晰、双主题（**默认深色**）、动效连续、信息层级可读。  
3. **丝滑酷炫**：暗色 HUD 气质 + 玻璃面板 + 克制光感；动效跟手，不靠花活藏安全状态。  
4. **配置完整 GUI**：LLM / MCP 在设置页完成；API key 与 MCP secret 进 Keychain；可测连通。  
5. **证据独立页**：证据库全宽浏览/校验，不只是状态栏数字。

### 1.2 非目标（第一版明确不做）

| 不做 | 原因 |
|------|------|
| 复制 Web 的 Agents / Governance / Users 等 21 Tab | 与 DEC-027 单兵定位冲突；成本等同第二套后台 |
| `packages/ui-shared` 全量抽取（M0b） | 开放问题 H：成本接近重构大页；本设计不依赖它 |
| M6 connected UI（服务端审批队列、策略同步） | 按需，非本期 |
| Developer ID 公证与 Gatekeeper 产品页 | M7 证书依赖 |
| Tailwind / 新 UI 框架 | 用 CSS tokens + 原生 CSS 控制动效与体积 |
| Windows / Linux 适配 | 二期 |
| 多 agent 对辩作为默认主路径 | 开放问题 G 未收敛；UI 预留「可选」入口位即可，第一版不实现 |

### 1.3 成功标准（可验收）

1. 冷启动后 3s 内进入 Workbench；主题切换无闪白。  
2. **不打开 Finder 手改 JSON**，即可配置 live LLM + 至少一个 MCP，并完成一次告警分诊 Markdown 报告。  
3. Evidence 页可 list / verify，展示 sha256 与只读状态。  
4. Plan 自批准、run 暂停恢复、加密导出与卸载在 UI 内闭环。  
5. 状态栏常显：sidecar、sandbox、tcc、llm、tier、run、evidence 计数。  
6. 开发版横幅与 `approval_type: self` 标识符合 INV-38。

---

## 2. 气质与视觉系统

### 2.1 定位一句话

**暗色作战 HUD × macOS 原生壳**：专业安全工具的信息密度 + 苹果系的壳层克制。

### 2.2 主题

| 模式 | 行为 |
|------|------|
| `dark` | **默认**。近黑底 `#0a0c10`，表面层半透明/轻微 blur，电青强调 `#3ee0c5`，风险琥珀/红 |
| `light` | 同一布局与组件；token 换肤，表面为浅灰白，强调色略降饱和 |
| `system` | 跟随 `prefers-color-scheme`；用户选择写入本地偏好 |

实现：`document.documentElement.dataset.theme = "dark" | "light"`，CSS 变量分主题块。

### 2.3 Design tokens（最小集）

```
--bg / --bg-elevated / --surface / --surface-hover
--border / --border-subtle
--text / --text-muted / --text-inverse
--accent / --accent-muted
--ok / --warn / --danger
--radius-sm|md|lg
--shadow-panel
--motion-fast 160ms / --motion-base 240ms / --ease-out
--font-ui / --font-mono
```

### 2.4 动效（丝滑标准）

| 场景 | 规范 |
|------|------|
| 视图切换（Workbench↔Evidence↔Settings） | opacity + translateY(8–12px)，`motion-base`，`ease-out` |
| 列表/卡片 hover | 1–2px 抬升或 border 提亮，**禁止**大幅缩放 |
| 流式 token | 追加到消息尾部；自动滚底可选、用户上滚则暂停跟滚 |
| 状态 pill 变更 | 颜色 160ms 过渡 |
| 禁止 | 满屏粒子、循环炫光、超过 400ms 的入场动画 |

### 2.5 风险与安全色（不可「炫」掉）

| 状态 | 色 | 展示位置 |
|------|-----|----------|
| seatbelt + online | ok 绿 | 状态栏 |
| sandbox `none` | danger 红 + 文案 | 状态栏 + 横幅 |
| TCC restricted | warn 琥珀 | 状态栏 + 横幅 |
| 自批准 Plan | warn + 「自批准」标签 | Plan 面板（INV-06/38） |
| run 已暂停 | warn/红 | 状态栏 + 主区横条 |
| source_trust=hostile | 工具结果卡标注 | 时间线（INV-39） |

### 2.6 字体与 Markdown

- UI：系统栈 `-apple-system, BlinkMacSystemFont, "SF Pro Text", …`  
- 日志 / 工具输出 / hash：`ui-monospace, SF Mono, Menlo`  
- Markdown 报告：标题层级、列表、代码块、引用块；工具输出与最终报告分区卡片化（升级现有 `SimpleMarkdown`）

---

## 3. 信息架构

### 3.1 壳布局

```
┌─ Chrome（拖拽区 + 导航）──────────────────────────────────┐
│  Logo  [ Workbench ] [ Evidence ]     [⚙ Settings] [主题] │
├─ StatusBar（常驻）────────────────────────────────────────┤
│  sidecar · sandbox · tcc · llm · tier · run · evidence   │
├─ Main（唯一活动视图）─────────────────────────────────────┤
│  WorkbenchView | EvidenceView | SettingsView              │
└───────────────────────────────────────────────────────────┘
```

- 导航：视图状态枚举 `activeView: "workbench" | "evidence" | "settings"`（**不强制** react-router；URL hash 可选增强，非必须）。  
- 开发版横幅：Settings/About 与壳顶保留 INV-38 文案（development / 非公证 / 自批准 ≠ 职责分离）。  
- 托盘：显示窗口、打开 Data 面板（导出/卸载）— 与现有 main 进程一致。

### 3.2 Workbench（三栏）

| 栏 | 职责 |
|----|------|
| **左 · Sessions** | 会话列表、新建（⌘N）、搜索过滤、当前选中、删除（crypto-shred 确认） |
| **中 · Stream** | 用户任务 + 事件时间线（tool_call / answer / plan / pause）+ 输入框 + Run/Abort/Steer + 档位 readonly\|full |
| **右 · Context** | 可折叠分段：Pending Plan、本轮工具、技能 catalog 提示、本轮证据摘要、auth bounds 只读 |

空状态（无会话或新安装）：三步引导卡片 — **配置 LLM → 添加 MCP → 跑一条分诊任务**（链到 Settings 对应段）。

### 3.3 Evidence（独立全页）

| 区域 | 能力 |
|------|------|
| 工具条 | 注册文件（系统文件选择器经 main）、刷新、按会话/时间过滤（若索引支持则做，否则 list 全量） |
| 表格/卡片列表 | path、note、sha256 短显、mount=read-only、registered_at |
| 详情 | 完整 hash、verify 结果、打开所在目录（只读意图；不提供「用 agent 改写」入口） |

与 Workbench 联动：时间线里 `evidence_register` 事件可「在证据库中查看」。

### 3.4 Settings（分组）

| 分组 | 能力（第一版必须） |
|------|-------------------|
| **LLM Provider** | mock/live；base_url；model；temperature（可选）；API key 写入 Keychain（输入框不回显已存密钥，仅「已配置 / 未配置」）；**测试连通**；显示 public status（mode/model/base_url/has_api_key） |
| **MCP Servers** | CRUD 列表：id、command、args、readonly、enabled、description、secret_env；secret 经 Keychain slot；Discover tools 展示 `mcp__id__tool` |
| **Skills** | 只读 catalog（builtin name+description+version）；说明 progressive `load_skill` |
| **Data & Security** | data_root 路径；FileVault 状态；session 加密开关说明；加密导出；卸载 inventory / dry-run / execute；保留期说明（90 天默认） |
| **Appearance** | theme dark/light/system；字号 sm/md/lg（可选） |
| **About** | app 版本、desktop 标记、开发版声明、文档链接路径 |

配置持久化：

- 偏好（主题等）：`data_root/ui_prefs.json` 或 sidecar 统一 prefs RPC。  
- Provider：Keychain 存 key；非密钥字段可 `provider.json`（key 字段清空，与现有 migrate 一致）。  
- MCP：`mcp_servers.json` **不含**明文 secret；secret 仅 Keychain。

---

## 4. 进程边界与 IPC

### 4.1 不变约束

- Renderer **无** Node；仅 `window.cyberguard` preload API。  
- Sidecar **无** 监听端口；JSONL stdio。  
- 凭据永不进渲染日志、永不进会话 JSONL 明文（INV / 现有 secrets 设计）。

### 4.2 现有 API（继续用）

`ping`、`capabilities`、`run` / `abort` / `steer`、`sessions.*`、`plan.*`、`evidence.*`、`exportEncrypted`、`uninstall*`、`onEvent`、`onOpenDataPanel`、skills 相关若已有则复用。

### 4.3 新增 / 补齐 RPC（实现计划中逐条落地）

| 方法 | 用途 |
|------|------|
| `provider.get` | 返回 `public_status` + 非密钥配置字段（无 api_key） |
| `provider.set` | 写 base_url/model/mode；可选 `api_key` 时转 `secrets.set_provider_key` |
| `provider.test` | 最小 chat/completions 探活；返回 ok/error（不落密钥） |
| `mcp.config.list` | 读配置列表（无 secret 明文） |
| `mcp.config.upsert` / `mcp.config.delete` | 写 `mcp_servers.json` |
| `mcp.discover` | 已有则复用 |
| `secrets.set_mcp` / 查询 has_secret | 已有则复用 |
| `ui.prefs.get` / `ui.prefs.set` | 主题、字号等 |
| `evidence.list` / `register` / `verify` | 已有则复用；register 可由 main 弹文件框后传 path |

Main 进程补充：

- `dialog.showOpenDialog` 用于证据注册、可选 MCP 脚本路径选择。  
- 主题变更不需要 main，纯 renderer + 可选 nativeTheme 同步。

---

## 5. 目录结构（renderer）

```
apps/desktop/renderer/
  main.tsx
  App.tsx                      # Shell: nav, status bar, theme, banners, view switch
  index.html
  styles/
    tokens.css                 # dark/light variables
    base.css
    motion.css
    views.css                  # layout for three views
  components/
    StatusBar.tsx
    StatusPill.tsx
    Button.tsx
    Panel.tsx
    Markdown.tsx
    EmptyState.tsx
    EventCard.tsx              # from current EventCard
    PlanPanel.tsx
    SessionList.tsx
    …
  views/
    WorkbenchView.tsx
    EvidenceView.tsx
    SettingsView.tsx
  hooks/
    useSidecar.ts
    useTheme.ts
    useSessions.ts
  lib/
    ipc.ts                     # typed wrappers around window.cyberguard
    types.ts
```

原则：单文件职责清晰；`App.tsx` 不再超过 ~300 行壳逻辑；样式以 tokens 为唯一颜色来源。

---

## 6. 交互细节（关键路径）

### 6.1 跑一次任务

1. 选/建会话与档位 → 输入任务 → Run。  
2. 中栏追加 `user_task` / `run_started` / tool cards / `answer_ready`。  
3. 高危触发 Plan → 顶部或中栏 PlanPanel：「自批准并执行 / 拒绝」；超时=拒绝。  
4. Provider 网络失败 → 状态「已暂停」+ Resume。  
5. Abort / Steer 仅在 running 时可用。

### 6.2 配置 LLM

1. Settings → LLM → 填 base_url/model → 粘贴 key（一次）→ Save（key 进 Keychain）。  
2. Test → 成功/失败 toast 或行内状态。  
3. Workbench 状态栏 `llm:` 立即反映 public status。

### 6.3 配置 MCP

1. Add server → 表单 → 可选 Browse 选 command 路径 → Save。  
2. 可选 Set secret → Discover → 工具名列表。  
3. readonly 开关影响档位可见性（与现 sidecar 语义一致）。

### 6.4 快捷键（第一版）

| 键 | 动作 |
|----|------|
| ⌘N | 新会话 |
| ⌘, | 打开 Settings |
| ⌘1 | Workbench |
| ⌘2 | Evidence |
| ⌘Enter | 发送/Run（输入框聚焦时） |
| Esc | 关闭模态 / 取消焦点 |

---

## 7. 交付波次

| 波次 | 范围 | 出口 |
|------|------|------|
| **P0 壳 + 视觉** | tokens 双主题；Shell 导航；StatusBar；现有工作台迁入 WorkbenchView；EventCard/Markdown 视觉升级；动效基线 | 深色默认观感达标；功能不回退 |
| **P1 设置 GUI** | LLM + MCP 完整 GUI；provider/mcp RPC；Keychain；连通测试；空状态引导链到设置 | 无手改 JSON 完成黄金路径配置 |
| **P2 证据页** | Evidence 全页；register/verify UI；与时间线联动 | 独立证据库可用 |
| **P3 抛光** | 快捷键；字号；浅色主题验收；空状态文案；细节动效；无障碍焦点环 | 成功标准 §1.3 全勾 |

每波次可独立合并；P0 不得破坏 headless/sidecar 契约。

---

## 8. 测试策略

| 层 | 内容 |
|----|------|
| 单元/契约 | 新增 provider/mcp config RPC 的 pytest（无密钥落盘、list 无明文 secret） |
| 渲染 | 可选：对纯函数（Markdown 解析、theme resolve）轻测；Electron 全 UI 不强制 e2e |
| 手工验收 | P0–P3 检查清单：主题切换、配置 LLM+MCP、分诊跑通、证据 verify、导出/卸载、Plan 自批准 |
| 回归 | 现有 `tests/test_desktop_*` 全绿；`npm run codesign:verify` 开发签名仍有效 |

---

## 9. 风险与不变量

| 风险 | 缓解 |
|------|------|
| 设置页把 key 写进 renderer 日志 | 禁止 log key；仅 has_api_key |
| MCP command 任意路径 | 保持 sidecar 校验；UI 提示绝对路径 |
| 炫技动效掩盖 sandbox none | StatusBar + 横幅强制 danger |
| 范围膨胀成 Web 克隆 | §1.2 非目标；评审拒绝新 Tab 类需求进第一版 |
| INV-38 文案弱化 | 开发版横幅与自批准标签为验收项 |

相关不变量：INV-06/38（自批准）、INV-14（Trust Gate，设置不绕过）、INV-37（standalone 自洽）、INV-39（hostile 标记可见）。

---

## 10. 与现有代码关系

| 现状 | 本设计 |
|------|--------|
| 单文件 `App.tsx` ~1100 行 | 拆为 shell + views + components |
| `styles.css` 单文件 | `styles/tokens|base|motion|views` |
| provider.json 手改 | Settings GUI + Keychain |
| evidence 仅 count + RPC | 独立 Evidence 页 |
| 功能 RPC 已齐大半 | 补 provider/mcp config/prefs 薄层 |

Sidecar 业务语义（Plan、Seatbelt、episodic、skills progressive）**不重写**，只加配置面与 UI 编排。

---

## 11. 开放点（实现中冻结，不阻塞开工）

| 点 | 默认决定 |
|----|----------|
| 是否使用 hash 路由 | 默认否；仅内存 `activeView` |
| 字号档位 | P3：sm/md/lg 三档映射 root font-size |
| MCP args 编辑 UX | 多行文本按行拆 args，或 JSON 数组；实现选一种写死 |
| 浅色主题精确色板 | P0 先可切换；P3 对照验收调色 |

---

## 12. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-04 | 初稿：方案 A + 双主题默认深色 + Workbench/Settings/Evidence + 完整配置 GUI + 丝滑酷炫视觉约束；用户确认后落盘 |
