# 桌面端前端 UI 重构设计（结构 + 视觉）

状态：设计 · 2026-08-13 · 路线 B（主屏先行，反向萃取）
前置：`feature/desktop-app-frontend` 已合 `main`（6b9d629）；M0a–M5 + M7 工程已落地
关联：`docs/desktop/04-INVARIANTS.md` · `05-DECISIONS.md` · `13-M2-EXIT-CHECKLIST.md`
取代：`2026-08-04-desktop-app-frontend-design.md` 的 §2 视觉系统与状态栏排布部分（其余仍有效）

---

## 0. 这次改什么，为什么

上一版前端（2026-08-04 设计，8 月 4 日落地）把功能补齐了：三栏骨架、双主题、设置 GUI、证据页、流式输出、技能管理都能用。**功能没问题，观感是毛胚。**

具体诊断见 §2。一句话概括：**token 层质量不错，但没有字阶、没有层级阶、颜色语义重载、组件边界缺失，所以"能用"和"像个产品"之间隔着一整层。**

### 0.1 非目标

| 不做 | 原因 |
|---|---|
| 换配色方案 | 深色 + teal 成立，问题不在色板（见 §2 诊断 1） |
| 引入 Tailwind | 与既有 CSS token 体系重复，迁移成本换不到设计收益 |
| 引入完整 UI 组件库（MUI / Ant / shadcn） | 与 DEC 的"不引入新 UI 框架"冲突；只引无头原语（§9） |
| `packages/ui-shared` 抽取（M0b） | 未排期，本设计不依赖它 |
| ⌘K 命令面板 | 三个视图撑不起命令面板，YAGNI |
| 全局 toast | 见 §7.5，对安全工具是错的默认 |
| 快照测试 | 重构期是负资产，每次改样式都要重录 |
| 服务端 WebUI 的任何改动 | 服务端处于冻结期 |

---

## 1. 现状诊断

单跑渲染层（`npm run dev:renderer`，无 Electron / sidecar）截图观察，1440×900：

1. **配色不是问题。** token 层的深浅双主题、语义色（ok/warn/danger/plan）、圆角与动效变量质量都不错。**"毛胚"感不来自色板** —— 这个结论省掉了最大一笔潜在返工。
2. **顶部堆了四条横带**（nav → mock 告警条 → StatusBar 胶囊行 → 栏头），吃掉约 150px，且信息重复：`LLM mock` 出现 2 次，`只读` 出现 3 次（StatusBar / 右栏档位 / composer 下拉）。
3. **三栏没有视觉层级差**。左中右背景近乎同色，只靠 1px 边框分隔，看不出谁是主角 —— 这是"信息架构混乱"的直接来源。
4. **大片死区**。中间栏下半约 250px 全空；左栏 240px 只放了一句"还没有会话"。
5. **原生控件穿帮**。composer 的档位选择器是 macOS 原生 `<select>`，与整体质感完全脱节 —— 单点最刺眼。
6. **按钮无权重区分**。右栏「查看证据 / 数据源 / 语言模型」三个全宽按钮外观完全相同，但它们分属事实与配置两类。
7. **字阶几乎不存在**。除一个标题外全是 13–14px，靠颜色深浅撑层次，撑不住。
8. **右栏是杂物间**。演示就绪卡 + 工具 chips + 三个跳转按钮 + 调试折叠 + 数据面板，五种不同性质的东西堆在一列。

### 1.1 代码层症状

| 症状 | 数据 |
|---|---|
| `useDesktopRuntime` god hook | 529 行，33 个 `useState` |
| `WorkbenchView` props 爆炸 | 45 个 props 手传 |
| `SettingsView` 过大 | 1478 行 |
| `EventCard` 类型分支堆叠 | 391 行处理全部事件类型 |
| CSS 平铺无归属 | `styles.css` 1455 行 + `views.css` 746 行，职责重叠 |

---

## 2. 路线：B（主屏先行，反向萃取）

先把调查页（Workbench）按目标观感一次做到位，过程中沉淀的组件抽成 primitives，再套用到证据页与设置页。

**已知代价**：抽象容易偏向 Workbench，1478 行的 Settings 有返工风险。
**对冲措施**：Workbench 每抽出一个组件，评估"Settings 的表单用得上吗"，能低成本泛化的当场泛化，泛化不了的不硬套（§6.4 复用度列已标注）。

**过渡期双模式共存是预期内的**：`RuntimeProvider` 这轮只落 Workbench 用到的域，Settings 与 Evidence 暂时保持现有 props 传递，轮到它们时再迁。这是路线 B 的必然形态，不是失误。

### 2.1 本轮范围

