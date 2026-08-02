# 14 · EDR / MDM 白名单指引（M7）

状态：草稿 · 2026-08-02  
适用：macOS 桌面节点（开发 / 内部分发 / 未来公证版）

> 本应用的行为画像（spawn Python、stdio MCP、调用 `sandbox-exec`、读写调查目录）与部分恶意软件高度重合。  
> **客户是安全团队**——终端几乎必装 EDR。不提供白名单说明，首批安装会被自己的防护拦下，并优先怀疑产品。

---

## 1. 预期进程与路径

| 组件 | 典型路径 / 标识 | 行为 |
|------|-----------------|------|
| Electron 壳 | `CyberGuard.app/Contents/MacOS/CyberGuard`（发布）或 `Electron`（dev） | 无监听端口；spawn sidecar |
| Python sidecar | 项目 `.venv/bin/python -m apps.desktop.sidecar` 或 onedir 打包路径 | stdin/stdout JSONL；无 listen socket |
| Seatbelt | `/usr/bin/sandbox-exec` | 为 host 工具生成临时 profile 并执行白名单二进制 |
| MCP 子进程 | 用户配置的 `command`（如 `python3` + MCP server 脚本） | 进程组随 sidecar 退出清理 |
| 允许的 host 二进制 | `/bin/ls`、`/usr/bin/uname`、`/usr/bin/tee`、`/bin/rm` 等白名单 | **无 free-form shell** |

**Bundle ID（dev）**：`com.cyberguard.desktop.dev`  
**签名（dev）**：CN=`CyberGuard Dev`（见 `scripts/ensure-dev-codesign-identity.sh`）  
**签名（release）**：Developer ID Application（M7 流水线；未配置前禁止宣称已公证）

---

## 2. 网络画像

- **默认**：sidecar **不监听任何端口**（INV-07）。
- **出站**：仅当用户配置 live LLM Provider 或 MCP 需要时，HTTPS 到用户指定端点。
- **更新通道（规划）**：仅 HTTPS；证书固定；包级 Ed25519 验签（INV-42）。

---

## 3. 建议允许规则（通用表述）

请按贵司 EDR 产品映射为具体策略；下列为意图描述：

1. **允许** 已签名的 `CyberGuard.app` 及其 Team ID 启动 Python 子进程（sidecar）。  
2. **允许** sidecar 执行 `/usr/bin/sandbox-exec` 且参数为应用生成的 profile 路径（位于 Application Support 或 managed tmp）。  
3. **允许** sandbox-exec 子进程执行 allowlist 中的系统二进制（只读调查常见：`ls`、`uname`、`file` 等——以当前 `host_ops` 白名单为准）。  
4. **允许** 用户明确配置的 MCP 可执行文件路径（安装时收集 allowlist，而非任意 PATH）。  
5. **告警 / 需二次确认**：向非企业允许的域名发起 LLM API 出站（配合 `approved_remote` profile）。  
6. **阻断**：未签名或签名不匹配的更新包；sidecar 监听 TCP/UDP。

---

## 4. MDM 配置提示

- 预批准 **Full Disk Access**（若策略要求分析师读取受保护路径）；否则 TCC 横幅会提示 restricted。  
- 部署 Developer ID / 公证包时，启用 **Gatekeeper 标准**（无需用户关闭 Gatekeeper）。  
- 数据目录：`~/Library/Application Support/CyberGuard`（可用 `CYBERGUARD_DATA_DIR` 覆盖，测试用）。  
- 敏感目录已标记备份排除（`.cg-nobackup` + Time Machine xattr）；长期留存请用 **加密导出**（`export.encrypted`）。

---

## 5. 验证清单（至少一款主流 EDR）

在装有 CrowdStrike / SentinelOne / Microsoft Defender for Endpoint / 等产品的测试机上：

- [ ] 冷启动 Electron + sidecar，无误报隔离  
- [ ] 执行只读 `host_list_dir` / `host_read_file`  
- [ ] 配置 1 个 stdio MCP 并完成工具调用  
- [ ] 触发 Plan Mode 自批准后 full 档 host 工具  
- [ ] 更新通道验签失败用例被拒且有审计  

将 EDR 产品名、策略版本、截图/日志链入发布检查单。

---

## 6. 客户沟通要点

- 我们会 spawn 子进程与 `sandbox-exec`：**这是功能，不是后门**。  
- 凭据不进沙箱（Keychain / secrets store）。  
- 节点不听端口。  
- 更新必须双验签（包签名 + 应用公证），防供应链投毒。
