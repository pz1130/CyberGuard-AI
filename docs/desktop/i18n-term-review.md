# 桌面端 i18n 安全术语审阅表

状态：**待用户定稿** · 2026-08-19（Task 7）

范围：全部 `degradation.*`、`statusbar.*`、审批与档位相关词条。
判据 3 要求本表每一条经人确认后，再把定稿写回 `docs/desktop/06-GLOSSARY.md`。
下表「建议英文」已落入 `en.json`，作为草案运行；**未打勾前判据 3 保持 open**。

| 中文 | 建议英文 | 出处 | 为什么这么译 | ☐ |
|---|---|---|---|---|
| 开发构建 · 未公证 · 禁止分发。Plan Mode = 自批准 (approval_type=self)，超时=拒绝。本地哈希链 ≠ WORM。 | Development build · not notarized · not for distribution. Plan Mode = self-approve (approval_type=self), timeout=reject. Local hash chain ≠ WORM. | `app.devTitle` · apps/desktop/renderer/App.tsx | DEV 徽章 title；self-approve 与计划条一致 | ☐ |
| 能力档位 | Capability tier | `composer.tier.aria` · apps/desktop/renderer/components/investigation/Composer.tsx | 能力档位选择器 | ☐ |
| 完整 | Full | `composer.tier.full` · apps/desktop/renderer/components/investigation/Composer.tsx | 与 statusbar 同译 Full | ☐ |
| 只读 | Read-only | `composer.tier.readonly` · apps/desktop/renderer/components/investigation/Composer.tsx | 与 statusbar 同译 Read-only | ☐ |
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
| 完整 | Full | `statusbar.tierFull` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 档位 Full，非 Complete | ☐ |
| 只读 | Read-only | `statusbar.tierReadonly` · apps/desktop/renderer/i18n/zh.json + StatusBar.tsx | 档位；Glossary read-only（带连字符） | ☐ |