**在本轮内：**

- §4 设计系统全部（token 收紧，全局生效）
- §5 primitives 全部十个
- §6 状态层拆分中 Workbench 消费的五个域（`useSessions` / `useRun` / `useStream` / `usePlan` / `useEnvironment`）
- §6.1 导出/卸载迁出 Workbench —— **在 Settings 侧只做"接住"，不重做 Settings 的观感**
- Workbench 三栏完整重做（§3）
- §7 交互与动效、§8 测试

**不在本轮内：**

- `SettingsView`（1478 行）的视觉与结构重做
- `EvidenceView` 的视觉与结构重做
- `useDataLifecycle` 之外的 Settings 状态层迁移

> token 层是全局的，收紧后 Settings 与 Evidence 会**被动继承新的字阶与色彩语义**。这会让它们在本轮结束时处于"配色一致但排布仍是旧的"的中间态 —— 预期内，下一轮处理。

---

## 3. 布局与信息架构

### 3.1 目标形态

```
┌──────────────────────────────────────────────────────────────────┐
│  CyberGuard   调查  证据  设置                        Dark   DEV  │ 48px
├──────────────────────────────────────────────────────────────────┤
│ ⚠ FileVault 未开启 · 证据加密不可用                         关闭 │ 仅异常
├───────────┬──────────────────────────────────┬───────────────────┤
│  会话      │  告警分诊                         │  本次调查          │
│   layer-0  │        layer-1（抬起）            │      layer-0      │
│           │                                  │                   │
│ ▸ 告警分诊 │  ┌ 计划 · 已批准 ────────────┐  │  发现              │
│   2 分钟前 │  │ 1 拉取告警           ✓    │  │  ┗ 3 条高危        │
│           │  │ 2 关联资产           ✓    │  │                   │
│   日志回溯 │  │ 3 丰富情报        ● 运行中 │  │  证据              │
│   昨天     │  └──────────────────────────┘  │  ┗ 4 件 · 已验证    │
│           │                                  │                   │
│   样本分析 │  ▸ list_alerts           0.4s   │  工具              │
│   3 天前   │    → 12 条 · 3 high             │  ┗ list_alerts     │
│           │                                  │    get_alert       │
│           │  ┌────────────────────────────┐  │                   │
│  + 新建    │  │ 描述任务…            ⌘↵   │  │ ───────────────── │
│           │  └────────────────────────────┘  │ ●在线 ●沙箱 ●权限  │
│           │                                  │ live · 只读     ▸ │ 状态栏
└───────────┴──────────────────────────────────┴───────────────────┘
```

### 3.2 关键决策

- **右栏一分为二。** 上半滚动区只放**本次调查产生的事实**（发现 / 证据 / 工具）；下半贴底固定**状态栏**。分界线是"这轮跑出来的" vs "机器本来就这样"。这解决 §1 诊断 8。
- **顶部从四条压到一条**（48px）。nav 右侧不再挂状态胶囊，常规状态全部下放右栏状态栏。异常条独立浮出，平时零高度。
- **中间栏 `--layer-1` 抬起，左右栏 `--layer-0` 沉下**，栏间不用边框、靠色阶分割（省像素且更干净）。
- **左栏取消"还没有会话"空文案**，改为直接可点的示例任务入口。
- **拆掉三个同权重全宽按钮**：证据是事实 → 挂到右栏「证据」区标题；数据源与语言模型是配置 → 归进状态栏展开面板。
- **导出 / 卸载整块移出 Workbench**（详见 §6.1）。

### 3.3 状态栏规格（合规关键，见 §10）

右栏贴底一行，**常显、不可折叠**：

| 项 | 显示 |
|---|---|
| 连接态 | `●在线` / `●离线`（sidecar ping） |
| sandbox | `●沙箱` + impl，`none` 时转 danger |
| tcc | `●权限`，restricted 时转 warn |
| 模型 | `live` / `mock` |
| 档位 | `只读` / `完整` |
| 暂停态 | 存在时追加 `⏸ 已暂停`（INV-36 要求常显） |

点击 `▸` 展开：caps 明细、`data_root`、sandbox 模式、TCC 指引、版本。**展开面板只放详情，上述六项永不折叠。**

---

## 4. 设计系统

### 4.1 字阶

| token | 值 | 用途 |
|---|---|---|
| `--text-2xs` | 11px | 时间戳、单位、辅助元数据 |
| `--text-xs` | 12px | 标签、pill、栏头 |
| `--text-sm` | 13px | 次要正文、元信息 |
| `--text-base` | 14px | 正文默认 |
| `--text-md` | 16px | 卡片标题、会话名 |
| `--text-lg` | 20px | 视图标题 |
| `--text-xl` | 26px | 空态主标题（全局唯一大字） |

