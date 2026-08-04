# 13 · M2 出口检查清单

状态：进行中 · 2026-07-31  
对照：`03-ROADMAP.md` M2 出口判据 + `2026-07-27-desktop-node-design.md` §3.1–3.2

> **规则**：每一项必须有「自动化证据」或「明确未完成」。不得用感觉代替。

---

## 如何跑逃逸 / M2 套件

```bash
cd cyberguard
export PYTHONPATH="packages:$(pwd)"
./apps/desktop/scripts/run_m2_suite.sh
# 或
.venv/bin/python -m pytest -q \
  tests/test_desktop_m2_escape.py \
  tests/test_desktop_m2_sandbox.py \
  tests/test_desktop_tcc.py \
  tests/test_desktop_sidecar.py \
  tests/test_desktop_m15_provider.py \
  tests/test_desktop_mcp_stdio.py \
  tests/test_desktop_m1_persistence.py
```

---

## 出口判据对照

| # | 判据 | 状态 | 证据 |
|---|------|------|------|
| 1 | 越出 `writable_roots` 写入被拦 | **PASS** | `test_escape_write_outside_writable_roots`, `test_escape_host_ops_blocks_outside_and_git`, `test_sandboxed_write_in_workspace_only` |
| 2 | 只读模式下写文件被拦 | **PASS** | `test_escape_read_only_blocks_any_write`, `test_seatbelt_read_only_blocks_write_outside` |
| 3 | 可写模式下 sessions/audit/logs/**evidence**/secrets/config 仍不可写 | **PASS** | `test_sandboxed_write_in_workspace_only`；`always_readonly_paths` 含 evidence/secrets/config；`test_escape_evidence_dir_not_writable_even_under_workspace` |
| 4 | `.git` 在可写根内仍不可写 | **PASS** | `test_escape_host_ops_blocks_outside_and_git` |
| 5 | 受限模式无网络（profile 层） | **PASS** | `test_profile_*_denies_network`；host_run 不允许 curl/nc |
| 6 | 自由 shell / 非白名单二进制被拒 | **PASS** | `test_escape_exec_disallows_shell_and_network_tools`, allowlist |
| 7 | 宿主凭据路径不可被 host 工具读取 | **PASS** | `test_escape_credential_path_blocked`（provider.json 等） |
| 8 | `sandbox_impl` 识别；`none` 时无真实主机 I/O | **PASS** | `test_detect_sandbox_impl_on_macos`, `test_sandbox_none_denies_real_host_io` |
| 9 | TCC 未授权时有明确提示（非静默当「文件不存在」） | **PASS（探测）** | `tcc_status` + UI 横幅/状态栏 `tcc: restricted`；FDA 为启发式，非公证 API |
| 10 | 状态栏展示 sandbox / tcc / llm / tier | **PASS** | `App.tsx` status bar；`ping` 返回 sandbox+tcc |
| 11 | readonly 档无 Exec/Edit 端口 | **PASS** | `test_escape_readonly_tier_no_exec_edit_ports` |
| 12 | 开发期签名稳定，TCC 不因 rebuild 失效 | **PASS（本机 2026-08-04）** | Identity `CyberGuard Dev` 已在 valid 列表；`Electron.app` → `com.cyberguard.desktop.dev` + `codesign --verify` OK；`npm run dev:signed` 可起；TCC 探针 `fda_likely`/FDA true。公证仍归 M7；`npm install` 后需重跑 `codesign:dev` |
| 13 | 签名 / 公证 | **不做（M7）** | DEC-026 |
| 14 | danger-full-access 默认关闭 | **PASS** | profile 生成直接拒绝 |

---

## 已落地能力（相对 M1.5）

| 能力 | 档位 | 机制 |
|------|------|------|
| `host_read_file` / `host_list_dir` | readonly + full | Seatbelt |
| `host_write_file` / `host_delete_file` | full | workspace/ + tmp/  only |
| `host_run` | full | 绝对路径白名单 argv，无 shell |
| MCP stdio | 两档 | 既有 |
| Live LLM | 配置后 | provider.json |

---

## 仍不算 M2「全部出口通过」的原因

1. ~~**开发签名 / TCC**~~ → **本机已过（2026-08-04）**：valid identity + signed Electron + FDA 探针 true；CI 无钥匙串时仍不强制。  
2. ~~**网络逃逸**~~ → **已加深（2026-08-04）**：Seatbelt 网络 deny 探针用例；host_run 仍禁止 curl/nc。  
3. ~~**原始证据目录**~~ → **已产品化命名**：`always_readonly_paths` 含 evidence/secrets/config。  
4. 产品仍标记 **development / 禁止分发**（正确）。

**出口签字（内部分发前）**：上表 1–12、14 在本机已绿；**仍禁止对外分发**直至 M7 真公证。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-31 | 初稿；对齐已实现 Seatbelt / host_* / TCC 探测与逃逸套件 |
| 2026-07-31 | 判据 12：增加开发期固定 codesign 脚本与 `dev:signed` |
| 2026-08-04 | evidence/secrets/config 纳入 always_readonly；网络 Seatbelt 探针用例 |
