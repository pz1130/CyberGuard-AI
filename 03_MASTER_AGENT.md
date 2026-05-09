# Master Agent - LangGraph 状态机详细定义

## 1. 状态（States）

定义在 `app/agents/states.py` 的 `AgentState` 枚举：

| 状态 | 说明 |
|------|------|
| START | 接收用户输入，初始化 request_id 和 session 元数据 |
| PARSE_INTENT | 调用 LLM Router 解析用户意图，生成 task_plan |
| ROUTE_TO_SUB | 根据 task_plan 决定路由目标（Sub-Agents / 群聊 / 直接输出） |
| WAIT_FOR_SUB_RESULTS | 并行执行 Sub-Agent 任务，等待全部返回 |
| GROUP_CHAT_MODE | 群聊主持模式（轮流让各 Sub-Agent 发言） |
| VALIDATE_RESULTS | 检查结果一致性，检测高危关键词触发审批 |
| SUMMARIZE | 生成最终结构化报告（含 risk_score 和 action_items） |
| HUMAN_APPROVAL | 高危操作等待人工审批（最长等待 1 小时） |
| END | 输出最终结果 |
| ERROR | 错误处理（任何节点抛出未处理异常） |

## 2. 节点（Nodes）

实现在 `app/agents/master.py` 的 `MasterAgent` 类：

| 节点 | 方法 | 说明 |
|------|------|------|
| start_node | `_start_node` | 初始化 state，分配 request_id |
| parse_intent_node | `_parse_intent_node` | LLM 解析 → task_plan；检测群聊触发关键词 |
| router_node | `_router_node` | 提取 pending_agents 列表 |
| sub_agent_executor_node | `_sub_agent_executor_node` | 并行调用远程/本地 Sub-Agent；记录 audit log |
| group_chat_moderator_node | `_group_chat_moderator_node` | 轮流让每个 Sub-Agent 对话题发言 |
| validation_node | `_validation_node` | 检查 failed status 和高危关键词 |
| summarizer_node | `_summarizer_node` | LLM 生成摘要；无 Sub-Agent 时直接作为对话 LLM |
| approval_node | `_approval_node` | 写 ApprovalRequest DB 记录；轮询等待 admin 决策 |
| error_node | `_error_node` | 设置 ERROR 状态 |

## 3. 边（Edges）与条件跳转

```
start_node → parse_intent_node → router_node
router_node → [条件]
  ├─ group_chat_active=true → group_chat_moderator_node → summarizer_node → END
  ├─ task_plan 为空         → summarizer_node → END（直接 LLM 对话）
  ├─ 任何 task 需要审批      → approval_node → END
  └─ 正常                   → sub_agent_executor_node
                                  → validation_node → [条件]
                                        ├─ validation_passed=true → summarizer_node → END
                                        └─ validation_passed=false → approval_node → END
error_node → END
```

## 4. 路由决策逻辑

`_route_decision(state)` 按以下优先级判断：
1. `group_chat_active == True` → `group_chat`
2. `task_plan` 为空 → `summarize_direct`（无需 Sub-Agent，直接 LLM 回复）
3. 任意 task 包含 `requires_approval=True` → `approval`
4. 其他 → `sub_agents`

## 5. Sub-Agent 执行策略

`_sub_agent_executor_node` 并行执行所有 task：
- 如果 task 有明确 `agent_id` → 调用 `AgentExecutor.execute(agent_id=...)`（远程 HTTP）
- 如果 task 的 `agent_type` 有已注册且带 `endpoint_url` 的 Agent → 远程执行
- 否则 → 本地 LLM 执行器（`LocalExecutor`）fallback

## 6. 状态持久化

- LangGraph `StateGraph.compile()` 编译为可执行 graph
- **未使用 LangGraph checkpoint**（无 MemorySaver / PostgresSaver）——每次请求是独立的无状态执行
- 会话历史通过 `conversations` 表单独持久化（`app/routers/conversations.py`）
- Human-in-the-Loop 状态通过 `approval_requests` DB 表持久化，支持跨进程等待

## 7. Master Agent 全局配置

通过 `app/routers/master_config.py` 和 `app/services/master_config.py` 管理，存储在 `master_agent_config` 表：

- `model`：使用的 LLM 模型名（默认 `gpt-4o`）
- `temperature`：生成温度（默认 0.7）
- `system_prompt`：全局系统提示词
- `intent_parser_prompt`：意图解析专属提示词（覆盖内置 prompt）
- `summarizer_prompt`：摘要生成专属提示词（覆盖内置 prompt）

这些配置可在 WebUI 的 **Settings** 页面（或 Master Agent Config 页面）实时调整，无需重启服务。单次对话也可通过 Chat API 的 `system_prompt_override`、`model_override`、`temperature_override` 字段进行临时覆盖。

## 8. 单例与初始化

```python
# app/agents/master.py
_master_agent = None

def get_master_agent() -> MasterAgent:
    global _master_agent
    if _master_agent is None:
        from app.services.llm_router import get_llm_router
        _master_agent = MasterAgent(llm_router=get_llm_router())
    return _master_agent
```

Master Agent 是进程级单例，LLM Router 也是单例，Provider 客户端通过 `_client_cache` 缓存。
