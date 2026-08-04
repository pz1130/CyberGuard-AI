# 15 · 公证说明与卸载流程（M7）

状态：草稿 · 2026-08-02

---

## A. 公证会把什么上传给 Apple？

macOS **Developer ID + Notarization** 要求将待分发的二进制（或含二进制的归档）提交给 Apple 公证服务。Apple 会：

- 扫描恶意软件特征  
- 票据化（ticket）供 Gatekeeper 在线/装订验证  

**可能的客户顾虑**（政府 / 军工 / 金融）：

| 顾虑 | 我们的说明 |
|------|------------|
| 源码是否上传？ | **否**。上传的是编译后的应用包 / dmg / zip，不是源码仓库。 |
| 客户数据是否上传？ | **否**。公证在发布流水线执行，与终端用户会话数据无关。 |
| 二进制是否被 Apple 留存？ | 按 Apple 公证政策处理；我们不在公证通道中嵌入客户调查数据。 |
| 能否跳过公证？ | 企业内部分发可用 Developer ID 未公证 + MDM 信任，但 **Gatekeeper 体验差**；对外 GA 以公证为准（DEC-026）。 |

当前仓库状态：**开发版 / 未公证**。UI 与启动横幅不得宣称已公证或已通过安全评审（INV-38）。

### 发布流水线（目标态，需证书）

1. `electron-builder` 产出 `CyberGuard.app` / `.dmg`  
2. `codesign --deep --options runtime`（Developer ID）  
3. `xcrun notarytool submit` + `stapler staple`  
4. 生成更新 manifest：`version`、`artifact_sha256`、Ed25519 `signature`  
5. 审计：构建 ID、签名证书指纹、公证 ticket id  

证书吊销 / 过期：运维 runbook 单独维护（证书轮换后强制升级通道）。

### 仓库内骨架（无证书也可跑）

| 路径 / 命令 | 作用 |
|-------------|------|
| `apps/desktop/electron-builder.yml` | appId、mac hardenedRuntime、afterSign、产物命名 |
| `apps/desktop/entitlements/release.plist` | GA Hardened Runtime 最小权限 |
| `apps/desktop/scripts/notarize.cjs` | afterSign：无 `APPLE_*` 时 **DRY-RUN 退出 0**（不宣称已公证） |
| `npm run pack:check` | 校验骨架完整性 + 模拟 dry-run 公证钩子 |
| `npm run dist:dir` / `dist:mac` | 需 `electron-builder`；真实公证还要 `CSC_NAME` + `APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD` / `APPLE_TEAM_ID` |

```bash
cd apps/desktop
npm run pack:check          # 无证书，应 PASS
# CYBERGUARD_NOTARIZE_DRY_RUN=1 强制跳过提交（默认缺凭证即 dry-run）
```

**INV-38**：缺证书时流水线不得在 UI/日志中写成「已公证」。

---

## B. 卸载流程

### B.1 应用内（推荐）

**UI**：右侧 Context → **Data · Export / Uninstall (M7)**；托盘菜单亦有入口。  
Export 走系统「另存为」对话框 + 口令（≥8）；Uninstall 先 Inventory / Dry-run，真正删除前有二次确认框。

```text
RPC uninstall.inventory   → 预览将删除 / 不删除的内容
RPC uninstall.execute { "confirm": true, "dry_run": false }
RPC export.encrypted { dest_path, passphrase }
```

或 headless：

```bash
# dry-run
printf '%s\n' '{"id":"1","method":"uninstall.inventory","params":{}}' | \
  PYTHONPATH=packages .venv/bin/python -m apps.desktop.sidecar

# 真正删除（危险）
printf '%s\n' '{"id":"2","method":"uninstall.execute","params":{"confirm":true,"dry_run":false}}' | \
  PYTHONPATH=packages .venv/bin/python -m apps.desktop.sidecar
```

**会删除**

- `~/Library/Application Support/CyberGuard`（或 `CYBERGUARD_DATA_DIR`）  
  含 sessions（加密正文）、audit、episodic、evidence **索引**、trust、tmp 等  
- secrets 文件后端；尽力删除 Keychain 中 provider / index 等条目  

**删除密钥 = crypto-shred**：即便 SSD 上残留密文，无密钥则会话正文不可恢复。

**不会自动删除**

- 用户自选位置的证据原文件（`evidence.list` 中 path 在 data_root 之外的）——仅列出  
- TCC Full Disk Access 授权（**无法程序化撤销**）  
- `/Applications/CyberGuard.app` 本包（由用户拖到废纸篓）

### B.2 手动步骤（卸载后）

1. **TCC**：系统设置 → 隐私与安全性 → 完全磁盘访问 → 移除 CyberGuard / Electron  
2. **应用包**：删除 Applications 中的 app  
3. **外部证据**：根据卸载报告中的路径清单自行处理  
4. **钥匙串**：若仍有 `cyberguard.*` 通用密码项，可在「钥匙串访问」中搜索删除  

### B.3 残留清单自检

```bash
ls -la ~/Library/Application\ Support/CyberGuard 2>/dev/null || echo "data_root gone"
security find-generic-password -s cyberguard.provider 2>&1 | head -3
```

---

## C. 加密导出（卸载前 / 备份）

敏感目录已排除系统备份；长期留存请用显式导出：

```text
export.encrypted
  dest_path: ~/Desktop/cg-export.cgx
  passphrase: ****
  include: ["sessions", "audit", "evidence", "episodic", "trust.json"]
```

- 若本机有 `age`：优先 age 口令或 recipient 公钥（标准格式）  
- 否则：`CGX1` + PBKDF2 + Fernet 信封（可用同库解密；格式见 `export_bundle.py`）  

**导出不含** Keychain 中的 API key 明文。加密会话正文在无密钥时导出后仍为密文——请在导出前如需明文，先在可信环境解密会话（产品后续可提供「导出时附带会话密钥」的可选开关，默认关）。

---

## D. 与 INV-38

卸载与公证文档必须诚实：

- 本地哈希链 ≠ WORM  
- 自批准 ≠ 职责分离  
- 未公证构建 ≠ 安全已认证  
