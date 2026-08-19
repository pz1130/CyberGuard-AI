# 桌面端 i18n 安全术语审阅表

状态：**待用户定稿** · 2026-08-19（Task 7）· 共 **43 条**，按性质分五组

判据 3 要求本表每一条经人确认后，把定稿写回 `docs/desktop/06-GLOSSARY.md`。
下表「建议英文」已落入 `en.json` 作为草案运行；**未打勾前判据 3 保持 open**。

**怎么用**：一次过一组，只在「建议英文」这列上花注意力 —— 中文与出处是给你定位用的。
改哪条就直接把新译法写进那一格并打勾；全组无异议就把整组的 ☐ 划掉。
先看 §「拿不准的六条」，那是我自己觉得该由你拍板的。

---

## A · 安全降级文案（11 条）

**这组最要紧。** INV-38 要求安全降级显式标注，翻软了等于降低告警强度。看点：英文是否与中文同样是「禁止 / 已禁用」而不是「建议 / 可能」。

| 中文 | 建议英文 | 出处 | 为什么这么译 | ☐ |
|---|---|---|---|---|
| 收起 | Dismiss | `degradation.dismiss` · apps/desktop/renderer/state/degradations.ts + zh.json | 收起浮出条；Dismiss | ☐ |
| 全盘加密未开启，本机数据在设备丢失时可被读取 | Full-disk encryption is off; local data may be readable if the device is lost | `degradation.filevault.detail` · apps/desktop/renderer/state/degradations.ts + zh.json | 静态回落；sidecar 原文走 detailText | ☐ |
| FileVault 未开启 | FileVault is off | `degradation.filevault.label` · apps/desktop/renderer/state/degradations.ts + zh.json | FileVault 品牌保留；is off 直白 | ☐ |
| 未配置真实模型，输出不可用于结论 | No real model configured; output must not be used as findings | `degradation.mock.detail` · apps/desktop/renderer/state/degradations.ts + zh.json | must not = 禁止，非 should not（INV-38） | ☐ |
| 模型为 mock | Model is mock | `degradation.mock.label` · apps/desktop/renderer/state/degradations.ts + zh.json | Model is mock——禁止伪装成可用结论源 | ☐ |
| 本地执行进程未连接，运行已禁用 | Local execution process not connected; runs are disabled | `degradation.offline.detail` · apps/desktop/renderer/state/degradations.ts + zh.json | 说明运行已禁用，非 soft warn | ☐ |
| sidecar 离线 | Sidecar offline | `degradation.offline.label` · apps/desktop/renderer/state/degradations.ts + zh.json | INV-38 安全降级条标题 | ☐ |
| 仅允许只读档位（INV-16） | Read-only tier enforced (INV-16) | `degradation.sandbox.detail` · apps/desktop/renderer/state/degradations.ts + zh.json | INV-16；Read-only tier enforced | ☐ |
| 沙箱不可用 | Sandbox unavailable | `degradation.sandbox.label` · apps/desktop/renderer/state/degradations.ts + zh.json | 不得缩成 No sandbox（削弱告警） | ☐ |
| 部分目录读取会失败 | Some directories will fail to read | `degradation.tcc.detail` · apps/desktop/renderer/state/degradations.ts + zh.json | 静态回落；tccGuidance 不翻 | ☐ |
| 磁盘访问受限 | Disk access restricted | `degradation.tcc.label` · apps/desktop/renderer/state/degradations.ts + zh.json | 磁盘访问受限；restricted 非 denied（可能部分可） | ☐ |

---

## B · 审批与计划（16 条）

看点：`approval_type: self` 这类机器标识**必须原样保留**（INV-06 不许把本地自批准与职责分离审批混同）；「超时=拒绝」不能译成 timeout warning。

| 中文 | 建议英文 | 出处 | 为什么这么译 | ☐ |
|---|---|---|---|---|
| 计划 | Plan | `event.plan` · apps/desktop/renderer/components/investigation/events/ | 与 en.json 草案一致；界面普通文案/设置项 | ☐ |
| 计划 · 已批准 | Plan · approved | `event.plan.approved` · apps/desktop/renderer/components/investigation/events/ | Plan · approved | ☐ |
| 计划 · 已拒绝 | Plan · rejected | `event.plan.rejected` · apps/desktop/renderer/components/investigation/events/ | Plan · rejected | ☐ |
| 提权申请 | Privilege request | `event.privilege` · apps/desktop/renderer/components/investigation/events/ | 提权申请事件卡 | ☐ |
| 批准 | Approve | `plan.approve` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | Approve | ☐ |
| 计划审阅 | Plan review | `plan.aria` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | Plan Mode 审阅区 | ☐ |
| 计划待批 | Plan awaiting approval | `plan.pending` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | 待批状态 | ☐ |
| {base} · 提权 | {base} · privilege | `plan.privilegeLabel` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | {base} · privilege；提权后缀 | ☐ |
| 拒绝 | Reject | `plan.reject` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | Reject | ☐ |
| approval_type: self · 本地自批准 | approval_type: self · local self-approve | `plan.self` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | 保留 approval_type: self 原文；local self-approve（INV-38） | ☐ |
| 自批准 | Self-approve | `plan.selfApprove` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | sidecar 未给 ui_label 时的回落；Self-approve | ☐ |
| 计划摘要（可修改） | Plan summary (editable) | `plan.summary.aria` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | 可编辑摘要 | ☐ |
| 超时 {seconds}s = 拒绝 | Timeout {seconds}s = reject | `plan.timeout` · apps/desktop/renderer/components/investigation/PlanPanel.tsx / usePlan.tsx | 超时=拒绝；Timeout Ns = reject（INV-05） | ☐ |
| 批准生效 | Approve | `settings.skills.approve` · apps/desktop/renderer/views/settings/SkillsSection.tsx | 与 en.json 草案一致；界面普通文案/设置项 | ☐ |
| 批准 | approve | `settings.skills.approveWord` · apps/desktop/renderer/views/settings/SkillsSection.tsx | 与 en.json 草案一致；界面普通文案/设置项 | ☐ |
| 已批准 · {name} | Approved · {name} | `settings.skills.approved` · apps/desktop/renderer/views/settings/SkillsSection.tsx | 与 en.json 草案一致；界面普通文案/设置项 | ☐ |

