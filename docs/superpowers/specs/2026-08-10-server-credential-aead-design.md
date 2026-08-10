# 服务端凭据加密：从未认证 AES-CBC 迁移到 AEAD

状态：**已实现** · 2026-08-10 · §10 三项已拍板，§9 判据全部通过

实现：`app/core/security.py`（AEAD + `CredentialField`）、`app/services/encryption_status.py`（启动扫描）、
`scripts/reencrypt_credentials.py`（重写脚本）、`tests/test_credential_aead.py` + `tests/test_reencrypt_script.py`。

**来源**：2026-08-10 全项目 review 第 6 条。前五条已落地（`cad112d` / `76093d2` / `fcb26f0`），这条因为涉及存量密文迁移，按仓库惯例先出设计。

---

## 1. 现状

`app/core/security.py` 的 `AESCipher` 是裸 AES-256-CBC + PKCS7，**没有 MAC，不是 AEAD**：

```python
iv = os.urandom(16)
cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), ...)
combined = iv + ciphertext
return base64.b64encode(combined).decode('utf-8')
```

三个具体问题：

1. **密文可篡改，而且是可控改写，不是随机破坏。** CBC 里 `plaintext[0] = D(ct[0]) XOR IV`，而 IV 就明文存在密文头 16 字节。翻转 IV 的某一位就精确翻转明文第一个分组的对应位，**且 padding 在最后一个分组，第一个分组的改写不触发任何错误**。

   在当前代码上实测（这就是验收判据 §9 第 2 条的现成用例）：

   ```
   original : sk-live-PRODUCTION-key
   forged   : sk-live-ATTACKERON-key
   ```

   拿到数据库写权限的人可以把任意凭据的**前 16 字节改成自己指定的内容**，解密**不报任何错**，应用照常拿去用。改到第一分组之外才会撞上 padding 校验 —— 而那时报的是 `ValueError: Decryption failed: Invalid padding bytes`，正好是第 3 点的 oracle。
2. **无来源绑定。** 任何一列的密文可以整段搬到另一列、另一行，解密照样成功。拿到数据库写权限的人可以把测试 Provider 的 key 换到生产 Provider 上，或把 A 租户的 MCP 凭据搬给 B。
3. **解密失败可区分。** `decrypt_data` 抛 `ValueError(f"Decryption failed: {e}")`，padding 错误与内容错误的异常信息不同。只要有任一路径把它回显给调用方，就是 padding oracle 的雏形。

**对照**：桌面端同期写的 `apps/desktop/sidecar/data_crypto.py` 用的是 Fernet（AES-CBC + HMAC），`export_bundle.py` 用 PBKDF2 + Fernet。**新代码做对了，服务端这块是历史遗留没跟上**。

### 诚实的威胁模型边界

按 INV-38，先说防不住什么，避免做安全剧场：

| | 现状 | 换 AEAD 之后 |
|---|---|---|
| 数据库**只读**泄漏（备份泄漏、只读副本、SQL 注入读） | 已防住 | 同样防住 |
| 数据库**写**权限的攻击者篡改/搬运密文 | **防不住** | **防住** |
| 拿到 `ENCRYPTION_KEY` 的攻击者 | 防不住 | 防不住 |
| 应用进程内存取证 | 防不住 | 防不住 |
| 有 app 服务器 shell 的攻击者 | 防不住 | 防不住 |

**这次迁移买到的是"数据库写权限 ≠ 凭据替换权限"**，不是别的。`ENCRYPTION_KEY` 与密文同机时，收益边界就到这里 —— 产品文案不得超出这个范围宣称。

---

## 2. 影响面

### 2.1 数据库列（8 个）

