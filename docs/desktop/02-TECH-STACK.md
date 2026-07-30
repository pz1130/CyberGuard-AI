# 02 · 技术栈

状态：定稿 · 2026-07-27

**规则：本文件列出的选型不得擅自替换。** 需要变更时改本文件并在 `05-DECISIONS.md` 追加一条决策记录，说明触发原因。

---

## 1. 桌面壳

| 项 | 选型 | 约束 |
|---|---|---|
| 框架 | **Electron** | 锁 major 版本，跟随 stable channel |
| 打包 | **electron-builder** | 负责 macOS 签名与 notarization |
| 安全配置 | `contextIsolation: true`、`nodeIntegration: false`、`sandbox: true` | **不可放宽**，见 INVARIANTS-07 |
| 主↔渲染 IPC | `contextBridge` 白名单方法 | 不暴露 `ipcRenderer` 全量 |
| 节点凭据存储 | Electron `safeStorage`（底层 Keychain） | Provider 原始密钥不经 Gateway 下发；不落配置文件、不落 localStorage |

不选 Tauri 的理由见 `05-DECISIONS.md` DEC-002。

## 2. 渲染层

沿用现有 `webui/` 技术栈，**不引入新 UI 框架**：

React 19 · Vite · Tailwind v4 · react-router · i18next · lucide-react · react-markdown · @monaco-editor/react

新增：`packages/ui-shared` 作为 npm workspace 包，Web 与桌面共用组件、i18n 词条、API client、主题。

> Tailwind v4 依赖 `@property` / `oklch` 等较新 CSS 特性。Electron 自带 Chromium 无兼容问题——这也是不选 Tauri（用系统 WebView）的实际原因之一。

## 3. Python Sidecar

| 项 | 选型 | 说明 |
|---|---|---|
| 运行时 | Python ≥ 3.11 | 与服务端 `requires-python` 一致 |
| 包管理 | `uv` | 沿用现有 `uv.lock` |
| 通信 | **stdin/stdout JSONL** | **不引入 FastAPI / uvicorn**——节点不开端口，HTTP 栈是纯负担 |
| 打包 | **PyInstaller onedir** | **不用 onefile**，见下 |
| 调度 | APScheduler | 已在现有依赖中 |
| 本地存储 | 会话 = 树状 JSONL 文件；元数据索引 = SQLite（`aiosqlite`） | 节点**不建本地向量库** |
| HTTP 客户端 | `httpx` | 与服务端一致 |

### 3.1 LLM 访问边界

桌面端的 agent loop 在 sidecar 中运行。服务端下发 Provider 的非敏感元数据（名称、模型、能力、上下文窗口和策略），但不下发服务端数据库中的原始 API Key。

节点凭据由用户或企业安装流程写入 macOS Keychain，并由 sidecar 在内存中使用。默认 Profile 只允许本机或企业内网 Provider；云端 Provider 必须由用户显式选择 `approved_remote` Profile，界面显示数据出网提示并写入审计。

因此，“服务端管理 Provider”指管理配置、验证、模型能力和授权策略；“节点可使用 Provider”不等于节点拥有服务端 Provider 数据库的密钥。

**为什么是 onedir 不是 onefile**：onefile 每次启动解压到临时目录，这个行为与 macOS Hardened Runtime 冲突，且在 Windows 上被杀软误报率极高（像加壳恶意软件）。onedir 目录结构可直接签名，启动也更快。

**sidecar 依赖裁剪**——以下**不进**节点包：`fastapi`、`uvicorn`、`celery`、`flower`、`redis`、`asyncpg`、`psycopg2-binary`、`alembic`、`boto3`、`msal`、`pytesseract`、`pymupdf`、`pillow`、`langfuse`、governance seeds。

裁剪不是优化，是必需：这些原生扩展跨平台打包是主要痛苦来源，且节点用不上。

## 4. 沙箱与隔离（macOS）

| 项 | 选型 |
|---|---|
| 机制 | Seatbelt，`sandbox-exec` + `.sbpl` 策略 |
| 路径 | **硬编码 `/usr/bin/sandbox-exec`**，不走 PATH 查找 |
| 策略生成 | 只存在于 macOS 实现模块内，不外泄到上层 |
| 上层抽象 | 平台无关声明：`sandbox_mode` + `writable_roots` + `network_access` |

二期平台（Windows 受限令牌+ACL，Linux bwrap+seccomp）在同一接口下新增实现模块，不触碰上层与服务端派单逻辑。