---

## C · 档位与能力（5 条）

看点：只关心 Full / Read-only 两个词在全局是否一处一个译法。这组重复度高，扫一眼即可。

| 中文 | 建议英文 | 出处 | 为什么这么译 | ☐ |
|---|---|---|---|---|
| 能力档位 | Capability tier | `composer.tier.aria` · apps/desktop/renderer/components/investigation/Composer.tsx | 能力档位选择器 | ☐ |
| 完整 | Full | `composer.tier.full` · apps/desktop/renderer/components/investigation/Composer.tsx | 与 statusbar 同译 Full | ☐ |
| 只读 | Read-only | `composer.tier.readonly` · apps/desktop/renderer/components/investigation/Composer.tsx | 与 statusbar 同译 Read-only | ☐ |
| 完整 | Full | `statusbar.tierFull` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 档位 Full，非 Complete | ☐ |
| 只读 | Read-only | `statusbar.tierReadonly` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 档位；Glossary read-only（带连字符） | ☐ |

---

## D · 状态栏与连接态（10 条）

看点：状态栏常显五项的标签要短（1024 档一行放六个元素），同时不能短到失义。

| 中文 | 建议英文 | 出处 | 为什么这么译 | ☐ |
|---|---|---|---|---|
| 运行态 | Runtime status | `statusbar.aria` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 状态栏区域名；runtime status 比 status 更贴「运行态」 | ☐ |
| 连接中 | Connecting | `statusbar.connecting` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 连接态三点之一；Connecting 非 Connecting…（短） | ☐ |
| 环境详情 | Environment details | `statusbar.envDetails` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 展开环境详情 | ☐ |
| 离线 | Offline | `statusbar.offline` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 连接态三点之一 | ☐ |
| 在线 | Online | `statusbar.online` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 连接态三点之一 | ☐ |
| 已暂停 | Paused | `statusbar.paused` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 暂停运行态 | ☐ |
| 权限 | Permissions | `statusbar.permission` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | TCC/磁盘权限；复数 Permissions | ☐ |
| 沙箱 | Sandbox | `statusbar.sandbox` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 常显五项之一；Glossary 定 sandbox | ☐ |
| sidecar 未连接 | Sidecar not connected | `statusbar.sidecarOffline` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | tooltip；Sidecar 作专有名不翻 | ☐ |
| sidecar | sidecar | `statusbar.sidecarOk` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 正常态短标签 | ☐ |

---

## E · 其它（1 条）

看点：DEV 徽章那条长文案，里面 self-approve / WORM 的措辞与 B 组是否一致。

| 中文 | 建议英文 | 出处 | 为什么这么译 | ☐ |
|---|---|---|---|---|
| 开发构建 · 未公证 · 禁止分发。Plan Mode = 自批准 (approval_type=self)，超时=拒绝。本地哈希链 ≠ WORM。 | Development build · not notarized · not for distribution. Plan Mode = self-approve (approval_type=self), timeout=reject. Local hash chain ≠ WORM. | `app.devTitle` · apps/desktop/renderer/App.tsx | DEV 徽章 title；self-approve 与计划条一致 | ☐ |

---

## 拿不准的六条

以下是我译得心虚、或前后不一致的地方，按该不该改的把握从高到低排：

1. **`settings.skills.approve`「批准生效」→ `Approve`** —— 丢了「生效」。技能批准后是**立即启用**，与计划面板那个「批准」（放行这一次运行）不是一回事，但现在两条都是 `Approve`。建议 `Approve & activate`。
2. **`settings.skills.approveWord`「批准」→ `approve`（小写）** —— 与其余 `Approve` 大小写不一。若它是嵌在句子中间的词，小写是对的；我没确认它的上下文，你看一眼实际渲染再定。
3. **`statusbar.sidecarOk`「sidecar」→ `sidecar`（小写）vs `statusbar.sidecarOffline`「sidecar 未连接」→ `Sidecar not connected`（大写）** —— 同一个专有名两种写法。建议统一大写 `Sidecar`。
4. **`plan.selfApprove`「自批准」→ `Self-approve` vs `plan.self` 里的 `local self-approve`** —— 大小写差异是因为位置不同（标题 vs 句中），我认为可以接受，但你若要求全局一致我就统一。
5. **`degradation.mock.label`「模型为 mock」→ `Model is mock`** —— 直白但弱。detail 那条已经写死 `must not be used as findings`，所以我保留了 label 的直白。若你要 label 自身就带警示，可改 `Mock model — not for findings`。
6. **`statusbar.permission`「权限」→ `Permissions`（复数）** —— 指的是 TCC 磁盘访问那一类系统授权。若你更想强调是「磁盘访问」而非泛指权限，可改 `Disk access`，与 `degradation.tcc.label` 对齐。

其余 37 条我认为可以直接过；有异议的直接改格子即可。