| 模型 | 列 | 内容 |
|---|---|---|
| `provider.py` | `api_key_encrypted` | LLM Provider API key |
| `mcp.py` | `env_vars_encrypted` | MCP server 环境变量 JSON |
| `mcp.py` | `auth_token_encrypted` | MCP 认证 token |
| `agent.py` | `env_vars_encrypted` | 外部 agent 环境变量 JSON |
| `envvar.py` | `value_encrypted` | 全局环境变量 |
| `n8n.py` | `api_key_encrypted` | n8n 连接凭据 |
| `webhook.py` | `outgoing_secret_encrypted` | 出向 webhook 签名密钥 |
| `knowledge.py` | `metadata_encrypted` | 知识库条目元数据 |

调用点：`encrypt_data` 18 处、`decrypt_data` 17 处，全部经 `app/core/security.py` 两个函数，**没有旁路** —— 这是这次迁移唯一让人放心的地方。

### 2.2 数据库之外 —— 这条决定了迁移策略

`app/routers/backup.py::_encrypt_dump` 把 **pg_dump 的整个产物** base64 后走同一个 `encrypt_data`，落成磁盘文件。

**这些文件不在数据库里，alembic 迁移碰不到它们。** 客户手上可能存着几个月前的备份，而备份的全部意义就是很久以后还能恢复。

> **推论：`decrypt_data` 必须永久保留读取 legacy 格式的能力。** 这不是"过渡期兼容"，是长期契约。写入端可以立刻只写新格式，读取端不能设废弃期。

### 2.3 不受影响的

- 密文**从未**参与 SQL 比较或索引（`grep` 确认无 `_encrypted ==` / `.in_` / `where` 用法）→ **随机 nonce 安全，不需要确定性加密**。这排除了本类迁移最常见的坑。
- `agent.api_key_hash` 是 SHA-256，不是加密，不在范围内。
- 桌面端 `data_crypto.py` / `export_bundle.py` 已是 Fernet，不在范围内。

---

## 3. 决策一：算法选 AES-256-GCM，不选 Fernet

**决策**：`AESGCM`（`cryptography.hazmat.primitives.ciphers.aead`）。

考虑过直接复用桌面端的 Fernet 以保持全仓一致，否决理由：

- **Fernet 不支持 AAD。** §5 的来源绑定是这次迁移的主要收益之一，Fernet 结构上给不了。
- **Fernet 是 AES-128。** 现有配置项叫 `ENCRYPTION_KEY` 且宣称 AES-256，换 Fernet 等于悄悄降到 128 位密钥强度。虽然 128 位足够，但**在安全产品里把宣称的强度降一半而不说**，正是 INV-38 禁止的。
- Fernet 的密钥格式是它自己的 urlsafe-base64，与现有 `ENCRYPTION_KEY` 不同源，还要多一层派生。

代价：GCM 的 nonce 复用是灾难性的（泄露认证密钥）。缓解见 §4 —— 每次加密独立 `os.urandom(12)`，永不计数器化、永不复用。以 96 位随机 nonce 计，同一密钥下要到约 2³² 次加密才有可观碰撞概率；本系统凭据写入频次远低于此，但轮换机制（§7）仍应存在。

---

## 4. 决策二：密文格式

```
CG2.<key_id>.<base64url(nonce ‖ ciphertext ‖ tag)>
```

- 前缀 `CG2.` —— **base64 字母表不含 `.`**，所以与 legacy 密文（纯 base64）天然不歧义。判别只需 `startswith("CG2.")`，不需要试解密。
- `key_id` —— 现在恒为 `k1`，但**格式里先占住位置**。等到真要轮换密钥时，不必再做一次全量密文迁移。这是本设计里成本最低、回报最高的一格。
- nonce 12 字节，tag 16 字节（GCM 默认）。

`decrypt_data` 的分派：

```
CG2. 开头  → AEAD 路径
其他       → legacy CBC 路径（永久保留，见 §2.2）
```

---

## 5. 决策三：AAD 绑定到哪一层 —— **需要拍板，见 §10**

AAD 是这次能拿到的"防搬运"能力，但绑得越细，运维越硬。三个档位：