行高三档：`--leading-tight: 1.3`（标题）/ `--leading-normal: 1.5`（UI）/ `--leading-relaxed: 1.65`（正文与 Markdown 报告）。

字重只用 400 / 500 / 600。**禁用 700** —— 深色底上 700 会发糊。

### 4.2 间距阶（4px 基）

`--sp-1:4` `--sp-2:8` `--sp-3:12` `--sp-4:16` `--sp-5:20` `--sp-6:24` `--sp-8:32` `--sp-10:40`

**"舒适"的具体落法**（局部舒适、全局不浪费）：

| 位置 | 值 |
|---|---|
| 卡片内边距 | `sp-4` ~ `sp-5` |
| 卡片间距 | `sp-3` |
| 栏内边距 | `sp-4` |
| 模块间距 | `sp-6` |
| 栏间距 | 0（靠色阶分割） |

> 纯粹放大所有间距会让"太空"更空。舒适放在卡片内部，栏级保持紧凑。

### 4.3 层级阶

现有 `--surface` / `--surface-solid` / `--bg-elevated` 三者混用且无使用规则。替换为四级：

| 级 | 用途 |
|---|---|
| `--layer-0` | 沉底 —— 左右栏背景 |
| `--layer-1` | 基准 —— 中间栏背景 |
| `--layer-2` | 卡片 —— 事件卡、计划卡、会话项 |
| `--layer-3` | 浮层 —— 下拉、弹窗、tooltip |

每级配套 border 与 shadow token。

**硬规则：相邻嵌套必须差一级，同级不套同级。** 这条可机械检查，不靠自觉。

### 4.4 色彩职责拆分

现状：teal 一色同时表示品牌标识、nav 选中、primary 按钮、运行中状态、强边框 —— **五种语义共用一色等于没有语义**，这是"看不出层次"的真正原因。

拆分后：

- `--accent`（teal）→ **只**表示「主操作」与「当前选中」，不再表示任何状态
- `--ok` 完成 / `--warn` 需注意 / `--danger` 失败或降级 / `--info` 进行中 / `--plan` 计划态
- 「运行中」从 teal 改为 `--info` + 脉冲，与「选中」彻底分离

### 4.5 文件组织

```
renderer/
  styles/tokens.css     收紧：补字阶 / 间距阶 / 层级阶
  styles/base.css       保持
  styles/motion.css     扩充（§7.2）
  ui/                   【新】primitives，一组件一 .tsx + 同名 .css
  components/           业务组件 —— 只做「ui/ 原语 + 业务数据」的组合
  views/
```

`styles.css`(1455 行) 与 `views.css`(746 行) 随组件迁移逐步清空，最终删除。

**硬规则：新代码一行都不许往这两个文件加。** 否则会长回来。

---

## 5. Primitives 清单

| 组件 | Workbench 用途 | Settings 复用度 | 实现 |
|---|---|---|---|
| `Button` primary/secondary/ghost/danger × sm/md | 运行、中止、新建 | 高 | 手写 |
| `Select` | 档位 | 高 | **Radix** |
| `Field` label+input+hint+error | composer 辅助输入 | **很高** | 手写 |
| `Panel` 栏容器 + 栏头 | 三栏骨架 | 中 | 手写 |
| `Card` | 事件卡、计划卡 | 中 | 手写 |
| `Disclosure` | 工具展开、状态栏展开 | 高 | 手写（`<details>` 语义） |
| `StatusDot` | 在线态、运行态 | 中 | 手写 |
| `Tooltip` | 截断文本、图标按钮 | 高 | **Radix** |
| `ListRow` | 会话项、证据项 | 中 | 手写 |
| `Timestamp` | 事件时间 | 低 | 手写 |

---

## 6. 组件边界与状态层

### 6.1 白捡的收益：13 个 props 直接消失

`WorkbenchView` 现有 45 个 props 中，以下 13 个**不应存在于调查页**：

`exportPass` `exportBusy` `exportMsg` `onExport` `exportAvailable` `uninstallBusy` `uninstallPreview` `onUninstallInventory` `onUninstallDryRun` `onUninstallExecute` `showDataPanel` `onToggleDataPanel` `dataRoot`

加密导出与卸载是**数据生命周期管理**，不是调查行为。它们当前同时传给 Workbench 与 Settings 两份，而 Workbench 内的 `DataPanel` 正是右栏杂物间的组成部分。

**整块移入设置页，Workbench 不再感知其存在。** 零业务逻辑改动。

### 6.2 状态层拆成六个域

