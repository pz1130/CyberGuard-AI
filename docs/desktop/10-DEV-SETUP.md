# 10 · 开发环境注意事项

状态：活文档 · 遇到坑就往里加

本文记录**会浪费大量时间但原因不明显**的环境问题。开发桌面端前先读一遍。

---

## vite 必须绑 127.0.0.1，否则 `npm run dev` 起不来

**现象**：`npm run dev` 里 vite 正常打印 `ready`，Electron 窗口却是空的，日志里一行
`Failed to load URL: http://127.0.0.1:5173/ with error: ERR_CONNECTION_REFUSED`。

**原因**：`electron/main.cjs` 与 `renderer/index.html` 的 CSP 都写死了 `http://127.0.0.1:5173`
（IPv4 字面量，比 `localhost` 更收紧）。而 vite 默认按 `localhost` 解析监听地址——在把
`localhost` 先解析成 `::1` 的机器上，它只监听 IPv6，壳去连 IPv4 自然被拒。
`wait-on tcp:5173` 也解析到 `::1`，于是它先"等到了"，把竞态伪装成随机失败。

**结论**：`vite.config.ts` 的 `server.host` 固定 `"127.0.0.1"`，`wait-on` 写成
`tcp:127.0.0.1:5173`。两处都已改（2026-08-18）。**不要把它改回 `localhost`**——
改的话得同时动 main.cjs 的 loadURL 与 index.html 的 CSP，等于为了省一行配置放宽 CSP。

**排查口诀**：窗口空白 + vite 说 ready → 先 `lsof -nP -iTCP:5173 -sTCP:LISTEN` 看它绑的是
IPv4 还是 IPv6，别查渲染层。

---

## git worktree 里跑 pytest 会假失败：缺 `.env`

**现象**：在 `.worktrees/<name>/` 里跑 `pytest -q tests/test_desktop_*.py`，出现 1 个 ERROR：

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  Value error, ENCRYPTION_KEY and SECRET_KEY must be configured with unique values.
```

**原因**：`.env` 被 `.gitignore` 忽略，**只存在于主 checkout**，`git worktree add` 不会带过去。
而 pydantic-settings 是从**当前工作目录**读 `.env` 的，于是 worktree 里读不到密钥，
`Settings` 校验失败。它以 ERROR 而非 FAIL 出现（发生在 fixture 阶段），很容易被误判成
teardown 问题或测试代码 bug。

**修法**：把主 checkout 的 `.env` 软链进 worktree。

```bash
ln -sf "$(git rev-parse --show-toplevel)/.env" .worktrees/<name>/.env
```

链完 146 个桌面测试全过、零 error。**注意 `.venv` 不需要这么做** —— `git worktree add`
之后它通常已经是软链或能被找到；只有 `.env` 这类被忽略的配置文件会漏。

**排查口诀**：worktree 里测试比主目录多出 error、且报的是 pydantic/Settings/密钥 →
先看 `ls -l .env`，别查测试代码。

---

## ⚠️ 头号大坑：TCC 授权会随签名变化而失效

**现象**：昨天还好好的，今天重新构建之后，agent 读 `~/Downloads` 下的文件突然报"文件不存在"。检查代码没问题，检查路径没问题，怀疑人生。

**原因**：macOS 的 TCC（完全磁盘访问等隐私授权）**绑定的是 bundle identifier + 代码签名标识**，不是路径。未签名或使用临时（ad-hoc）签名的构建，每次重建可能被系统视为**另一个应用**——于是之前授予的权限对新构建无效。

而 TCC 拒绝是**静默的**：文件读取直接返回"不存在"，不是"权限不足"。这就是为什么会往代码里查半天。

**解决**：开发期也用一个**固定的本地自签名证书** + **固定 bundle id**（`com.cyberguard.desktop.dev`），保持签名标识一致。

```bash
cd apps/desktop
npm install

# 1) 一次性：创建/导入「CyberGuard Dev」代码签名身份（无需 Apple 付费账号）
npm run codesign:identity