| 档位 | AAD 内容 | 挡住 | 代价 |
|---|---|---|---|
| **A** | 无 AAD | 只挡篡改 | 密文仍可跨行跨列搬运 |
| **B** | `"<table>.<column>"` | 跨列搬运（把 webhook secret 塞进 provider key 列） | 几乎为零 —— 调用点静态可知 |
| **C** | `"<table>.<column>.<row_id>"` | 跨行搬运（把测试 Provider 的 key 搬到生产 Provider） | INSERT 时拿不到自增主键，需要两段式写入或改用应用侧生成的 UUID |

**倾向 B**，理由：C 挡住的攻击（同列跨行搬运）需要的权限，与直接改 `provider.base_url` 指向攻击者端点是同一级别 —— 而后者没有任何加密能拦。为了一个被更简单路径绕过的威胁，去换 INSERT 路径的两段式写入和一堆边界情况，不划算。

B 是纯收益：调用点全部静态可知，改动量为每个调用点补一个字面量参数。

> 这条留给人定，因为它是**产品安全声明的边界**，不是纯技术选择。

---

## 6. 决策四：迁移策略 —— 惰性重写，不做一次性数据迁移

**决策**：不写 alembic 数据迁移。改为：

1. `encrypt_data` **立即**只产出 `CG2.` 格式。
2. `decrypt_data` 两种都读。
3. 加一个**一次性重写脚本**（`scripts/reencrypt_credentials.py`），可重复执行、按行幂等（看前缀决定跳过还是重写），运维择机跑。
4. 提供 `--dry-run` 与逐表统计。

为什么不走 alembic：

- **alembic 迁移里需要 `ENCRYPTION_KEY`。** 迁移通常在部署管线里跑，密钥未必在那个上下文；缺了就整个 upgrade 失败，把一次凭据维护变成一次发布阻塞。
- **迁移中途失败会留下混合状态。** 虽然前缀让它幂等可续，但混合状态出现在 `alembic upgrade head` 里比出现在一个可反复跑的独立脚本里难解释得多。
- **没有 schema 变更。** 列类型都是 `Text`，密文变长（多 28 字节 + 前缀）远在范围内。没有 DDL 就不该占一个 revision 号。

alembic head 当前是 `032_agent_run_events`，本设计**不新增 revision**。

---

## 7. 密钥派生与轮换

**现状有个坑要顺手修**：

```python
if len(key) != 32:
    key = hashlib.sha256(key.encode()).digest()
```

`ENCRYPTION_KEY` 是 64 个十六进制字符 → 长度不等于 32 → 走 SHA-256(ASCII 十六进制串)。也就是说**配置里那 256 位熵，实际只被当成一个字符串再哈希一遍**。结果是稳定的、强度也够（sha256 输出 256 位），但语义混乱：一个"32 字节 hex 密钥"和一个"32 字符口令"会派生出不同的密钥，而两者看起来都像合法配置。

**新格式下**：`k1` 的派生显式定义为 `SHA-256(ENCRYPTION_KEY.encode())`，**与 legacy 完全一致** —— 这样重写脚本不需要同时处理两套密钥，且万一要回滚，新旧密文用的是同一把密钥。

轮换留到以后：`key_id` 位置已占住，届时新增 `k2` 与一份 `{key_id: key}` 映射即可，重写脚本原样复用。

---

## 8. 失败模式（INV-25）

安全边界的失败必须响：

- **解密失败** → 抛统一的 `DecryptionError`，**对外信息不区分原因**（不回显 padding / tag 校验的差别），详情只进日志。这同时修掉 §1 第 3 点。
- **认证失败（tag 不匹配）** → 这是**篡改信号**，不是普通错误。必须 `logger.error` 并带上表名列名（不带密文、不带明文），够触发告警。
- 现有 `app/core/audit.py` 已有"凭据解密失败可见"的先例（CHANGELOG INV-25 行），沿用同一模式。
- 重写脚本遇到任何一行解不开：**停止并报告该行**，不得跳过继续 —— 跳过等于静默丢失一条凭据。

