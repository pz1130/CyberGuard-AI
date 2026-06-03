# Chat 模型下拉:仅显示已验证模型

**Status:** draft
**Date:** 2026-06-03
**Scope:** `webui/src/pages/Chat.tsx` + `app/schemas/provider.py` + `app/routers/providers.py` + `app/main.py`(preset 种子)

---

## 1. 背景与问题

`webui/src/pages/Chat.tsx` 的"模型"下拉现在显示两类东西:

1. `FALLBACK_MODELS` 常量(`OPENAI/gpt-4o`、`ANTHROPIC/claude-sonnet-4-7-2025`、`GROK/grok-3`)— 这些是**硬编码的占位**(`provider_id: 0` 永远不对应到真实 provider),被当作 `useState` 初值塞进去,接口返回前就显示,接口返回后只在 `models.length > 0` 时才被覆盖。
2. 真实 provider 的 `models` 列表 — `for p in providers: for m in p.models: push({...})`,不过滤任何"已验证"状态。

用户反馈:"我选择模型的时候,只要看见已经验证过的模型,不要把默认的模型都放上去"。

**关键事实:** 系统目前**没有"已验证"这个概念**。`ProviderTestResponse` 返回 `success / latency / error`,但调用后**不写库**;`ModelInfo` schema 里也没有 `verified` 字段。`provider.is_active` 是当前最接近的概念,但它表示"该 provider 是否启用",不是"该 model 是否测试通过"。

## 2. 目标

- 模型下拉只显示**真正测试通过**的 model。
- `provider_id: 0` 的硬编码 fallback 必须删掉(它本来就不该出现在下拉里)。
- 用户在 Providers 页面点过"测试"且返回 `success=true` 的 model → 立刻出现在 Chat 下拉里。
- 测试失败、或从未测试过的 model → 不出现在 Chat 下拉。
- 内置 preset(Gemini/Kimi/MiniMax/DeepSeek/xAI/LM Studio 等手测过的 model)→ 冷启动就 mark `verified=true`,下拉不会瞬间空。

## 3. 方案

**per-model 验证状态写在 `models` JSON 字典里** — 复用 `ModelInfo` 的 `JSON` 列,新字段全部 optional,无迁移。

### 3.1 schema 变更(`app/schemas/provider.py`)

`ModelInfo` 增加三个 optional 字段:

```python
class ModelInfo(BaseModel):
    name: str
    model_type: Literal["chat", "embedding", "rerank"] = "chat"
    capabilities: Optional[Dict[str, Any]] = None
    # New — all optional, written by /providers/test and /models/probe
    verified: Optional[bool] = None            # None=never tested, True/False=test result
    last_tested_at: Optional[datetime] = None  # UTC, set on every test
    test_error: Optional[str] = None           # truncated error string on failure
```

`ProviderResponse` 不动 — 它已经透传 `models` 整个 JSON 列表,新字段会自然出现在 API 返回里。

### 3.2 后端写库逻辑(`app/routers/providers.py`)

`_test_provider_connectivity` 已经被 `POST /providers/test` 和 `POST /providers/{id}/models/probe` 共用。在它返回响应前,**不直接动它**(返回路径保持纯函数),而是在**调用方**写库:

**`POST /providers/{id}/models/probe`**(`probe_single_model`,在文件第 ~580 行附近):已经是 per-model 路径 — 拿到测试结果后:

```python
async def _stamp_model_verified(provider: Provider, model_name: str, ok: bool, err: Optional[str]):
    """Update verified/last_tested_at/test_error on a specific model dict in provider.models."""
    models = list(provider.models or [])
    for m in models:
        if isinstance(m, dict) and m.get("name") == model_name:
            m["verified"] = ok
            m["last_tested_at"] = datetime.utcnow().isoformat()
            m["test_error"] = (err or "")[:200] if not ok else None
            break
    else:
        # Model not in provider.models yet (e.g. freshly discovered) — append a stub
        models.append({
            "name": model_name,
            "model_type": "chat",
            "verified": ok,
            "last_tested_at": datetime.utcnow().isoformat(),
            "test_error": (err or "")[:200] if not ok else None,
        })
    provider.models = models
    await db.commit()
```

`POST /providers/test`(provider 级,只测一个 model — 第一个或显式 `test_model`):拿到结果后,用同样的 `_stamp_model_verified(provider, model_name, success, error)` 写库;不写 verified=undefined。

### 3.3 preset 种子(`app/main.py` / `app/routers/providers.py` 的 `_seed_presets`)

`_seed_presets` 在创建内置 preset 时,把每个 model dict 加 `verified: True`、`last_tested_at: <seed_time>`(无 `test_error`)。这是"我手测过"的事实声明。

新加的内置 preset(MiniMax/Gemini/DeepSeek/Kimi/xAI/LM Studio)的 model 列表在 `_seed_presets` 顶部定义 → 全部加 verified=True。已有内置 preset(OpenAI/Anthropic 等)如果 model 列表被列出,同样标。