## 5. 共享内核：两层，不是一层

参照 pi 的四层划分（`pi-ai` / `pi-agent-core` / `pi-coding-agent` / `pi-tui`），共享代码拆成**两个包**而非一个：

| 包 | 职责 | 禁止依赖 |
|---|---|---|
| `packages/llm-router` | 纯多 Provider 抽象：`chat` / `stream_chat` / `embed`、重试退避、限流、能力探测、**模型元数据（上下文窗口 / 最大输出）** | 任何 agent 概念 |

**Provider 差异有四个维度**（参照 pi），缺一不可：消息结构、流式协议、**thinking / reasoning 档位**、**cache control**。现有实现只覆盖前两个。

- thinking 用统一枚举（`off` / `minimal` / `low` / `medium` / `high` / `xhigh`）+ 每模型映射表，翻译成各 Provider 的具体参数——"语义统一、实现分散"。
- cache control 对成本影响显著：skills 注入 system prompt 的那部分内容稳定，正是最适合缓存的。

新增模型 = 写一个符合统一签名的 translator + 注册 + 配元数据，**agent 循环零改动**。
| `packages/agent-core` | 循环 + 守卫 + 压缩 + 四个端口（`Store` / `VectorIndex` / `TaskQueue` / `Bus`） | `sqlalchemy`、`redis`、`celery`、`fastapi`、`app.*` |

**为什么拆开**：现有 `llm_router.py`（944 行）混了两类东西——纯路由能力，和 `parse_intent` / `generate_summary` / `build_chat_system_prompt` 这类**业务语义**方法。后者属产品层，桌面节点根本用不到。拆开后节点只依赖这两个包，不拖入服务端业务逻辑。

业务语义方法**留在 `app/`**，不进任何共享包。

两条 lint 规则强制，CI 阻断。

## 5.1 运行模式

参照 pi 的多模式设计，sidecar 支持两种入口：

| 模式 | 用途 |
|---|---|
| **RPC**（默认） | 由 Electron 壳驱动，JSONL over stdin/stdout |
| **headless / JSON** | 直接喂 stdin 输出 JSON，不启动 GUI |

**headless 不是可选项**——M2 的沙箱逃逸用例集用它跑比驱动 Electron GUI 容易一个数量级；将来的自动化响应剧本（告警触发 → 自动取证采集）与 CI 回归也依赖它。

成本极低：协议本就是 JSONL，headless 只是换一个不启动壳的入口。

## 6. 测试

| 层 | 工具 |
|---|---|
| Python | `pytest` + `pytest-asyncio`（基线测试集是重构安全网；当前本地收集 365 个用例） |
| TS 单元 | Vitest |
| 端到端 | Playwright（仓库已有 `.playwright-mcp` 使用痕迹） |
| 沙箱验证 | 独立的逃逸用例集，见 `03-ROADMAP.md` M2 出口判据 |

## 7. 仓库拓扑

**单仓库（monorepo）**，不拆新仓库。理由见 DEC-001。

```
uv workspace     → app/ + packages/llm-router/ + packages/agent-core/ + apps/desktop/sidecar/
npm workspaces   → webui/ + packages/ui-shared/ + apps/desktop/renderer/
```

**`packages/ui-shared` 不得依赖任何 agent 概念**（参照 pi-tui 对其余 pi 包零依赖）。它是纯展示层：组件、i18n、主题、API client 类型。业务状态由各自的应用层注入。

## 8. 明确不采用

| 技术 | 原因 |
|---|---|
| Tauri | 需 Rust 管 sidecar 与 MCP 子进程；系统 WebView 对 Tailwind v4 有兼容风险 |
| localhost HTTP 做壳↔sidecar 通信 | 同机任意进程可连；stdin/stdout 让该问题不存在 |
| 节点侧本地向量库（sqlite-vec / LanceDB / Chroma） | 经验共享是相对单机 CLI 工具的结构性优势，不下放 |
| PyInstaller onefile | 与 Hardened Runtime 冲突，杀软误报率高；统一使用 onedir |
| 节点间 LAN 发现 / P2P | 企业网内的横向移动通道，安全团队不会批 |
| 公网 artifact URL | 取证报告不得出网 |
| 新 ORM / 新 UI 框架 / 替换现有依赖 | 无收益，纯风险 |
| 扩展 / 技能热重载 | pi 支持改完立即生效不重启——对安全产品是**绕过审批的能力变更通道**，违反 INV-20 / INV-26 |
