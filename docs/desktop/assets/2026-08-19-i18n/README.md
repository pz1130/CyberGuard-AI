# 2026-08-19 i18n 出口截图（判据 6）

状态：**已补做**（2026-08-19 晚，controller 用 CDP 完成）· 12 张齐全，无溢出无截断

原先 BLOCKED 的原因已查明：**启动时有一个原生模态框**（「M3/M4 development version… I understand」）
挡在主窗口之前，未关掉它 CDP 就没有 page target（`/json/list` 与 `Target.getTargets` 都是空）。
用 AX 按钮名点掉即可，不要用屏幕坐标点：

```bash
osascript -e 'tell application "System Events" to tell (first process whose unix id is <pid>) to click button "I understand" of window 1'
```

**第二个坑**：切语言不能直接写 `localStorage.cg.language` —— `useUiPrefs` 挂载时会用
`prefsGet()` 从 sidecar 的 `ui_prefs.json` 回填并盖掉它（sidecar 是权威源，符合设计）。
要走 `window.cyberguard.prefsSet({ language: "en" })` 再 reload，这也正是界面点选走的那条路。

命名约定：`<lang>-w<width>-<view>.png`，共 2 × 2 × 3 = 12 张。视口 1440×900 与 1024×768；每档每语言各重载一次。

## Files

| File | Lang | Width | View |
|---|---|---|---|
| `zh-w1440-workbench.png` | zh | 1440 | workbench |
| `zh-w1440-evidence.png` | zh | 1440 | evidence |
| `zh-w1440-settings.png` | zh | 1440 | settings |
| `zh-w1024-workbench.png` | zh | 1024 | workbench |
| `zh-w1024-evidence.png` | zh | 1024 | evidence |
| `zh-w1024-settings.png` | zh | 1024 | settings |
| `en-w1440-workbench.png` | en | 1440 | workbench |
| `en-w1440-evidence.png` | en | 1440 | evidence |
| `en-w1440-settings.png` | en | 1440 | settings |
| `en-w1024-workbench.png` | en | 1024 | workbench |
| `en-w1024-evidence.png` | en | 1024 | evidence |
| `en-w1024-settings.png` | en | 1024 | settings |

## 目视结论（EN）

| 检查点 | 结果 |
|---|---|
| 状态栏五项是否挤爆 | 未挤。1024 档 `Online · Sandbox · Permissions · live · Read-only · Environment details` 一行放得下 |
| 设置页左侧分区导航 200px 是否截断 | 未截断，`Data sources (MCP)` 完整显示 |
| 正文列 736px 是否被英文撑破 | 未撑破，空态三张卡与 composer 均在列内 |

`Sandbox unavailable` 这条没能在目视中复现 —— 本机沙箱正常，状态栏是常态。
它的英文由 `degradation.test.tsx` 的英文用例覆盖（断言整条进 danger 态且文案含 sandbox）。

截图期间发现并修掉一处英文 copy bug：`settings.hub.lede` 的 `Current LLM:` 缺尾随空格，
渲染成 `Current LLM:live`（中文用全角冒号自带间距，英文没有）。已修并重拍。

侧栏会话标题在英文档下仍是中文 —— 那是历史会话数据，按 spec §2.2 不翻。
