"""Internal (in-app, configurable) sub-agent runner.

Runs an inline tool-call loop against the LLM Router. See:
  docs/superpowers/specs/2026-05-28-internal-agents-design.md

M0a-1: loop guards, compaction, and ``run_loop`` live in ``agent_core``;
this module owns DB/memory/skills/MCP wiring and dispatches tools.
"""
import asyncio  # re-exported for tests that monkeypatch internal_agent.asyncio.sleep
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select

from agent_core.compact import maybe_compact_messages
from agent_core.loop_utils import (
    AUTO_CONTINUE_MAX,
    CONTEXT_COMPACT_CHARS,
    CONTEXT_KEEP_RECENT,
    LLM_RETRY_BACKOFF,
    LLM_RETRY_MAX,
    LOOP_DETECT_THRESHOLD,
    REFLECT_GUIDANCE,
    REFLECT_MAX,
    TOOL_CALL_BUDGET_DEFAULT,
    TOOL_CALL_BUDGET_LIMITED,
    TOOL_RESULT_MAX_CHARS,
    budget_notice as _budget_notice_core,
    estimate_message_chars,
    loop_notice as _loop_notice_core,
    messages_to_text,
    tool_call_fingerprint,
    truncate_tool_result,
)
from agent_core.pipeline import BlockedResult, run_tool_call
from agent_core.run_loop import RunLoopConfig, run_loop

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.services.llm_router import get_llm_router
from app.services.tool_executor import execute_tool


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
    def __init__(self, config: Dict[str, Any], *, pre_approved: bool = False):
        # A human has already approved this dispatch, so the *first* gated tool
        # call may proceed. Deliberately consumed once: one approval authorises
        # one action, not every gated action the run later thinks of.
        self._pre_approved: bool = bool(pre_approved)
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
        # off | approval | auto. An absent or NULL column means the gated
        # default, never the open one.
        self.code_execution_mode: str = (
            config.get("code_execution_mode") or "approval"
        )
        self._run_request_id: Optional[str] = None
        # Set when a tool asked for human approval during this run. The run's
        # own status has to carry it: master decides whether to suspend from
        # the sub-agent result, and a tool result never reaches that decision.
        self._pending_approval_reason: Optional[str] = None
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
        from app.services.conversation_messages import fetch_recent, to_message_dict

        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Conversation).where(
                    Conversation.parent_conversation_id == parent_conversation_id,
                    Conversation.agent_id == self.agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return []
            # LIMIT memory_window in the database. The blob this replaced was
            # loaded whole and then sliced, so a long-lived agent slice paid
            # for its entire history on every turn.
            rows = await fetch_recent(s, row.id, self.memory_window)
            return [to_message_dict(m) for m in rows]

    async def _append_memory(
        self, parent_conversation_id: Optional[int], user_id: int,
        messages: List[Dict[str, str]],
    ) -> None:
        if parent_conversation_id is None or not messages:
            return
        from app.services.conversation_messages import append_messages_locked

        async with AsyncSessionLocal() as s:
            row = await self._get_or_create_slice_row(s, parent_conversation_id, user_id)
            await s.flush()
            # Takes the row lock itself; the chain head is read under it.
            await append_messages_locked(s, row.id, [dict(m) for m in messages])
            await s.commit()

    # -------- System prompt assembly --------

    async def _load_skill_catalog(self, skill_ids: List[int]) -> List[Dict[str, Any]]:
        """Metadata only (name + description) — progressive disclosure."""
        if not skill_ids:
            return []
        from app.services.skill_loader import SkillLoader
        return await SkillLoader.load_skill_catalog(skill_ids)

    async def _load_skill_bodies(self, skill_ids: List[int]) -> Dict[int, str]:
        """Deprecated full-body load — tests may still patch this; prefer catalog."""
        catalog = await self._load_skill_catalog(skill_ids)
        # Bodies intentionally omitted from catalog path
        return {int(s["id"]): "" for s in catalog if s.get("id") is not None}

    async def _build_system_prompt(self, task: Optional[str] = None) -> str:
        parts = [self.system_prompt] if self.system_prompt else []
        # Progressive disclosure: name+description only; body via load_skill tool
        catalog = await self._load_skill_catalog(self.associated_skills)
        if catalog:
            from app.services.skill_loader import SkillLoader
            parts.append("\n\n" + SkillLoader.format_catalog_prompt(catalog))

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

        if getattr(self, "code_execution_mode", "approval") != "off":
            tools.append({
                "type": "function",
                "function": {
                    "name": "run_python",
                    "description": (
                        "Run a short Python program in an isolated sandbox with no "
                        "network access and the standard library only. Use it to "
                        "compute, parse or transform data you already have. Unless "
                        "this agent is in auto mode the code is shown to a human "
                        "for approval before it runs."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string",
                                     "description": "The complete Python program."},
                        },
                        "required": ["code"],
                    },
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

        # Progressive skill load (body not in system prompt)
        if self.associated_skills:
            tools.append({
                "type": "function",
                "function": {
                    "name": "load_skill",
                    "description": (
                        "Load the full text of an associated skill/SOP by name or id. "
                        "Use after consulting the skill catalog in the system prompt."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Skill name or numeric id",
                            },
                        },
                        "required": ["name"],
                    },
                },
            })
        return tools

    # -------- Tool governance (INV-28 before_tool_call) --------

    def _tool_meta(self, name: str) -> Dict[str, Any]:
        """Governance taxonomy for ``name``, resolved before anything executes.

        Untagged MCP / pool tools fall back to ``observe``, matching
        ``execute_tool``. That keeps existing deployments working, but it means
        the *category* rules only bite for tools an operator has actually
        tagged — the kill switch and the audit trail apply either way, which is
        the part that was missing.
        """
        if name in (getattr(self, "_mcp_by_name", None) or {}):
            tool_row, _server = self._mcp_by_name[name]
            return {"action_category": getattr(tool_row, "action_category", None),
                    "risk_tier": getattr(tool_row, "risk_tier", None),
                    "transport": "mcp"}
        pool = getattr(self, "_pool_tools_by_name", None) or {}
        if name in pool:
            tool_row = pool[name]
            return {"action_category": getattr(tool_row, "action_category", None),
                    "risk_tier": getattr(tool_row, "risk_tier", None),
                    "transport": "pool"}
        if name == "run_python":
            # The one built-in that executes caller-authored code. Grouping it
            # with the read-only helpers would hide it from category rules.
            return {"action_category": "mutate", "risk_tier": "high",
                    "transport": "builtin"}
        # Synthetic read-only tools owned by this runner.
        if name in ("kb_search", "web_search", "vuln_search", "load_skill"):
            return {"action_category": "observe", "risk_tier": "low",
                    "transport": "builtin"}
        return {"action_category": None, "risk_tier": None, "transport": "unknown"}

    async def _before_tool_call(self, ctx, args) -> Optional[BlockedResult]:
        """Kill switch + gatekeeper for **every** tool, whatever its transport.

        Previously only pool tools were gated, inside ``execute_tool``. MCP,
        ``kb_search`` and ``web_search`` reached their executors directly, so
        the one path carrying arbitrary external capability was also the one
        with no kill switch, no gatekeeper and no audit row (audit #5).

        Hanging this on ``before_tool_call`` rather than adding a second check
        in ``_dispatch`` is what makes "every path is gated" statically
        checkable (INV-28).
        """
        from app.core.audit import record_action
        from app.services.gatekeeper import gatekeeper_check, Decision
        from app.services.governance_config import load_governance
        from app.services.kill_switch import is_halted
        from app.services.tool_confidence import estimate_tool_confidence

        name = ctx.tool_name
        meta = self._tool_meta(name)
        governance = load_governance(self._governance_cfg)
        governance.halted = await is_halted(agent_id=self.agent_id)
        # A real confidence signal, so `escalate_to_human_below` stops being
        # dead configuration (audit #10).
        confidence = estimate_tool_confidence(meta, args)
        verdict = gatekeeper_check(meta, governance, confidence=confidence)

        # INV-29: the audit emit is awaited and its failure is *not* swallowed.
        # A refusal we cannot prove afterwards is not a control.
        await record_action(
            user_id=getattr(self, "_user_id", None) or None,
            agent_id=self.agent_id, agent_name=self.agent_name,
            action=f"gatekeeper:{verdict.decision.value}",
            action_category=verdict.category, risk_tier=verdict.risk_tier,
            confidence=confidence,
            input_data={"tool": name, "transport": meta["transport"], "args": args},
            output_data={"decision": verdict.decision.value, "reason": verdict.reason},
        )

        if verdict.decision is Decision.DENY:
            status = "halted" if governance.halted else "denied"
            # INV-32: structured, not a string prefix the model has to parse.
            return BlockedResult(
                payload={"status": status, "is_error": True,
                         "error": f"tool {name!r} was refused — {verdict.reason}"},
                reason=status)
        if verdict.decision is Decision.NEEDS_APPROVAL:
            if name == "run_python":
                # run_python carries its own, stronger gate: it opens an
                # approval holding the program and pins its digest. Letting the
                # generic escalation short-circuit here would put a record in
                # front of a reviewer with no code in it — a blind approval —
                # and delay the code-carrying one by a round. A DENY above
                # still short-circuits; only the escalation defers.
                return None
            if self._pre_approved:
                # A human already signed off on this dispatch. Spend the
                # approval on this one call so the next gated tool still stops.
                self._pre_approved = False
                await record_action(
                    user_id=getattr(self, "_user_id", None) or None,
                    agent_id=self.agent_id, agent_name=self.agent_name,
                    action="gatekeeper:pre_approved",
                    action_category=verdict.category, risk_tier=verdict.risk_tier,
                    input_data={"tool": name, "args": args},
                    output_data={"decision": "allowed",
                                 "reason": "prior human approval",
                                 "approval_type": "separation_of_duties"},
                )
                return None
            await self._request_approval(name, args, verdict.risk_tier)
            reason = (f"tool {name!r} requires human approval — {verdict.reason}")
            # The loop carries on and the model writes some closing text, so the
            # run would otherwise report "completed" and the graph would never
            # suspend — leaving the approval record with nothing to resume.
            # This applies to every gated tool, not only run_python.
            self._pending_approval_reason = reason
            return BlockedResult(
                payload={"status": "needs_approval", "is_error": True,
                         "error": reason},
                reason="needs_approval")
        return None

    async def _request_approval(self, name: str, args: Dict[str, Any],
                                risk_tier: Optional[str]) -> None:
        """Raise a human-approval request for a gated tool call.

        INV-06 / INV-38: the record states which kind of approval this is. On
        the server this is separation-of-duties (a different human decides);
        recording it unmarked would let a self-approval later be read as one.
        """
        import uuid
        from app.services.approval_service import ApprovalService

        await ApprovalService.create_request(
            request_id=str(uuid.uuid4()),
            user_id=getattr(self, "_user_id", 0) or 0,
            action_type="tool.execute",
            action_description=f"Agent {self.agent_name!r} wants to run tool {name!r}",
            agent_id=self.agent_id, agent_name=self.agent_name,
            payload={"tool": name, "args": args, "approval_type": "separation_of_duties"},
            risk_level=risk_tier or "high",
        )

    async def _run_python(self, code: str) -> Dict[str, Any]:
        """Execute model-authored code, gated by this agent's execution mode.

        In `approval` mode the gate is here in code rather than in gatekeeper
        policy: removing the human is meant to be an explicit, audited change of
        `code_execution_mode`, not a threshold someone lowers to zero.
        """
        from app.core.database import get_db_context
        from app.services import code_approval, code_runner

        mode = getattr(self, "code_execution_mode", "approval")
        if mode == "off":
            return {"status": "error", "is_error": True,
                    "error": "this agent is not permitted to execute code"}

        if mode == "auto":
            return await code_runner.run_code(code)

        run_id = getattr(self, "_run_request_id", None)
        if not run_id:
            # Without a run id an approval cannot be scoped, and an unscoped
            # approval is not one. Refuse rather than widen it.
            return {"status": "error", "is_error": True,
                    "error": "no run id available to scope a code approval"}

        digest = code_approval.code_digest(code)
        async with get_db_context() as db:
            if await code_approval.find_approved(db, run_id, digest):
                return await code_runner.run_code(code)

            if await code_approval.count_rounds(db, run_id) >= \
                    code_approval.MAX_CODE_APPROVAL_ROUNDS:
                return {
                    "status": "error", "is_error": True,
                    "error": (
                        "too many code approval rounds in this run; the proposed "
                        "code kept changing between approvals"
                    ),
                }

            await code_approval.create_pending(
                db, request_id=run_id, digest=digest, code=code,
                user_id=getattr(self, "_user_id", 0) or 0,
                agent_id=self.agent_id, agent_name=self.agent_name,
            )

        reason = ("this code needs human approval before it can run; "
                  "propose the identical code again after it is approved")
        # The loop will carry on and the model will write some closing text, so
        # the run would otherwise report "completed" and the graph would never
        # suspend. Record it here; execute() turns it into the run's status.
        self._pending_approval_reason = reason
        return {"status": "needs_approval", "is_error": True, "error": reason}

    # -------- Tool dispatch --------

    async def _dispatch(self, call) -> str:
        """Execute a single tool_call and return a JSON-safe string result.

        Every branch goes through ``agent_core.pipeline.run_tool_call`` (INV-28).
        Pool tools additionally re-enter the pipeline inside ``execute_tool``;
        nested pipeline is intentional (outer = agent dispatch, inner = pool gates).
        """
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}

        async def _execute(_ctx, bound_args: dict) -> str:
            # 1. MCP tool lookup
            if hasattr(self, "_mcp_by_name") and name in self._mcp_by_name:
                from app.services.mcp_executor import execute_mcp_tool
                tool_row, server_row = self._mcp_by_name[name]
                try:
                    result = await execute_mcp_tool(server_row, tool_row.tool_name, bound_args)
                    return json.dumps(result, ensure_ascii=False, default=str)
                except Exception as e:
                    return f"ERROR: MCP tool {name!r} failed: {e}"

            # 1b. Progressive skill body load
            if name == "load_skill":
                from app.services.skill_loader import SkillLoader
                key = bound_args.get("name") or bound_args.get("id") or ""
                skill = await SkillLoader.load_skill_body(
                    key, allowed_ids=self.associated_skills or None
                )
                if not skill:
                    return json.dumps(
                        {
                            "status": "error",
                            "is_error": True,
                            "error": f"unknown or unauthorized skill: {key!r}",
                        },
                        ensure_ascii=False,
                    )
                return SkillLoader.wrap_skill_body(skill)

            # 1c. Model-authored code
            if name == "run_python":
                res = await self._run_python(bound_args.get("code") or "")
                if res.get("status") == "completed":
                    return res.get("stdout", "") or "(no output)"
                return res

            # 2. KB synthetic tool
            if name == "kb_search" and self.knowledge_base_id:
                try:
                    chunks = await knowledge_service.search(
                        self.knowledge_base_id,
                        bound_args.get("query", ""),
                        bound_args.get("top_k", 5),
                    )
                    return json.dumps(chunks, ensure_ascii=False, default=str)
                except Exception as e:
                    return f"ERROR: kb_search failed: {e}"

            # 3. Search synthetic tools (OSINT web / vuln recon)
            if name in ("web_search", "vuln_search") and self.enable_search:
                try:
                    fn = getattr(search_service, name)
                    results = await fn(bound_args.get("query", ""), bound_args.get("limit", 5))
                    return json.dumps(results, ensure_ascii=False, default=str)
                except Exception as e:
                    return f"ERROR: {name} failed: {e}"

            # 4. Executable pool Tool. `governance=None` skips execute_tool's own
            # gatekeeper block: `before_tool_call` already rendered that verdict
            # for every transport, and running it twice would double-audit and
            # raise two approval requests for one call. execute_tool's RBAC,
            # sandbox and runner checks still apply, as do its gates for the
            # REST and broker callers that pass a governance context.
            if getattr(self, "_pool_tools_by_name", None) and name in self._pool_tools_by_name:
                tool_row = self._pool_tools_by_name[name]
                res = await execute_tool(tool_row, bound_args, user_id=getattr(self, "_user_id", 0),
                                         governance=None, confidence=None)
                if res.get("status") == "completed":
                    return res.get("stdout", "") or "(no output)"
                return {"status": res.get("status") or "error", "is_error": True,
                        "error": res.get("error") or res.get("stderr") or str(res)}

            return {"status": "error", "is_error": True,
                    "error": f"unknown tool {name!r}"}

        return await run_tool_call(
            tool_name=name,
            arguments=args,
            user_id=getattr(self, "_user_id", None),
            metadata={"backend": "internal_dispatch", "agent_name": self.agent_name},
            before_tool_call=self._before_tool_call,
            execute=_execute,
        )

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

    # -------- Tool-result pruning + context compaction (agent_core wrappers) --

    @staticmethod
    def _fingerprint(name: str, arguments: str) -> str:
        return tool_call_fingerprint(name, arguments)

    @staticmethod
    def _loop_notice(name: str, count: int) -> str:
        return _loop_notice_core(name, count)

    @staticmethod
    def _budget_notice(budget: int) -> str:
        return _budget_notice_core(budget)

    @staticmethod
    def _truncate_tool_result(text: str) -> str:
        return truncate_tool_result(text, max_chars=TOOL_RESULT_MAX_CHARS)

    @staticmethod
    def _estimate_chars(messages: List[Dict[str, Any]]) -> int:
        return estimate_message_chars(messages)

    @staticmethod
    def _messages_to_text(messages: List[Dict[str, Any]]) -> str:
        return messages_to_text(messages)

    async def _maybe_compact(self, messages: List[Dict[str, Any]], router) -> List[Dict[str, Any]]:
        """Summarise older messages when the buffer grows too large.

        M0a-2: prefer remaining-budget threshold from model context_window.
        """
        from agent_core.model_limits import resolve_model_limits

        try:
            from app.services.model_limits import limits_for_provider_model
            cw, mo = await limits_for_provider_model(self.llm_provider_id, self.llm_model)
        except Exception:
            cw, mo = resolve_model_limits(self.llm_model)

        return await maybe_compact_messages(
            messages,
            router.chat,
            keep_recent=CONTEXT_KEEP_RECENT,
            context_window=cw,
            reserve_output=mo or 1024,
            chat_kwargs={
                "provider_id": self.llm_provider_id,
                "model": self.llm_model,
                "tools": None,
                "pii_policy": self._pii_policy,
            },
        )

    # -------- Public entry point --------

    async def _run_loop(self, task: str, conversation_id: Optional[int],
                        user_id: int):
        """Shared tool-call loop — delegates to ``agent_core.run_loop``."""
        system_prompt = await self._build_system_prompt(task)
        tools = await self._build_tools()
        await self._resolve_mcp_lookup()
        history = await self._load_memory(conversation_id)
        router = get_llm_router()

        async def _chat(*, messages, tools=None):
            return await router.chat(
                messages=messages,
                provider_id=self.llm_provider_id,
                model=self.llm_model,
                tools=tools if tools else None,
                pii_policy=self._pii_policy,
            )

        async def _compact(messages):
            return await self._maybe_compact(messages, router)

        cfg = RunLoopConfig(
            max_steps=self.max_steps,
            tool_call_budget=self.tool_call_budget,
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            auto_continue_max=AUTO_CONTINUE_MAX,
            loop_detect_threshold=LOOP_DETECT_THRESHOLD,
            reflect_max=REFLECT_MAX,
            llm_retry_max=LLM_RETRY_MAX,
            llm_retry_backoff=LLM_RETRY_BACKOFF,
            tool_result_max_chars=TOOL_RESULT_MAX_CHARS,
            reflect_guidance=REFLECT_GUIDANCE,
        )
        async for ev in run_loop(
            task=task,
            system_prompt=system_prompt,
            history=history,
            tools=tools,
            config=cfg,
            chat=_chat,
            dispatch=self._dispatch,
            compact=_compact,
        ):
            yield ev

    async def execute(self, task: str, conversation_id: Optional[int],
                      user_id: int, *,
                      run_request_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the tool-call loop (batch). Returns same shape as SubAgentWrapper.execute()."""
        start = time.monotonic()
        self._user_id = user_id
        # Scopes a code approval to this graph run. Without it run_python has no
        # key to ask "was this exact code approved for this run?".
        self._run_request_id = run_request_id
        self._pending_approval_reason = None

        # A prior human approval covers this dispatch; without honouring it the
        # graph's post-approval re-dispatch hits the same refusal and the
        # approved work never runs. The per-tool gate still applies.
        if self.permission_level == "high" and not self._pre_approved:
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
            err = (
                final_event["error"]
                if final_event
                else "no result produced"
            )
            tool_log = (
                final_event.get("tool_call_log", []) if final_event else []
            )
            # Record failed episodes too (success=False) so we retain negative signal
            await self._maybe_record_episode(
                task, f"FAILED: {err}", tool_log, success=False
            )
            if final_event and final_event.get("status") == "failed":
                return {
                    "status": "failed",
                    "output": None,
                    "error": err,
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "execution_time": round(time.monotonic() - start, 2),
                    "tool_calls": tool_log,
                }
            return {
                "status": "error",
                "output": None,
                "error": err,
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "execution_time": round(time.monotonic() - start, 2),
                "tool_calls": tool_log,
            }

        # answer_ready: batch mode uses the candidate text directly (no re-stream)
        final_text = final_event["candidate_text"]
        new_messages = final_event["new_messages"]
        new_messages.append({"role": "assistant", "content": final_text})
        await self._append_memory(conversation_id, user_id, new_messages)
        await self._maybe_record_episode(
            task, final_text, final_event["tool_call_log"], success=True
        )

        return {
            # A tool that asked for approval makes the whole run ask: master
            # reads the sub-agent status to decide whether to suspend, and a
            # tool result never reaches that decision on its own.
            "status": "needs_approval" if self._pending_approval_reason else "completed",
            "output": final_text,
            "error": self._pending_approval_reason,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "execution_time": round(time.monotonic() - start, 2),
            "tool_calls": final_event["tool_call_log"],
        }

    async def _maybe_record_episode(
        self,
        task: str,
        output: str,
        tool_call_log: List[Dict[str, Any]],
        *,
        success: bool = True,
    ) -> None:
        """Record a run as an episode (best-effort, opt-in). success=False for failures."""
        if not self.enable_episodic:
            return
        try:
            from app.services.episodic_memory import distill_approach
            await episodic_memory.record(
                self.agent_id,
                task,
                distill_approach(tool_call_log),
                output,
                success=success,
                tool_count=len(tool_call_log),
                embedding=self._episode_embedding if success else None,
                provider_id=self.llm_provider_id,
            )
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

        if self.permission_level == "high" and not self._pre_approved:
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
                    await self._maybe_record_episode(
                        task,
                        f"FAILED: {ev.get('error')}",
                        ev.get("tool_call_log") or [],
                        success=False,
                    )
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
                        await self._maybe_record_episode(
                            task,
                            f"FAILED: stream error: {e}",
                            ev.get("tool_call_log") or [],
                            success=False,
                        )
                        yield {"type": "error", "content": f"stream error: {e}"}
                        return

                    final_text = "".join(parts)
                    new_messages.append({"role": "assistant", "content": final_text})
                    await self._append_memory(conversation_id, user_id, new_messages)
                    await self._maybe_record_episode(
                        task, final_text, ev["tool_call_log"], success=True
                    )
                    yield {"type": "done", "output": final_text,
                           "execution_time": round(time.monotonic() - start, 2),
                           "tool_calls": ev["tool_call_log"]}
                    return
