"""Internal (in-app, configurable) sub-agent runner.

Runs an inline tool-call loop against the LLM Router. See:
  docs/superpowers/specs/2026-05-28-internal-agents-design.md
"""
import asyncio
import json
import logging
import time
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
        self.mcp_tool_ids: List[int] = meta.get("mcp_tool_ids") or []
        self.pool_tool_ids: List[int] = meta.get("tool_ids") or []
        self.permission_level: str = config.get("permission_level") or "medium"

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
        await session.commit()
        await session.refresh(row)
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
                                                          Skill.is_active == True))
            rows = result.scalars().all()
        return {r.id: (r.md_content or "") for r in rows}

    async def _build_system_prompt(self) -> str:
        parts = [self.system_prompt] if self.system_prompt else []
        bodies = await self._load_skill_bodies(self.associated_skills)
        if bodies:
            parts.append("\n\n## Skills available to you\n")
            for sid in self.associated_skills:
                body = bodies.get(sid)
                if body:
                    parts.append(f"\n### Skill #{sid}\n{body}\n")
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
                                       MCPTool.is_active == True)
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
                                   Tool.is_active == True,
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

        # 3. Executable pool Tool
        if getattr(self, "_pool_tools_by_name", None) and name in self._pool_tools_by_name:
            tool_row = self._pool_tools_by_name[name]
            res = await execute_tool(tool_row, args, user_id=getattr(self, "_user_id", 0))
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
                .where(MCPTool.id.in_(self.mcp_tool_ids), MCPTool.is_active == True)
            )
            for tool, server in result.all():
                self._mcp_by_name[tool.tool_name] = (tool, server)

    # -------- Tool-result pruning + context compaction --------

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

    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int) -> Dict[str, Any]:
        """Run the tool-call loop. Returns same shape as SubAgentWrapper.execute()."""
        start = time.monotonic()
        self._user_id = user_id

        # 1. Permission gate
        if self.permission_level == "high":
            return {
                "status": "needs_approval",
                "output": None,
                "error": "High permission internal agent requires approval",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": 0,
            }

        # 2. Build system prompt + tool catalog + memory
        system_prompt = await self._build_system_prompt()
        tools = await self._build_tools()
        await self._resolve_mcp_lookup()
        history = await self._load_memory(conversation_id)

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": task})

        # Track new messages added this turn (for persistence)
        new_messages: List[Dict[str, Any]] = [{"role": "user", "content": task}]
        tool_call_log: List[Dict[str, Any]] = []

        router = get_llm_router()
        final_text: Optional[str] = None
        tool_used_ever = False
        auto_continue_used = 0

        for step in range(self.max_steps):
            # Compact older history if the running buffer grew too large.
            messages = await self._maybe_compact(messages, router)

            try:
                msg = await router.chat(
                    messages=messages,
                    provider_id=self.llm_provider_id,
                    model=self.llm_model,
                    tools=tools if tools else None,
                )
            except Exception as e:
                return {
                    "status": "failed",
                    "output": None,
                    "error": f"LLM error at step {step}: {e}",
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "execution_time": round(time.monotonic() - start, 2),
                }

            # router.chat returns a plain str when tools is None/empty (Task 4
            # contract); otherwise a message object with optional .tool_calls.
            if isinstance(msg, str):
                tool_calls = None
                text_only = True
                candidate_text = msg
            else:
                tool_calls = getattr(msg, "tool_calls", None)
                text_only = not tool_calls
                candidate_text = getattr(msg, "content", None) or ""

            if text_only:
                # Auto-continue: a tool-equipped agent that answered without
                # ever calling a tool gets a bounded nudge to use tools or
                # confirm completion (cf. QwenPaw _auto_continue_if_text_only).
                # The nudge is intentionally NOT persisted to memory.
                if tools and not tool_used_ever and auto_continue_used < AUTO_CONTINUE_MAX:
                    auto_continue_used += 1
                    messages.append({
                        "role": "user",
                        "content": "如果任务尚未完成，请调用相应工具继续；"
                                   "如果确认已完成，请直接给出最终答复。",
                    })
                    continue
                final_text = candidate_text
                new_messages.append({"role": "assistant", "content": final_text})
                break

            tool_used_ever = True
            # Append assistant message that requested tools
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

            # Execute this step's tool calls concurrently (cf. QwenPaw's
            # asyncio.gather over a reasoning step's tool_calls). _dispatch
            # catches its own errors and returns an error string.
            results = await asyncio.gather(*[self._dispatch(c) for c in tool_calls])
            for call, result_str in zip(tool_calls, results):
                result_str = self._truncate_tool_result(result_str)
                tool_call_log.append({"name": call.function.name,
                                       "arguments": call.function.arguments,
                                       "result_preview": result_str[:200]})
                tool_msg = {"role": "tool", "tool_call_id": call.id,
                            "content": result_str}
                messages.append(tool_msg)
                new_messages.append(tool_msg)

        if final_text is None:
            return {
                "status": "error",
                "output": None,
                "error": f"exceeded tool_loop_max_steps ({self.max_steps})",
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": round(time.monotonic() - start, 2),
                "tool_calls": tool_call_log,
            }

        # Persist memory slice
        await self._append_memory(conversation_id, user_id, new_messages)

        return {
            "status": "completed",
            "output": final_text,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "execution_time": round(time.monotonic() - start, 2),
            "tool_calls": tool_call_log,
        }
