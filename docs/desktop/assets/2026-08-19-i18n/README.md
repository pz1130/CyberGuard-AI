# 2026-08-19 i18n 出口截图（判据 6）

状态：**BLOCKED** — Task 7 未能可靠驱动 Electron/CDP 截图；勿用占位 PNG。Controller 后续用 CDP 补做。

命名约定：`<lang>-w<width>-<view>.png`，共 2 × 2 × 3 = 12 张。视口 1440×900 与 1024×768；每档每语言各重载一次。

## Expected files

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

## Review focus (EN)

- 状态栏五项是否挤爆
- `Sandbox unavailable` 是否溢出
- 设置页左侧分区导航 200px 是否截断

发现溢出改 CSS 并重截，不要记进「已知问题」。
