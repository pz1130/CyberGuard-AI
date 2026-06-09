"""Internal (in-app, configurable) sub-agent runner.

Runs an inline tool-call loop against the LLM Router. See:
  docs/superpowers/specs/2026-05-28-internal-agents-design.md
"""
import asyncio
import json
import logging
import time
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.services.llm_router import get_llm_router
from app.services.tool_executor import execute_tool


# --- Tunables (aligned with QwenPaw's ReActAgent behaviours) ---------------
# Truncate oversized tool outputs so a single noisy tool can't blow the
# context window (cf. QwenPaw LightContextManager._prune_tool_result).
TOOL_RESULT_MAX_CHARS = 8000
# When the model answers with text but never used a tool, nudge it to either
# call a tool or confirm completion — bounded to avoid loops / runaway cost
# (cf. QwenPaw _auto_continue_if_text_only).
AUTO_CONTINUE_MAX = 2
# Compact older history once the running message buffer exceeds this size
# (~6k tokens at ~4 chars/token), keeping the most recent turns verbatim
# (cf. QwenPaw _compact_context / context_compact_threshold).
CONTEXT_COMPACT_CHARS = 24000
CONTEXT_KEEP_RECENT = 6

# --- Reflector / loop guard (cf. PentAGI Reflector + execution monitoring) --
# Same (tool name + normalized args) seen this many times across steps ==
# the agent is stuck repeating itself instead of making progress.
LOOP_DETECT_THRESHOLD = 3
# How many reflector interventions to allow before aborting a stuck loop.
REFLECT_MAX = 2
# Bounded self-recovery on transient LLM failures before failing the turn.
LLM_RETRY_MAX = 2
LLM_RETRY_BACKOFF = 0.5  # base seconds between retries (linear backoff)

# Hard cap on total tool executions per run, preventing runaway operations
# (cf. PentAGI: 100 for general agents, 20 for limited ones). Once spent, the
# agent is forced to answer from what it already has rather than erroring out.
TOOL_CALL_BUDGET_DEFAULT = 100
TOOL_CALL_BUDGET_LIMITED = 20

# Injected as a user nudge when a loop is detected, to break the rut.
REFLECT_GUIDANCE = (
    "你似乎在重复同一个操作且没有进展。请停下来反思：要么换一种"
    "完全不同的方法或参数，要么基于已有信息直接给出最终答复。"
)


# ---------------------------------------------------------------------------
# KnowledgeService adapter — exposes search(kb_id, query, top_k) as an
# awaitable without requiring a caller-supplied db session.
# Mockable from tests via:
#   monkeypatch.setattr("app.services.internal_agent.knowledge_service", FakeKB())
# ---------------------------------------------------------------------------
class _KSAdapter:
    """Thin adapter so dispatch can call knowledge_service.search(kb_id, query, top_k)."""

    async def search(self, kb_id: int, query: str, top_k: int = 5):
        from app.services.knowledge_service import get_knowledge_service
        svc = get_knowledge_service()
        async with AsyncSessionLocal() as db:
            return await svc.query(db=db, kb_id=kb_id, query=query, top_k=top_k)


knowledge_service = _KSAdapter()


# ---------------------------------------------------------------------------
# SearchService adapter — exposes web_search/vuln_search returning JSON-safe
# dicts. Mockable from tests via:
#   monkeypatch.setattr("app.services.internal_agent.search_service", FakeSearch())
# ---------------------------------------------------------------------------
class _SearchAdapter:
    async def web_search(self, query: str, limit: int = 5):
        from app.services.search_service import get_search_service
        return [r.to_dict() for r in await get_search_service().web_search(query, limit)]

    async def vuln_search(self, query: str, limit: int = 5):
        from app.services.search_service import get_search_service
        return [r.to_dict() for r in await get_search_service().vuln_search(query, limit)]


search_service = _SearchAdapter()