---

## 9. 验收判据

- [ ] 新写入的密文全部 `CG2.` 前缀；legacy 密文仍可读（**含一个真实的 legacy 备份文件恢复用例**）
- [ ] **§1 的 IV 改写用例**（`sk-live-PRODUCTION-key` → `sk-live-ATTACKERON-key`）在新格式下必须失败并记 error 日志。这条是整次迁移的核心判据 —— 它在当前代码上是**静默成功**的
- [ ] 篡改密文任意一位 → 解密抛 `DecryptionError` 且记 error 日志
- [ ] 把 A 列的密文写进 B 列 → 解密失败（AAD 档位 B 的核心用例）
- [ ] 同一明文加密两次密文不同（nonce 随机性）
- [ ] `decrypt_data` 的对外异常信息在 padding 错误与 tag 错误下**完全一致**
- [ ] 重写脚本：跑两遍结果一致（幂等）；`--dry-run` 不改数据；中途中断后可续跑
- [ ] 全量测试绿，且**每个提交单独绿**（CLAUDE.md：不许先红后绿跨提交）
- [ ] `make check` 通过

---

## 10. 已拍板（2026-08-10）

1. **AAD 档位 = B**，`"<table>.<column>"`。跨列搬运挡住，跨行不挡 —— 因为能跨行搬运的权限也足够直接改 `provider.base_url` 指向攻击者端点，而那条路径没有任何加密能拦。
   **安全声明的措辞边界**：可以说"凭据密文与其所在字段绑定，跨字段搬运会被拒绝"；**不得**说"凭据无法被替换"。

2. **legacy 读取路径不设废弃期。** 长期契约，不是过渡兼容。理由见 §2.2：备份文件在数据库外，且备份的价值就是很久以后还能恢复。
   → 因此 `_decrypt_legacy_cbc` 上必须有注释写明"这不是待删代码"，否则将来一定有人当死代码清掉。

3. **启动时统计残留 legacy 密文并告警。** 惰性兼容意味着不跑重写脚本也能用，所以必须有东西持续提醒，否则存量密文会无限期停留在可篡改状态。
   实现：启动扫描 8 列，计数写进进程级状态；`GET /api/v1/security/encryption-status` 暴露；日志按数量分级（>0 → warning）。**只计数，不解密**。

### AAD 取值表（唯一权威来源，实现见 `app/core/security.py::CredentialField`）

| 常量 | AAD 值 |
|---|---|
| `PROVIDER_API_KEY` | `providers.api_key_encrypted` |
| `MCP_ENV_VARS` | `mcp_servers.env_vars_encrypted` |
| `MCP_AUTH_TOKEN` | `mcp_servers.auth_token_encrypted` |
| `AGENT_ENV_VARS` | `agent_configs.env_vars_encrypted` |
| `ENV_VAR_VALUE` | `env_vars.value_encrypted` |
| `N8N_API_KEY` | `n8n_connections.api_key_encrypted` |
| `WEBHOOK_OUTGOING_SECRET` | `webhooks.outgoing_secret_encrypted` |
| `KNOWLEDGE_METADATA` | `knowledge_bases.metadata_encrypted` |
| `BACKUP_DUMP` | `backup.dump`（不是数据库列；备份文件用） |

> AAD 一旦写进密文就**不能改**——改了等于所有存量密文解不开。这张表的值是长期契约，与列名重命名解耦（列真被改名时，AAD 保持旧值并在此注明）。

---

## 11. 不在本设计范围

- 密钥轮换的实现（只占住格式位）
- KMS / HSM 托管 `ENCRYPTION_KEY`（真正提升边界的是这个，但属于部署形态变更）
- 桌面端 Fernet → 统一算法（无收益，且 `data_crypto.py` 已是认证加密）
- `agent.api_key_hash` 等哈希字段