**关键约束:幂等** — `_seed_presets` 已经在用"per-preset commit + IntegrityError 回滚"防多 worker 竞态。`verified=True` 的赋值要放在 commit 之前,这样不会重复 seed。

### 3.4 前端过滤(`webui/src/pages/Chat.tsx`)

**删除 `FALLBACK_MODELS` 常量**(行 68-72)和 `useState<ProviderModel[]>(FALLBACK_MODELS)` 初值(行 110)→ 改成 `useState<ProviderModel[]>([])`。

`loadModels` 过滤逻辑改成:

```ts
for (const m of (p.models || [])) {
  const verified = (typeof m === 'object' && m !== null) ? (m as any).verified : undefined
  if (verified !== true) continue        // 核心:不是 true 就跳过
  models.push({ ... })
}
```

**UI 提示:** 初次打开 Chat 时,如果 `availableModels.length === 0`,在 `MODEL` 下拉旁边显示一个 tooltip "尚未验证任何模型 — 请到 Providers 页面点测试",小字、灰色。

**可选项(本期不做,留作后续):** localStorage 开关 `chat.showUnverifiedModels` 临时显示未验证 model — YAGNI,先不做。

### 3.5 Providers 页面 UX(`webui/src/pages/Providers.tsx`)

每个 model 旁加状态徽章(基于 `verified`):

| `verified`  | 徽章                       | 颜色        |
|-------------|----------------------------|-------------|
| `undefined` | `· UNTESTED`               | 灰          |
| `true`      | `✓ VERIFIED`               | 绿(var(--accent)) |
| `false`     | `✗ FAILED` (hover 显示 err)| 红          |

"测一下" 按钮(每行末尾,以及顶部"探测能力"按钮)— 已存在,只需在 `probe()` / `test()` 调用后**刷新列表**(目前调用 `loadProviders` 重新拉,会自动带新 verified 状态)。

## 4. 数据流

```
用户在 Providers 页面点 "测一下 model X"
  → POST /providers/{id}/models/probe {model: "X"}
    → _test_provider_connectivity(...)
    → probe response (success, latency, error)
  → _stamp_model_verified(provider, "X", success, error)
    → 写回 provider.models 中 name=="X" 的 dict
    → db.commit()
  → 返回 response 给前端
    → 前端 reload providers list
      → 列表里 X 旁边显示 ✓ VERIFIED
      → 下次切到 Chat 页面,loadModels 看到 X.verified===true,出现在下拉
```

## 5. 边界 / 错误处理

- **冷启动,所有 model 都未验证:** Chat 下拉空 + 灰色提示文字,引导到 Providers。这是设计预期(强一致),不是 bug。
- **测试接口 5xx:** `_stamp_model_verified(..., ok=False, err=...)` 仍然写库,用户能看到 ✗ FAILED。
- **probe 探到 capability 但 connectivity 失败:** `verified=false`,`capabilities` 保留(因为 prober 自己写过)。
- **model 名字包含冒号(在 Chat 解析 `provider_id:model` 时有 bug):** 不在本期范围 — 历史问题,和验证逻辑无关。
- **`models` 字段是历史纯字符串数组 `["gpt-4o"]`:** schema 的 `convert_legacy_models` 已经把它们转成 `[{name, model_type}]`,但 `verified` 会是 undefined → 不出现在下拉,符合预期。如果用户想让历史 provider 立即出现,得在 Providers 页面测一下 — 这是 design 接受的代价(强一致 > 沉默失败)。

## 6. 涉及文件

- `app/schemas/provider.py` — `ModelInfo` 加 3 字段
- `app/routers/providers.py` — 新增 `_stamp_model_verified`,在 `test_provider_connection` 和 `probe_single_model` 末尾调用
- `app/main.py` / `app/routers/providers.py` 的 `_seed_presets` — preset model dict 加 `verified: True`
- `webui/src/pages/Chat.tsx` — 删 `FALLBACK_MODELS`、改 `useState` 初值、改 `loadModels` 过滤、加空状态提示
- `webui/src/pages/Providers.tsx` — model 行加状态徽章
- `webui/src/api/client.ts` — `ProviderModel` interface 加 `verified?` 等字段

## 7. 测试

- 后端:`tests/test_providers.py` 加:
  - 测一次成功 → `provider.models[i].verified === true`
  - 测一次失败 → `verified === false`、`test_error` 非空
  - 测一个新 model(不在 provider.models 里)→ 被 append 进列表
  - preset 种子创建后 → `verified === true`、`last_tested_at` 非空
- 前端:手动跑 chat 流程,验证空状态提示 & 测过的 model 出现。

## 8. 范围外(YAGNI)

- ❌ 自动定期重测所有 model
- ❌ "信任此 model 永不过期"开关
- ❌ localStorage 强制显示未验证 model
- ❌ Chat 页内直接发起测试(必须去 Providers 测)
- ❌ 区分"手动测过" vs "probe 探过"的徽章(都算 verified)