# ---------------------------------------------------------------------------
# EpisodicMemory adapter — recall/record over the agent_episodes store, opening
# its own DB session. Mockable from tests via:
#   monkeypatch.setattr("app.services.internal_agent.episodic_memory", Fake())
# ---------------------------------------------------------------------------
class _EpisodicAdapter:
    async def recall(self, agent_id: int, task: str, top_k: int = 3,
                     provider_id: Optional[int] = None):
        from app.services.episodic_memory import get_episodic_memory_service
        svc = get_episodic_memory_service()
        async with AsyncSessionLocal() as db:
            return await svc.recall(db, agent_id=agent_id, task=task,
                                    top_k=top_k, provider_id=provider_id)

    async def record(self, agent_id: int, task: str, approach: str, outcome: str,
                     success: bool = True, tool_count: int = 0,
                     embedding=None, provider_id: Optional[int] = None):
        from app.services.episodic_memory import get_episodic_memory_service
        svc = get_episodic_memory_service()
        async with AsyncSessionLocal() as db:
            await svc.record(db, agent_id=agent_id, task=task, approach=approach,
                             outcome=outcome, success=success, tool_count=tool_count,
                             embedding=embedding, provider_id=provider_id)


episodic_memory = _EpisodicAdapter()


class InternalAgentRunner:
    def __init__(self, config: Dict[str, Any]):
        self.agent_id: int = config["id"]
        self.agent_name: str = config["agent_name"]
        self.system_prompt: str = config.get("system_prompt") or ""
        self.llm_provider_id: Optional[int] = config.get("llm_provider_id")
        self.llm_model: Optional[str] = config.get("llm_model")
        self.max_steps: int = config.get("tool_loop_max_steps") or 8
        self.memory_window: int = config.get("memory_window") or 20
        self.knowledge_base_id: Optional[int] = config.get("knowledge_base_id")
        self.associated_skills: List[int] = config.get("associated_skills") or []
        meta = config.get("metadata_json") or {}
        self.mcp_tool_ids: List[int] = config.get("associated_mcp_tools") or meta.get("mcp_tool_ids") or []
        self.pool_tool_ids: List[int] = config.get("associated_tools") or meta.get("tool_ids") or []
        self.permission_level: str = config.get("permission_level") or "medium"
        # OSINT search tools (web_search / vuln_search) opt-in per agent.
        self.enable_search: bool = bool(
            config.get("enable_search") or meta.get("enable_search"))
        # Episodic memory (recall past successes / record this run) opt-in.
        self.enable_episodic: bool = bool(
            config.get("enable_episodic") or meta.get("enable_episodic"))
        self._episode_embedding = None    # reused between recall and record
        # Hard per-run tool-call cap: explicit override, else by permission tier.
        self.tool_call_budget: int = config.get("tool_call_budget") or (
            TOOL_CALL_BUDGET_LIMITED if self.permission_level == "low"
            else TOOL_CALL_BUDGET_DEFAULT
        )
        _gov = meta.get("governance") or {}
        # Prefer first-class governance columns (Plan 2); fall back to metadata_json.
        self._governance_cfg = {
            "autonomy_tier": config.get("autonomy_tier") or _gov.get("autonomy_tier", "L2"),
            "allowed_categories": config.get("allowed_categories") or _gov.get("allowed_categories"),
            "escalate_to_human_below": config.get("escalate_to_human_below") or _gov.get("escalate_to_human_below", 0.60),
            "is_poc": config.get("is_poc") if config.get("is_poc") is not None else _gov.get("is_poc", True),
            "agent_name": config.get("agent_name"),
        }
        self._pii_policy: Optional[str] = config.get("pii_handling_policy")

    # -------- Memory --------

    async def _get_or_create_slice_row(
        self, session, parent_conversation_id: int, user_id: int
    ) -> Conversation:
        result = await session.execute(
            select(Conversation).where(
                Conversation.parent_conversation_id == parent_conversation_id,
                Conversation.agent_id == self.agent_id,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row
        row = Conversation(
            user_id=user_id,
            title=f"agent:{self.agent_name}",
            parent_conversation_id=parent_conversation_id,
            agent_id=self.agent_id,
            messages_json="[]",
        )
        session.add(row)
        await session.flush()
        return row

    async def _load_memory(self, parent_conversation_id: Optional[int]) -> List[Dict[str, str]]:
        if parent_conversation_id is None:
            return []
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Conversation).where(
                    Conversation.parent_conversation_id == parent_conversation_id,
                    Conversation.agent_id == self.agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row or not row.messages_json:
                return []
            try:
                msgs = json.loads(row.messages_json) or []
            except json.JSONDecodeError:
                return []
            return msgs[-self.memory_window:]

    async def _append_memory(
        self, parent_conversation_id: Optional[int], user_id: int,
        messages: List[Dict[str, str]],
    ) -> None:
        if parent_conversation_id is None or not messages:
            return
        async with AsyncSessionLocal() as s:
            row = await self._get_or_create_slice_row(s, parent_conversation_id, user_id)
            existing = json.loads(row.messages_json or "[]")
            existing.extend(messages)
            row.messages_json = json.dumps(existing, ensure_ascii=False)
            await s.commit()

    # -------- System prompt assembly --------

    async def _load_skill_bodies(self, skill_ids: List[int]) -> Dict[int, str]:
        if not skill_ids:
            return {}
        from app.models.skill import Skill
        async with AsyncSessionLocal() as s:
            result = await s.execute(select(Skill).where(Skill.id.in_(skill_ids),
                                                          Skill.is_active.is_(True)))
            rows = result.scalars().all()
        return {r.id: (r.md_content or "") for r in rows}

    async def _build_system_prompt(self, task: Optional[str] = None) -> str:
        parts = [self.system_prompt] if self.system_prompt else []
        bodies = await self._load_skill_bodies(self.associated_skills)
        if bodies:
            parts.append("\n\n## Skills available to you\n")
            for sid in self.associated_skills:
                body = bodies.get(sid)
                if body:
                    parts.append(f"\n### Skill #{sid}\n{body}\n")

        if self.enable_episodic and task:
            try:
                episodes, emb = await episodic_memory.recall(
                    self.agent_id, task, provider_id=self.llm_provider_id)
                self._episode_embedding = emb
                if episodes:
                    parts.append("\n\n## 过往成功经验（参考）\n")
                    for ep in episodes:
                        parts.append(
                            f"- 任务：{ep.get('task','')}\n"
                            f"  方法：{ep.get('approach','')}\n"
                            f"  结果：{ep.get('outcome','')}\n")
            except Exception as e:           # noqa: BLE001 - never break the run
                logger.debug("episodic recall failed: %s", e)

        return "\n".join(parts).strip() or "You are an assistant."

    # -------- Tool catalog --------

    async def _load_mcp_tools(self) -> List[Dict[str, Any]]:
        """Resolve mcp_tool_ids into OpenAI function-tool schemas."""
        if not self.mcp_tool_ids:
            return []
        from app.models.mcp import MCPTool
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(MCPTool).where(MCPTool.id.in_(self.mcp_tool_ids),
                                       MCPTool.is_active.is_(True))
            )
            tools = result.scalars().all()
        out = []
        for t in tools:
            try:
                schema = json.loads(t.input_schema_json) if t.input_schema_json else {}
            except json.JSONDecodeError:
                schema = {}
            if not isinstance(schema, dict):
                schema = {}
            out.append({
                "type": "function",
                "function": {
                    "name": t.tool_name,
                    "description": t.description or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                },
            })
        return out

    async def _load_pool_tools(self):
        """Load executable Tool-pool rows referenced by metadata_json.tool_ids."""
        if not self.pool_tool_ids:
            return []
        from app.models.skill import Tool
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Tool).where(Tool.id.in_(self.pool_tool_ids),
                                   Tool.is_active.is_(True),
                                   Tool.command_template.isnot(None))
            )
            return list(result.scalars().all())

    async def _build_tools(self) -> List[Dict[str, Any]]:
        self._pool_tools_by_name: Dict[str, Any] = {}
        tools = await self._load_mcp_tools()

        # Append executable pool Tools (MCP names win on collision)
        mcp_names = {t["function"]["name"] for t in tools}
        for pt in await self._load_pool_tools():
            if pt.name in mcp_names:
                logger.warning("pool Tool %r skipped: name collides with an MCP tool", pt.name)
                continue  # MCP name wins; skip colliding pool tool
            try:
                schema = json.loads(pt.input_schema_json) if pt.input_schema_json else {}
            except json.JSONDecodeError:
                schema = {}
            if not isinstance(schema, dict):
                schema = {}
            self._pool_tools_by_name[pt.name] = pt
            tools.append({
                "type": "function",
                "function": {
                    "name": pt.name,
                    "description": pt.description or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                },
            })

        if self.knowledge_base_id:
            tools.append({
                "type": "function",
                "function": {
                    "name": "kb_search",
                    "description": "Search the agent's attached knowledge base.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "search query"},
                            "top_k": {"type": "integer", "default": 5,
                                       "description": "max number of chunks to return"},
                        },
                        "required": ["query"],
                    },
                },
            })

        if self.enable_search:
            for tname, desc in (
                ("web_search", "Search the public web for general OSINT / recon."),
                ("vuln_search", "Search exploit/vulnerability databases (Sploitus) "
                                "for a CVE, product, or keyword."),
            ):
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tname,
                        "description": desc,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "search query"},
                                "limit": {"type": "integer", "default": 5,
                                           "description": "max number of results"},
                            },
                            "required": ["query"],
                        },
                    },
                })
        return tools

    # -------- Tool dispatch --------

    async def _dispatch(self, call) -> str:
        """Execute a single tool_call and return a JSON-safe string result."""
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}

        # 1. MCP tool lookup
        if hasattr(self, "_mcp_by_name") and name in self._mcp_by_name:
            from app.services.mcp_executor import execute_mcp_tool
            tool_row, server_row = self._mcp_by_name[name]
            try:
                result = await execute_mcp_tool(server_row, tool_row.tool_name, args)
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception as e:
                return f"ERROR: MCP tool {name!r} failed: {e}"

        # 2. KB synthetic tool
        if name == "kb_search" and self.knowledge_base_id:
            try:
                chunks = await knowledge_service.search(
                    self.knowledge_base_id,
                    args.get("query", ""),
                    args.get("top_k", 5),
                )
                return json.dumps(chunks, ensure_ascii=False, default=str)
            except Exception as e:
                return f"ERROR: kb_search failed: {e}"

        # 3. Search synthetic tools (OSINT web / vuln recon)
        if name in ("web_search", "vuln_search") and self.enable_search:
            try:
                fn = getattr(search_service, name)
                results = await fn(args.get("query", ""), args.get("limit", 5))
                return json.dumps(results, ensure_ascii=False, default=str)
            except Exception as e:
                return f"ERROR: {name} failed: {e}"

        # 4. Executable pool Tool
        if getattr(self, "_pool_tools_by_name", None) and name in self._pool_tools_by_name:
            tool_row = self._pool_tools_by_name[name]
            from app.services.governance_config import load_governance
            governance = load_governance(self._governance_cfg) if self._governance_cfg else None
            res = await execute_tool(tool_row, args, user_id=getattr(self, "_user_id", 0),
                                     governance=governance, confidence=None)
            if res.get("status") == "completed":
                return res.get("stdout", "") or "(no output)"
            if res.get("status") == "needs_approval":
                return (f"NEEDS_APPROVAL: tool {name!r} is high-permission; "
                        f"an approval request was created for a human to review.")
            return f"ERROR: tool {name!r}: {res.get('error') or res.get('stderr') or res}"

        return f"ERROR: unknown tool {name!r}"

    async def _resolve_mcp_lookup(self) -> None:
        """Populate self._mcp_by_name = {tool_name: (MCPTool, MCPServer)} for dispatch."""
        self._mcp_by_name = {}
        if not self.mcp_tool_ids:
            return
        from app.models.mcp import MCPTool, MCPServer
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(MCPTool, MCPServer)
                .join(MCPServer, MCPServer.id == MCPTool.server_id)
                .where(MCPTool.id.in_(self.mcp_tool_ids), MCPTool.is_active.is_(True))
            )
            for tool, server in result.all():
                self._mcp_by_name[tool.tool_name] = (tool, server)

    # -------- Tool-result pruning + context compaction --------

    @staticmethod
    def _fingerprint(name: str, arguments: str) -> str:
        """Stable identity for a tool call: name + order-invariant arguments.

        Two calls with the same name and semantically equal arguments (regardless
        of JSON key order) share a fingerprint, so the loop guard can count
        genuine repeats. Unparseable arguments fall back to the raw string.
        """
        try:
            norm = json.dumps(json.loads(arguments or "{}"), sort_keys=True,
                              ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            norm = arguments or ""
        return f"{name}::{norm}"

    @staticmethod
    def _loop_notice(name: str, count: int) -> str:
        return (f"LOOP_DETECTED: 你已用相同参数调用 {name} {count} 次，结果不会改变。"
                f"请改用其他工具或参数，或直接给出最终答复。")

    @staticmethod
    def _budget_notice(budget: int) -> str:
        return (f"BUDGET_EXHAUSTED: 已达到工具调用上限（{budget} 次），"
                f"该调用未执行。请基于已有信息给出最终答复。")

    @staticmethod
    def _truncate_tool_result(text: str) -> str:
        """Cap a single tool result so noisy tools can't blow the context."""
        if text is None:
            return ""
        if len(text) <= TOOL_RESULT_MAX_CHARS:
            return text
        dropped = len(text) - TOOL_RESULT_MAX_CHARS
        return text[:TOOL_RESULT_MAX_CHARS] + f"\n…[truncated {dropped} chars]"

    @staticmethod
    def _estimate_chars(messages: List[Dict[str, Any]]) -> int:
        total = 0
        for m in messages:
            total += len(str(m.get("content") or ""))
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                total += len(str(fn.get("arguments") or "")) + len(str(fn.get("name") or ""))
        return total

    @staticmethod
    def _messages_to_text(messages: List[Dict[str, Any]]) -> str:
        lines = []
        for m in messages:
            role = m.get("role", "?")
            content = str(m.get("content") or "")
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                content += f" [tool_call {fn.get('name')}({fn.get('arguments')})]"
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _maybe_compact(self, messages: List[Dict[str, Any]], router) -> List[Dict[str, Any]]:
        """Summarise older messages when the buffer grows too large.

        Keeps the leading system message and the last CONTEXT_KEEP_RECENT
        messages verbatim; replaces the middle with an LLM-produced summary.
        On any failure falls back to simply dropping the middle.
        """
        if self._estimate_chars(messages) <= CONTEXT_COMPACT_CHARS:
            return messages
        if len(messages) <= CONTEXT_KEEP_RECENT + 2:
            return messages  # too few to bother

        system = messages[0]
        recent = messages[-CONTEXT_KEEP_RECENT:]
        # A 'tool' message must follow its assistant tool_calls; if the recent
        # window starts mid tool-exchange, drop the orphaned leading tool msgs.
        while recent and recent[0].get("role") == "tool":
            recent = recent[1:]
        middle = messages[1:len(messages) - len(recent)]
        if not middle:
            return messages

        summary_prompt = [
            {"role": "system", "content":
                "You compress conversation history for an AI agent. Produce a concise "
                "summary that preserves facts, user intent, decisions, and key tool "
                "results. Use markdown with ## section headers."},
            {"role": "user", "content":
                "Summarize the conversation so far:\n\n" + self._messages_to_text(middle)},
        ]
        try:
            summary = await router.chat(
                messages=summary_prompt,
                provider_id=self.llm_provider_id,
                model=self.llm_model,
                tools=None,
                pii_policy=self._pii_policy,
            )
            if not isinstance(summary, str):
                summary = getattr(summary, "content", None) or ""
            summary = summary.strip()
            if not summary:
                raise ValueError("empty summary")
            digest = {"role": "system",
                      "content": "## 对话摘要（早期消息已压缩）\n" + summary}
            return [system, digest] + recent
        except Exception:
            # Fallback: drop the middle entirely rather than fail the turn.
            return [system] + recent

    # -------- Public entry point --------

    async def _run_loop(self, task: str, conversation_id: Optional[int],
                        user_id: int):
        """Shared tool-call loop. Yields semantic events:

          {"type": "start", "agent_id", "agent_name"}
          {"type": "tool_call_start", "name", "arguments", "call_id"}
          {"type": "tool_call_end", "name", "call_id", "result_preview", "error"}
          {"type": "answer_ready", "messages", "new_messages",
                                   "candidate_text", "tool_call_log"}   # terminal-ish
          {"type": "error", "status": "failed"|"error", "error", ["tool_call_log"]}

        On ``answer_ready`` the model is ready to produce the final answer but
        it has NOT been generated/streamed yet — the consumer finalizes it.
        Persistence is the consumer's job (batch uses candidate_text; stream
        re-generates), so this generator never writes memory.
        """
        system_prompt = await self._build_system_prompt(task)
        tools = await self._build_tools()
        await self._resolve_mcp_lookup()
        history = await self._load_memory(conversation_id)

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": task})

        new_messages: List[Dict[str, Any]] = [{"role": "user", "content": task}]
        tool_call_log: List[Dict[str, Any]] = []

        router = get_llm_router()
        tool_used_ever = False
        auto_continue_used = 0
        fingerprints: Counter = Counter()  # tool-call fingerprint -> times seen
        reflections_used = 0               # reflector interventions so far
        tool_calls_made = 0                # total tools dispatched this run

        yield {"type": "start", "agent_id": self.agent_id, "agent_name": self.agent_name}

        for step in range(self.max_steps):
            messages = await self._maybe_compact(messages, router)

            # Self-recovery: retry transient LLM failures with linear backoff
            # before failing the turn (cf. PentAGI Reflector recovery).
            msg = None
            last_err: Optional[Exception] = None
            for attempt in range(LLM_RETRY_MAX + 1):
                try:
                    msg = await router.chat(
                        messages=messages,
                        provider_id=self.llm_provider_id,
                        model=self.llm_model,
                        tools=tools if tools else None,
                        pii_policy=self._pii_policy,
                    )
                    break
                except Exception as e:
                    last_err = e
                    if attempt < LLM_RETRY_MAX:
                        yield {"type": "reflection", "reason": "llm_error",
                               "attempt": attempt + 1}
                        await asyncio.sleep(LLM_RETRY_BACKOFF * (attempt + 1))
            if msg is None:
                yield {"type": "error", "status": "failed",
                       "error": f"LLM error at step {step} after "
                                f"{LLM_RETRY_MAX + 1} attempts: {last_err}"}
                return

            if isinstance(msg, str):
                tool_calls = None
                text_only = True
                candidate_text = msg
            else:
                tool_calls = getattr(msg, "tool_calls", None)
                text_only = not tool_calls
                candidate_text = getattr(msg, "content", None) or ""

            if text_only:
                if tools and not tool_used_ever and auto_continue_used < AUTO_CONTINUE_MAX:
                    auto_continue_used += 1
                    messages.append({
                        "role": "user",
                        "content": "如果任务尚未完成，请调用相应工具继续；"
                                   "如果确认已完成，请直接给出最终答复。",
                    })
                    continue
                yield {"type": "answer_ready", "messages": messages,
                       "new_messages": new_messages,
                       "candidate_text": candidate_text,
                       "tool_call_log": tool_call_log}
                return

            tool_used_ever = True
            assistant_msg = {
                "role": "assistant",
                "content": getattr(msg, "content", None) or "",
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.function.name,
                                      "arguments": c.function.arguments},
                    } for c in tool_calls
                ],
            }
            messages.append(assistant_msg)
            new_messages.append(assistant_msg)

            for c in tool_calls:
                yield {"type": "tool_call_start", "name": c.function.name,
                       "arguments": c.function.arguments, "call_id": c.id}

            # Per-call guards, evaluated synchronously before any await so the
            # shared counters can't interleave across the gathered coroutines:
            #   * budget gate — hard cap on total tool executions per run;
            #   * loop guard  — short-circuit identical repeats into a notice.
            loop_hit = False
            budget_hit = False

            async def _dispatch_or_reflect(call):
                nonlocal loop_hit, budget_hit, tool_calls_made
                if tool_calls_made >= self.tool_call_budget:
                    budget_hit = True
                    logger.warning("internal agent %s: tool-call budget (%d) exhausted",
                                   self.agent_name, self.tool_call_budget)
                    return self._budget_notice(self.tool_call_budget)
                tool_calls_made += 1
                fp = self._fingerprint(call.function.name, call.function.arguments)
                fingerprints[fp] += 1
                if fingerprints[fp] >= LOOP_DETECT_THRESHOLD:
                    loop_hit = True
                    logger.warning("internal agent %s: tool-call loop on %r (x%d)",
                                   self.agent_name, call.function.name, fingerprints[fp])
                    return self._loop_notice(call.function.name, fingerprints[fp])
                return await self._dispatch(call)

            results = await asyncio.gather(*[_dispatch_or_reflect(c) for c in tool_calls])
            for call, result_str in zip(tool_calls, results):
                result_str = self._truncate_tool_result(result_str)
                tool_call_log.append({"name": call.function.name,
                                       "arguments": call.function.arguments,
                                       "result_preview": result_str[:200]})
                tool_msg = {"role": "tool", "tool_call_id": call.id,
                            "content": result_str}
                messages.append(tool_msg)
                new_messages.append(tool_msg)
                yield {"type": "tool_call_end", "name": call.function.name,
                       "call_id": call.id, "result_preview": result_str[:200],
                       "error": result_str.startswith(
                           ("ERROR", "LOOP_DETECTED", "BUDGET_EXHAUSTED"))}

            if budget_hit:
                # Hard cap reached: withdraw tools so the next turn must answer
                # from what it already gathered, rather than erroring out.
                tools = None
                yield {"type": "reflection", "reason": "budget",
                       "tool_calls_made": tool_calls_made}
                messages.append({"role": "user", "content": (
                    f"已达到本次任务的工具调用上限（{self.tool_call_budget} 次），"
                    f"不会再执行任何工具。请基于已获取的信息直接给出最终答复。")})
                continue

            if loop_hit:
                reflections_used += 1
                yield {"type": "reflection", "reason": "loop",
                       "count": reflections_used}
                if reflections_used > REFLECT_MAX:
                    yield {"type": "error", "status": "error",
                           "error": (f"aborted: agent stuck in a tool-call loop "
                                     f"(repeated identical calls); reflector gave up "
                                     f"after {REFLECT_MAX} nudges"),
                           "tool_call_log": tool_call_log}
                    return
                # One reflector nudge to push the model onto a different path.
                messages.append({"role": "user", "content": REFLECT_GUIDANCE})

        yield {"type": "error", "status": "error",
               "error": f"exceeded tool_loop_max_steps ({self.max_steps})",
               "tool_call_log": tool_call_log}

    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int) -> Dict[str, Any]:
        """Run the tool-call loop (batch). Returns same shape as SubAgentWrapper.execute()."""
        start = time.monotonic()
        self._user_id = user_id

        if self.permission_level == "high":
            return {
                "status": "needs_approval",
                "output": None,
                "error": "High permission internal agent requires approval",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": 0,
            }

        from app.core.langfuse_tracing import trace_run
        session_id = str(conversation_id) if conversation_id else f"agent:{self.agent_id}"

        final_event = None
        with trace_run(session_id=session_id, agent_name=self.agent_name,
                       user_id=user_id):
            async for ev in self._run_loop(task, conversation_id, user_id):
                if ev["type"] in ("answer_ready", "error"):
                    final_event = ev
                    break
                # start / tool_call_* events are not surfaced in batch mode

        if final_event is None or final_event["type"] == "error":
            if final_event and final_event.get("status") == "failed":
                return {
                    "status": "failed",
                    "output": None,
                    "error": final_event["error"],
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "execution_time": round(time.monotonic() - start, 2),
                }
            return {
                "status": "error",
                "output": None,
                "error": final_event["error"] if final_event else "no result produced",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": round(time.monotonic() - start, 2),
                "tool_calls": final_event.get("tool_call_log", []) if final_event else [],
            }

        # answer_ready: batch mode uses the candidate text directly (no re-stream)
        final_text = final_event["candidate_text"]
        new_messages = final_event["new_messages"]
        new_messages.append({"role": "assistant", "content": final_text})
        await self._append_memory(conversation_id, user_id, new_messages)
        await self._maybe_record_episode(task, final_text, final_event["tool_call_log"])

        return {
            "status": "completed",
            "output": final_text,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "execution_time": round(time.monotonic() - start, 2),
            "tool_calls": final_event["tool_call_log"],
        }

    async def _maybe_record_episode(self, task: str, output: str,
                                    tool_call_log: List[Dict[str, Any]]) -> None:
        """Record a successful run as an episode (best-effort, opt-in)."""
        if not self.enable_episodic:
            return
        try:
            from app.services.episodic_memory import distill_approach
            await episodic_memory.record(
                self.agent_id, task, distill_approach(tool_call_log), output,
                success=True, tool_count=len(tool_call_log),
                embedding=self._episode_embedding, provider_id=self.llm_provider_id)
        except Exception as e:               # noqa: BLE001 - never break the run
            logger.debug("episodic record failed: %s", e)

    async def execute_stream(self, task: str, conversation_id: Optional[int],
                             user_id: int):
        """Run the tool-call loop, streaming SSE-shaped event dicts.

        Emits: start / tool_call_start / tool_call_end / text* / done / error.
        The final answer is re-generated via router.stream_chat() (tools=None) —
        Approach 1's one extra LLM call, confined to the streaming path.
        """
        start = time.monotonic()
        self._user_id = user_id

        if self.permission_level == "high":
            yield {"type": "error",
                   "content": "High permission internal agent requires approval"}
            return

        from app.core.langfuse_tracing import trace_run
        session_id = str(conversation_id) if conversation_id else f"agent:{self.agent_id}"

        with trace_run(session_id=session_id, agent_name=self.agent_name,
                       user_id=user_id):
            async for ev in self._run_loop(task, conversation_id, user_id):
                t = ev["type"]
                if t in ("start", "tool_call_start", "tool_call_end", "reflection"):
                    yield ev
                elif t == "error":
                    yield {"type": "error", "content": ev["error"]}
                    return
                elif t == "answer_ready":
                    messages = ev["messages"]
                    new_messages = ev["new_messages"]
                    router = get_llm_router()
                    parts: List[str] = []
                    try:
                        async for delta in router.stream_chat(
                            messages=messages,
                            provider_id=self.llm_provider_id,
                            model=self.llm_model,
                            pii_policy=self._pii_policy,
                        ):
                            parts.append(delta)
                            yield {"type": "text", "content": delta}
                    except Exception as e:
                        yield {"type": "error", "content": f"stream error: {e}"}
                        return

                    final_text = "".join(parts)
                    new_messages.append({"role": "assistant", "content": final_text})
                    await self._append_memory(conversation_id, user_id, new_messages)
                    await self._maybe_record_episode(task, final_text, ev["tool_call_log"])
                    yield {"type": "done", "output": final_text,
                           "execution_time": round(time.monotonic() - start, 2),
                           "tool_calls": ev["tool_call_log"]}
                    return