```
renderer/state/
  RuntimeProvider.tsx     组合各域，挂在 App 外层
  useSessions.ts          sessions / sessionId / 选择 / 新建 / 删除
  useRun.ts               running / runId / runStatus / tier / task / 跑停继续
  useStream.ts            streamText / streaming
  usePlan.ts              pendingPlan / 批准 / 拒绝
  useEnvironment.ts       ping / caps / provider / sandbox / TCC / FileVault / mcpTools
  useDataLifecycle.ts     导出 / 卸载 —— 只被 Settings 消费
```

**`useStream` 必须单独拆。** 流式输出每 token 更新一次；若与 `running` / `tier` 同处一个 context，每个 token 都会触发全部消费者重渲染，三栏跟着抖。拆开后高频更新隔离在流式卡片内部。

> 这是纯 Context 方案唯一的真陷阱。拆细即可解决，不需要引入状态库。

**`usePlan` 单独成域的理由**：计划审批是 INV-06 / INV-38 的落点，`approval_type: self` 的标注逻辑必须收在一处，不能散进 `useRun`。

拆完后 `WorkbenchView` 的 props：**45 → 0**。

### 6.3 组件边界

```
views/WorkbenchView.tsx           只剩三栏骨架，约 40 行
components/
  session/SessionRail.tsx         左栏（含空态示例入口）
  investigation/
    InvestigationHeader.tsx
    Timeline.tsx
    events/ToolEvent.tsx  PlanEvent.tsx  MessageEvent.tsx  StreamEvent.tsx
    Composer.tsx
  context/
    ContextRail.tsx               右栏容器
    FindingsSection.tsx
    EvidenceSection.tsx
    ToolsSection.tsx
    StatusBar.tsx                 贴底状态栏 + 展开面板（§3.3）
```

**`EventCard` 拆成四类是"内容太干"的正解。** 当前所有事件都渲染为同一种灰卡片，工具调用、计划、报告外观完全相同。拆开后每类才能有自己的表现力：工具调用出参数与结果摘要、计划出进度、报告出排版。

---

## 7. 交互、动效与错误呈现

### 7.1 运行生命周期的可见性

现状：点「运行」后除按钮文字变化外几乎无反馈，首包前只有一行"等待首包…"。

| 时刻 | 反馈 |
|---|---|
| 提交瞬间 | 输入**立刻**以消息卡落入时间线，composer 清空（乐观渲染，不等后端） |
| 首包之前 | 时间线底部三条脉冲骨架 |
| 工具调用中 | 实时计时器走秒，完成后定格 + 结果摘要（`→ 12 条 · 3 high`） |
| 计划执行中 | 步骤逐条点亮，当前步骤脉冲 |
| 全程 | 中间栏顶部 2px 不确定态进度条 |

### 7.2 动效原则

只做三类：

- **进入** —— 新事件 fade + 上移 8px，180ms
- **状态变化** —— 颜色 / 尺寸过渡，150ms
- **持续态** —— 脉冲，2s 循环

**明确不做**：视图切换滑动、卡片 hover 位移、任何装饰性动画。

全部尊重 `prefers-reduced-motion`（关闭进入与脉冲，保留状态过渡）。

时长收为两档，`--motion-base` 由 240ms 改为 **180ms**（240ms 用于 UI 反馈偏拖沓）。

### 7.3 错误与降级呈现

- 工具失败使用结构化失败卡：工具名 + 错误类型 + 是否可重试。不用一行红字。
- **安全降级使用专属视觉**（danger 色 + 锁形标记），与普通运行错误在视觉上区分。
  > INV-38 要求"降级不得伪装成正常"，与普通错误混用同一种红色即构成伪装。
- sidecar 断连：状态栏转红 + 顶部浮出 + 运行按钮禁用**并写明原因**。不做静默失败（P5 / INV-25）。

### 7.4 键盘

保留 ⌘1 / ⌘2 / ⌘N / ⌘, / ⌘↵；补 Esc 收浮层、↑↓ 在会话列表移动。

### 7.5 操作确认：不做全局 toast

删除会话、导出成功等需要确认。**不引 toast 库、不自建全局 toast**，改为就地反馈：

- 删除会话 → 行内撤销条（5 秒）
- 导出结果 → 按钮旁结果行

> 理由：全局 toast 会飘走，错过即消失。对一个需向第三方举证的安全工具，"操作结果只存在 3 秒"是错误的默认。就地反馈可追溯。

---

## 8. 测试策略

引入 vitest + React Testing Library，**只测关键路径，不追求覆盖率**。

