# 10 · 开发环境注意事项

状态：活文档 · 遇到坑就往里加

本文记录**会浪费大量时间但原因不明显**的环境问题。开发桌面端前先读一遍。

---

## ⚠️ 头号大坑：TCC 授权会随签名变化而失效

**现象**：昨天还好好的，今天重新构建之后，agent 读 `~/Downloads` 下的文件突然报"文件不存在"。检查代码没问题，检查路径没问题，怀疑人生。

**原因**：macOS 的 TCC（完全磁盘访问等隐私授权）**绑定的是 bundle identifier + 代码签名标识**，不是路径。未签名或使用临时（ad-hoc）签名的构建，每次重建可能被系统视为**另一个应用**——于是之前授予的权限对新构建无效。

而 TCC 拒绝是**静默的**：文件读取直接返回"不存在"，不是"权限不足"。这就是为什么会往代码里查半天。

**解决**：开发期也用一个**固定的本地自签名证书**，保持签名标识一致。

```bash
# 一次性：创建自签名代码签名证书
# 钥匙串访问 → 证书助理 → 创建证书
#   名称: CyberGuard Dev
#   身份类型: 自签名根证书
#   证书类型: 代码签名

# 每次构建后签名（保持标识一致，TCC 授权就能留住）
codesign --force --deep --sign "CyberGuard Dev" /path/to/CyberGuard.app
```

不需要 Apple 开发者账号，成本几乎为零。**这一步省不得**——否则整个开发期会反复丢授权。

**排查口诀**：文件读不到、路径确认没错、又刚重新构建过 → 先查 TCC，别查代码。

```bash
# 查看当前 TCC 授权状态
tccutil reset SystemPolicyAllFiles com.cyberguard.desktop   # 重置后重新授权
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
