# Internal (Configurable) Sub-Agents — Design Spec

**Date:** 2026-05-28
**Status:** Approved for implementation planning
**Inspiration:** [agentscope-ai/QwenPaw](https://github.com/agentscope-ai/QwenPaw) — configurable sub-agents driven by prompt + tools rather than a separately-deployed process.

## Goal

Add a second **kind** of sub-agent — `internal` — that is configured entirely inside CyberGuard (prompt + LLM + skills + MCP + optional KB) and runs inline via the LLM Router. Existing sub-agents (OpenClaw / Hermes / Custom HTTP) become `kind=external`. The Master Agent, Chat, and Group Chat treat both kinds as equal participants.

Internal agents are additive — no existing functionality is removed or behaviour-changed.

## Terminology

| Kind | What it is | Runtime |
|---|---|---|
| `external` | Existing OpenClaw / Hermes / Custom HTTP agents — owned process, registered via WebUI | `SubAgentWrapper` (HTTP) or OpenClaw Gateway poll-and-pub/sub |
| `internal` | New. Configured entirely inside CyberGuard: `(system_prompt, llm_provider, skills[], mcp_tools[], kb?)` | New `InternalAgentRunner` — inline tool-call loop via LLM Router |

Both kinds:
- Live in the existing `agent_configs` table (single-table model, new `kind` column)
- Are routable by Master Agent (NL intent parser and explicit selector)
- Are valid group-chat participants
- Pick subsets from the shared **Skill pool** (`skills`) and **MCP pool** (`mcp_tools`)

The previously-existing `LocalAgentExecutor` (fallback in `app/services/local_executor.py`) is **not** replaced — it stays as the "no sub-agent matched" path for the Master Agent. Internal agents are a *configurable* alternative, not a fallback.

---

## 1. Schema changes

### 1.1 New Alembic migration `010_agent_kind_and_internal.py`

```python
# agent_configs
op.add_column("agent_configs", sa.Column("kind", sa.String(20),
                                          nullable=False, server_default="external"))
op.add_column("agent_configs", sa.Column("llm_provider_id", sa.Integer,
                                          sa.ForeignKey("providers.id"), nullable=True))
op.add_column("agent_configs", sa.Column("llm_model", sa.String(100), nullable=True))
op.add_column("agent_configs", sa.Column("tool_loop_max_steps", sa.Integer,
                                          nullable=False, server_default="8"))
op.add_column("agent_configs", sa.Column("memory_window", sa.Integer,
                                          nullable=False, server_default="20"))
op.add_column("agent_configs", sa.Column("knowledge_base_id", sa.Integer,
                                          sa.ForeignKey("knowledge_bases.id"), nullable=True))
op.create_index("ix_agent_configs_kind", "agent_configs", ["kind"])

# Backfill: every existing row was external by definition
op.execute("UPDATE agent_configs SET kind='external'")

# conversations — slice memory per internal agent
op.add_column("conversations", sa.Column("agent_id", sa.Integer,
                                          sa.ForeignKey("agent_configs.id"), nullable=True))
op.create_index("ix_conv_agent", "conversations", ["agent_id", "conversation_id"])
```

### 1.2 Field reuse for `kind=internal`

| Column | Used by internal? | Notes |
|---|---|---|
| `agent_name`, `description`, `system_prompt`, `is_active`, `permission_level` | yes | same semantics as external |
| `associated_skills` (JSON list of skill IDs) | yes | resolved into tool schemas for the loop |
| `metadata_json.mcp_tool_ids` | yes | resolved via existing `AgentExecutor.get_mcp_tools_for_agent()` |
| `llm_provider_id`, `llm_model` | **required** | which model the loop runs against |
| `tool_loop_max_steps`, `memory_window`, `knowledge_base_id` | optional | sensible defaults via `server_default` |
| `backend_type`, `endpoint_url`, `env_vars_encrypted`, `api_key_hash`, `openclaw_last_seen` | NULL | external-only fields |

### 1.3 Validation

DB does not enforce the kind/field matrix (cleaner error messages live in Python). Service-layer rules in `app/services/agent_service.py` (or wherever agent CRUD validates today):

- `kind=external` → must have `backend_type`; `openclaw` needs `api_key_hash`; `hermes`/`custom` needs `endpoint_url`.
- `kind=internal` → must have `llm_provider_id`; must NOT have `endpoint_url` or `backend_type`.

### 1.4 Per-agent memory model

- A `conversations` row with `agent_id IS NULL` = Master Agent conversation (existing behaviour — unchanged).
- A `conversations` row with `agent_id = X` = an internal-agent memory slice keyed off the parent conversation.
- Sliding window: the runner loads at most `memory_window` most-recent messages for that `(conversation_id, agent_id)` pair.
- External agents do **not** get a slice — they manage state themselves (existing behaviour).

---

## 2. Internal-agent runtime

### 2.1 New file `app/services/internal_agent.py` (~150 lines)

```python
class InternalAgentRunner:
    def __init__(self, config: dict):
        # config is the same dict shape AgentExecutor builds for SubAgentWrapper
        self.agent_id = config["id"]
        self.agent_name = config["agent_name"]
        self.system_prompt = config["system_prompt"] or ""
        self.llm_provider_id = config["llm_provider_id"]
        self.llm_model = config.get("llm_model")
        self.max_steps = config.get("tool_loop_max_steps", 8)
        self.memory_window = config.get("memory_window", 20)
        self.knowledge_base_id = config.get("knowledge_base_id")
        self.associated_skills = config.get("associated_skills") or []
        self.mcp_tool_ids = (config.get("metadata_json") or {}).get("mcp_tool_ids") or []

    async def execute(self, task: str, conversation_id: int | None,
                      user_id: int) -> dict:
        # Same return shape as SubAgentWrapper.execute():
        # {status, output, agent_id, agent_name, execution_time, tool_calls?, error?}
        ...
```

### 2.2 Loop (concrete steps)

1. **Load memory** — query `conversations` for `(conversation_id, agent_id)`, take last `memory_window` messages. Empty if `conversation_id is None` (one-shot dispatch from Master, no persisted slice).
2. **Build `tools[]`** — union of:
   - For each id in `associated_skills`: resolve `skills` row. The current `Skill` model has only `md_content` (markdown body) and `category` — **no `input_schema` column**. Two options for the implementation plan to choose between:
     - **(a)** Add a nullable `input_schema_json` column to `skills` via the same migration `010`. Skills without a schema are exposed as a single-arg tool `<skill.name>(input: str)` whose body is the markdown prompt prepended to the input. Skills with a schema get a structured tool.
     - **(b)** Treat every selected skill as a single-arg `<skill.name>(input: str)` tool unconditionally for v1. Defer structured-schema work.
     The spec recommends **(a)** — minimal extra cost, future-proof. The implementation plan will pick.
   - For each id in `mcp_tool_ids`: reuse the existing converter `AgentExecutor.get_mcp_tools_for_agent({"mcp_tool_ids": self.mcp_tool_ids})`. MCP tools already have `input_schema_json` (verified — see `app/models/mcp.py` use in `agent_executor.py:276`).
   - If `knowledge_base_id` is set: append a synthetic `kb_search(query: str, top_k: int = 5)` tool.
3. **Build `messages`** — `[{"role":"system","content":system_prompt}] + memory + [{"role":"user","content":task}]`.
4. **Loop** up to `max_steps`:
   ```
   resp = await llm_router.chat(messages, tools=tools,
                                 provider_id=llm_provider_id, model=llm_model)
   if not resp.tool_calls: break
   for call in resp.tool_calls:
       result = await dispatch(call)   # see 2.3
       messages.append({"role":"tool","tool_call_id":call.id,"content":result})
   messages.append(assistant_message_with_tool_calls)
   ```
5. **Persist** — append (user task, every assistant turn including intermediate ones, every tool result, final assistant text) to `conversations` with this agent's `agent_id`.
6. **Return** `{status: "completed", output: final_text, tool_calls: [summary list], agent_id, agent_name, execution_time}`. On loop exhaustion without a final non-tool response: `{status: "error", error: "exceeded tool_loop_max_steps"}`.

### 2.3 Tool dispatch `dispatch(tool_call)`

Single router in the same file:

```python
async def dispatch(self, call):
    name = call.function.name
    args = json.loads(call.function.arguments or "{}")

    # 1. Match against skill names (resolved at runner init)
    if name in self._skill_by_name:
        return await SkillLoader.invoke(self._skill_by_name[name], args)

    # 2. Match against MCP tool names
    if name in self._mcp_by_name:
        return await mcp_runner.invoke(self._mcp_by_name[name], args)

    # 3. KB synthetic tool
    if name == "kb_search" and self.knowledge_base_id:
        return await knowledge_service.search(self.knowledge_base_id,
                                               args["query"],
                                               args.get("top_k", 5))

    return f"ERROR: unknown tool '{name}'"
```

The actual MCP runner / skill executor functions already exist for use elsewhere (`AgentExecutor.get_mcp_tools_for_agent`, `SkillLoader`). The implementation plan must verify their invoke surfaces and add thin invoke helpers if missing.

### 2.4 Guardrails & RBAC

- Tool-call arguments pass through the existing `app/core/guardrails.py` prompt-injection screen before invocation, same as Master Agent today.
- `permission_level` is checked **before** the loop starts — `high` returns `needs_approval` without invoking the LLM, mirroring `AgentExecutor.execute()` line 343.
- Per-tool RBAC: same `Permission` enum from `app/core/rbac.py`. Skills/MCP tools already carry permission metadata; the dispatcher honours it.

### 2.5 Cost / observability

- OpenTelemetry spans wrap the loop (`internal_agent.execute`) and each `dispatch` call — keeps existing tracing coverage consistent.
- Token usage logged via the existing `token_usage_service` — provider_id is known per call so the existing path works unchanged.

---

## 3. Master + group chat + chat integration

### 3.1 `app/services/agent_executor.py`

Single new branch in `AgentExecutor.execute()`:

```python
if config_dict["kind"] == "internal":
    from app.services.internal_agent import InternalAgentRunner
    runner = InternalAgentRunner(config_dict)
    result = await runner.execute(
        task=task,
        conversation_id=context.get("conversation_id") if context else None,
        user_id=user_id,
    )
else:
    # existing branches: openclaw / hermes / custom — UNCHANGED
    ...
```

`AgentExecutor.execute()`'s signature gains an optional `context: dict | None = None` parameter so callers can pass `conversation_id`. Existing callers stay source-compatible (default None → no memory persistence, treated as one-shot).

### 3.2 Master Agent (`app/agents/master.py`)

No behavioural changes needed. The LLM intent parser already calls `AgentExecutor.execute(agent_id, task, user_id)` after picking an agent from the active list. Add `context={"conversation_id": state.conversation_id}` to the call site so internal agents get their memory slice.

The agent list injected into the Master system prompt (`llm_router._get_agents_info`) lists every active row regardless of kind — no change.

### 3.3 Group chat (`app/services/group_chat.py`)

Single change: thread `conversation_id` through `GroupChatSession` (it already has `session_id`; add `parent_conversation_id: int | None`) and pass it as `context={"conversation_id": ...}` to each `AgentExecutor.execute()` call. Both kinds participate equally; round-robin and result aggregation logic stays intact.

### 3.4 Chat (`/api/v1/chat/*`)

Both the natural-language path (LLM intent parser → `agent_name`) and the explicit-selector path (`agent_id` on the chat body) already route through `AgentExecutor.execute()`. Once 3.1 is in place, chat supports internal agents with zero changes to chat handlers.

### 3.5 Expert mode fan-out

`execute_parallel(agent_ids, task, user_id)` (agent_executor.py:456) — gains the optional `context` param and forwards it to `execute()`. Internal agents in fan-out share the parent conversation_id but each writes its own slice.

---

## 4. WebUI changes

`webui/src/pages/Agents.tsx` (and friends):

- **Kind** column with coloured badge (`internal` / `external`)
- **Kind** filter dropdown above the list
- **New Agent** button → modal with first step "Choose kind" → routes to existing external form OR new internal form
- **New internal-agent form fields:**
  - name, description, system_prompt
  - llm_provider (dropdown of active providers from existing `/api/v1/providers`)
  - llm_model (free text or autocomplete; existing convention)
  - knowledge_base (optional dropdown of active KBs)
  - tool_loop_max_steps (default 8), memory_window (default 20)
  - permission_level (low/medium/high)
  - associated_skills (multi-select from skill pool)
  - mcp_tool_ids (multi-select from MCP pool)
- **Group-chat agent-picker:** both kinds in the same multi-select, kind badge visible

No new pages. No tab split. Single roster, single filter.

API CRUD (`/api/v1/agents`) — same endpoints; the create/update handlers branch on `kind` for field validation. Response shape gains the new fields (additive, backward-compatible for any external API client).

---

## 5. Migration & rollout

1. Alembic `010_agent_kind_and_internal.py` runs on startup. Dev mode auto-applies; production deploys run it as part of the existing migration flow.
2. Existing agents auto-labelled `kind='external'` via the `UPDATE` in the migration — no operator action required.
3. **Optional seed:** behind env flag `SEED_EXAMPLE_INTERNAL_AGENTS` (default `false`), startup seeds two example internal agents idempotently so users see the feature:
   - `triage_analyst` — general SOC triage, picks from default skills
   - `policy_writer` — governance copilot bound to the ISO 27001 knowledge base
4. No API surface breaks. Existing `/api/v1/agents/*` endpoints validate the new `kind` field; absent → defaults to `external` for backward compat.

---

## 6. Out of scope (explicit YAGNI)

- **Streaming** for internal agents — parity with current external agents. Add later if needed; the loop is the place to wire it.
- **Long-term memory** beyond the conversation slice — user picked the conversations-table option (architecture_facts memory #4 confirms LangGraph has no persistence, so this is the established pattern).
- **Multi-LLM-per-agent** — one provider per internal agent. Per-call routing can be layered later by reading from `metadata_json`.
- **New permissions model** — reuses `permission_level` and `app/core/rbac.Permission`.
- **Webhook events for internal-agent lifecycle** — existing webhook event set is untouched.
- **Agent-to-agent direct calls** (an internal agent invoking another internal agent as a tool) — possible future extension; not in this spec.

---

## 7. Files touched (estimate)

**New:**
- `alembic/versions/010_agent_kind_and_internal.py`
- `app/services/internal_agent.py`
- WebUI: new internal-agent form component + kind chooser modal

**Modified:**
- `app/models/agent.py` (new columns)
- `app/models/conversation.py` (new `agent_id` column)
- `app/services/agent_executor.py` (kind branch + `context` param threading)
- `app/services/group_chat.py` (parent_conversation_id threading)
- `app/agents/master.py` (single line: pass `context={"conversation_id": ...}`)
- `app/routers/agents.py` (validation branching on kind, response shape)
- `webui/src/pages/Agents.tsx` (kind column + filter + chooser + new form)
- `webui/src/api/agents.ts` (new fields in types)

**Untouched:**
- `app/services/local_executor.py` — fallback path unchanged
- `app/services/openclaw_executor.py`, all external-agent code paths
- Webhook, guardrails, RBAC, KB, governance, prompt-templates code

## 8. Risks & open questions

- **Skills have no `input_schema` column today** — see section 2.2 step 2. Resolution decided at implementation-plan time: either add the column (recommended) or treat skills as single-arg tools for v1.
- **MCP tool name collisions with skill names** — `dispatch()` resolves in skill-first order. If both pools contain the same name, the skill wins. Document this in the form ("MCP tools with the same name as a selected skill are shadowed").
- **`kb_search` synthetic tool name collision** — reserve the name; reject skill/MCP imports that try to use it.