```
renderer/__tests__/
  state/useRun.test.ts          状态机 idle→running→paused→resumed→done/aborted
  state/useSessions.test.ts     选择/新建/删除后 sessionId 的收敛
  state/useEnvironment.test.ts  降级标志派生（fv/tcc/mock → 告警条该不该出）
  ui/Button.test.tsx            variant × size 类名与 disabled 语义
  ui/Select.test.tsx            键盘导航与 ARIA（验证 Radix 接线正确）
```

新增 `npm test`；将既有 `npm run typecheck` 一并接入流程。

**不做快照测试。**

> 拆 33 个 `useState` 是本次重构最容易出错的地方，状态层三个测试文件是主要的安全网。

---

## 9. 新依赖清单

| 包 | 用途 | 不手写的理由 |
|---|---|---|
| `@radix-ui/react-select` | 档位选择器 | 替换原生 `<select>`（§1 诊断 5）；焦点陷阱 + 键盘导航 + ARIA 手写易错 |
| `@radix-ui/react-tooltip` | 截断文本、图标按钮 | 定位计算 + ARIA 关联手写易错 |
| `vitest` | 测试运行器 | 与 Vite 共享配置 |
| `@testing-library/react` | 组件测试 | — |
| `jsdom` | 测试环境 | — |

共 5 个。`@radix-ui/react-dialog` 等在 Settings 阶段确有需要时再加，**不预支**。

> Radix 是无头原语库（只提供行为与可访问性，不带样式），不构成"新 UI 框架"，与既有约束不冲突。

---

## 10. 不变量与决策对照

本设计调整了状态栏的位置，以下为合规映射：

| 来源 | 要求 | 本设计如何满足 |
|---|---|---|
| **🔒 DEC-010** | 布局含「会话树 / 对话执行流 / 上下文面板 + 状态栏」 | 四者齐备。状态栏由顶部横带改为右栏贴底常显行 —— DEC-010 规定布局包含状态栏，未规定其必须横跨顶部。**不构成推翻。** |
| **INV-16** | `sandbox_impl: none` 时状态栏须显著告警 | 状态栏 sandbox 项转 danger，**且**从顶部浮出告警条（§3.2） |
| **INV-25 / P5** | 安全边界失败不得静默降级 | §7.3：断连禁用运行并写明原因；降级专属视觉 |
| **INV-36** | 状态栏须常显待上报数量与暂停状态 | §3.3：暂停态常显。待上报数量属 connected（M6），届时在同一行追加 |
| **INV-38** | 安全降级必须显式标注，不得伪装 | §7.3：降级与普通错误视觉区分；`approval_type: self` 标注逻辑收在 `usePlan`（§6.2） |
| **M2 判据 10** | 状态栏展示 sandbox / tcc / llm / tier | §3.3 六项常显，四项全含。**位置变更需在 `13-M2-EXIT-CHECKLIST.md` 判据 10 补一条位置注记**，判定结果不变。 |

**本设计不推翻任何 🔒 / ⚖️ 决策。**

---

## 11. 出口判据

1. `WorkbenchView` props 数 = 0；`useDesktopRuntime` 拆解完成，无单个 hook 超过 150 行
2. 顶部常驻高度 ≤ 48px；无异常时不出现第二条横带
3. 状态栏六项常显且不可折叠（§3.3），`sandbox_impl=none` 注入用例下转 danger 且顶部浮出
4. `styles.css` 与 `views.css` 中 **Workbench 相关**规则清零（Settings / Evidence 的规则本轮保留，见 §2.1）
5. composer 无任何原生 `<select>` / 未加样式控件
6. `npm test` 与 `npm run typecheck` 全绿
7. `prefers-reduced-motion: reduce` 下进入动效与脉冲全部关闭
8. 现有 138 个 Python 桌面测试保持全绿（本次不触碰 sidecar）
9. 深浅双主题下 **Workbench**（§3.1）布局均无破版；Settings / Evidence 在新 token 下**不破版**即可，不要求达到新观感

---

## 12. 风险与已知取舍

| 风险 | 缓解 |
|---|---|
| 路线 B 的抽象偏向 Workbench，Settings 返工 | §2 对冲措施；§5 已标注复用度 |
| 过渡期 Context 与 props 双模式共存造成混乱 | 预期内；`RuntimeProvider` 只覆盖 Workbench 域，边界清晰 |
| Context 高频更新导致重渲染 | `useStream` 单独隔离（§6.2） |
| "舒适"密度加剧"太空"观感 | §4.2 局部舒适、全局紧凑；配合 §6.3 事件卡分类提升内容密度 |
| 状态栏移位被误读为削弱安全可见性 | §10 对照表；出口判据 3 有注入用例 |