# 2) 每次 npm install 或 Electron 被覆盖后：签名本地 Electron.app
npm run codesign:dev
# 或开发时一步到位
npm run dev:signed

# 3) 校验
npm run codesign:verify
```

脚本位置：

| 脚本 | 作用 |
|------|------|
| `scripts/ensure-dev-codesign-identity.sh` | 生成并导入自签名 codesign 证书（CN=`CyberGuard Dev`） |
| `scripts/codesign-electron-dev.sh` | 改 `CFBundleIdentifier` 并签名 `node_modules/electron/dist/Electron.app` |
| `scripts/verify-dev-codesign.sh` | 检查 identity + Identifier + `codesign --verify` |
| `entitlements/dev.plist` | 开发用 entitlements（允许 spawn Python/MCP；**勿用于客户分发**） |

首次签名后：到 **系统设置 → 隐私与安全性 → 完全磁盘访问**，勾选该 Electron/CyberGuard 路径（脚本结束会打印路径）。之后 rebuild 只要**同一 identity + 同一 bundle id**，TCC 通常会保留。

不需要 Apple 开发者账号，成本几乎为零。**这一步省不得**——否则整个开发期会反复丢授权。

**排查口诀**：文件读不到、路径确认没错、又刚重新构建过 → 先查 TCC / 是否重签，别查代码。

```bash
# 重置后重新授权（bundle id 以实际 codesign -dv 为准）
tccutil reset SystemPolicyAllFiles com.cyberguard.desktop.dev
```

---

## 分发与签名（生产）

产品要**发给客户但不上架 App Store**，所以走 **Developer ID 签名 + 公证（notarization）**：

| 档位 | 是否需要 | 说明 |
|---|---|---|
| App Store 上架 | ❌ 不做 | 需 App Review 且强制 App Sandbox，跑不了本地扫描工具 |
| **Developer ID + 公证** | ✅ **就是这个** | 无需人工审核，Apple 自动扫描后盖章，客户双击即可安装 |
| 完全不签名 | ❌ | 要教客户绕过 Gatekeeper——安全产品这么干观感极差 |

**前置条件**：付费 Apple Developer Program 账号（99 美元/年）。证书有效期与吊销流程要纳入运维——**证书过期会导致无法签发新版本**（已安装的不受影响）。

**公证会把二进制上传给 Apple。** 政府、军工、金融类客户可能对此有疑问，建议在产品说明里主动写清楚（只是自动恶意代码扫描，不涉及源码），别等被问。

**Hardened Runtime 是公证的前提**，而它与 PyInstaller、子进程 spawn 有冲突，需要申请 `allow-unsigned-executable-memory` / `allow-dyld-environment-variables` / `disable-library-validation` 等 entitlements——**这些会削弱应用自身的完整性保护，必须在安全评审材料中主动披露**。

---

## 其他已知坑

**抓包需要 `/dev/bpf*` 权限。** 默认不可读（这就是 Wireshark 要装 ChmodBPF 的原因）。首版不装特权辅助工具，抓包类工具标为需集中执行（DEC-009）。

**PyInstaller 用 onedir 不用 onefile。** onefile 每次启动解压到临时目录，与 Hardened Runtime 冲突；onedir 目录可直接签名，启动也更快（DEC-008）。

**客户终端的 EDR 会告警。** 应用行为特征——spawn Python 子进程、spawn MCP 子进程、调用 `sandbox-exec`、执行扫描器——在 CrowdStrike / SentinelOne 眼里与恶意软件画像高度重合。需要准备 EDR 白名单指引（进程路径、签名标识、预期行为），否则第一批客户装完就被自己的 EDR 拦掉，而且会先怀疑你的产品。见 M7。

**`sandbox-exec` 路径必须硬编码 `/usr/bin/sandbox-exec`**，不走 PATH 查找（防 PATH 注入）。该接口被标记 deprecated 多年但仍是 Chrome、codex 在用的方案，短期可靠。

**Tailwind v4 依赖 `@property` / `oklch`。** 这是选 Electron（自带 Chromium）而非 Tauri（用系统 WebView）的实际原因之一——不用担心 WebView 版本差异。
