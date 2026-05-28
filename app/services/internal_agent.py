"""Internal (in-app, configurable) sub-agent runner.

Runs an inline tool-call loop against the LLM Router. See:
  docs/superpowers/specs/2026-05-28-internal-agents-design.md
"""
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation


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

    async def _build_tools(self) -> List[Dict[str, Any]]:
        tools = await self._load_mcp_tools()
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

    # -------- Public entry point — implemented in Task 7 --------

    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int) -> Dict[str, Any]:
        raise NotImplementedError("implemented in Task 7")
