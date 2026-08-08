"""LangGraph Master Agent implementation."""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.agents.states import MasterAgentState, AgentState, SubAgentResult
from app.services.agent_executor import AgentExecutor
from app.core.audit import log_audit
from app.core.context_compressor import maybe_compress

logger = logging.getLogger(__name__)


# Structured risk tiers, ordered. Anything unrecognised contributes nothing
# rather than defaulting high — an unknown tier is missing data, not evidence.
_RISK_TIER_WEIGHT = {"low": 0.0, "medium": 0.15, "high": 0.3, "critical": 0.4}
# Statuses that mean the sub-agent did not do its job.
_FAILED_STATUSES = frozenset({"failed", "denied", "halted", "error"})


def derive_risk_score(sub_results: Dict[str, Any]) -> float:
    """Risk score in [0, 1] from **structured** sub-result fields only.

    The node used to publish a literal 0.5, so a clean run and a run where
    every agent was denied scored the same — the number looked meaningful in
    the UI and the audit trail while carrying no information (audit #21).

    Deliberately blind to ``output``. INV-13 forbids user-controllable input
    from driving control flow and INV-39 classes tool output as hostile by
    default, so scoring the text would let anything the agent read move a
    number that a human uses to decide how hard to look.
    """
    results = [r for r in (sub_results or {}).values() if isinstance(r, dict)]
    if not results:
        return 0.0

    failed = sum(1 for r in results
                 if str(r.get("status") or "").lower() in _FAILED_STATUSES)
    fail_ratio = failed / len(results)
    worst_tier = max(
        (_RISK_TIER_WEIGHT.get(
            str(r.get("risk_tier") or r.get("risk_level") or "").lower(), 0.0)
         for r in results),
        default=0.0,
    )
    return round(min(1.0, 0.2 + 0.6 * fail_ratio + worst_tier), 3)


class MasterAgent:
    """
    LangGraph-based Master Agent for task orchestration.

    State machine:
    START -> PARSE_INTENT -> ROUTE_TO_SUB -> WAIT_FOR_SUB_RESULTS
                            -> VALIDATE_RESULTS -> SUMMARIZE -> END
                            -> HUMAN_APPROVAL -> END
       |                              |
       v                              v
    ERROR                          END
    """

    def __init__(self, llm_router=None):
        self.executor = AgentExecutor()
        self.llm_router = llm_router
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(MasterAgentState)

        # Add nodes
        workflow.add_node("start_node", self._start_node)
        workflow.add_node("parse_intent_node", self._parse_intent_node)
        workflow.add_node("router_node", self._router_node)
        workflow.add_node("sub_agent_executor_node", self._sub_agent_executor_node)
        workflow.add_node("group_chat_moderator_node", self._group_chat_moderator_node)
        workflow.add_node("validation_node", self._validation_node)
        workflow.add_node("summarizer_node", self._summarizer_node)
        workflow.add_node("approval_node", self._approval_node)
        workflow.add_node("error_node", self._error_node)

        # Set entry point
        workflow.set_entry_point("start_node")

        # Add edges
        workflow.add_edge("start_node", "parse_intent_node")
        workflow.add_edge("parse_intent_node", "router_node")

        # Router decides next step
        workflow.add_conditional_edges(
            "router_node",
            self._route_decision,
            {
                "sub_agents": "sub_agent_executor_node",
                "group_chat": "group_chat_moderator_node",
                "approval": "approval_node",
                "summarize_direct": "summarizer_node",
                "end": END,
            }
        )

        workflow.add_edge("sub_agent_executor_node", "validation_node")
        workflow.add_conditional_edges(
            "validation_node",
            self._validation_decision,
            {
                "approved": "summarizer_node",
                "rejected": "approval_node",
            }
        )

        workflow.add_edge("group_chat_moderator_node", "summarizer_node")
        workflow.add_edge("summarizer_node", END)
        workflow.add_edge("approval_node", END)
        workflow.add_edge("error_node", END)

        return workflow.compile()

    def _route_decision(self, state: MasterAgentState) -> str:
        """Decide routing based on parsed intent."""
        if state.get("group_chat_active"):
            return "group_chat"

        task_plan = state.get("task_plan", [])
        if not task_plan:
            # No tasks — go to summarizer for direct LLM response
            return "summarize_direct"

        # Check if any task requires approval
        for task in task_plan:
            if task.get("requires_approval", False):
                state["approval_required"] = True
                return "approval"

        return "sub_agents"

    def _validation_decision(self, state: MasterAgentState) -> str:
        """Decide based on structured validation flags (INV-13).

        HITL only when ``approval_required`` is set from structured signals
        (needs_approval status, requires_approval, risk_level). Agent failures
        alone go to summarizer so errors surface without keyword-based HITL.
        """
        if state.get("approval_required"):
            return "rejected"
        return "approved"

    async def _start_node(self, state: MasterAgentState) -> MasterAgentState:
        """Start node - initialize state."""
        state["current_state"] = AgentState.START
        state["request_id"] = str(uuid.uuid4())
        state["timestamp"] = datetime.now(timezone.utc).isoformat()
        state["sub_results"] = {}
        state["group_chat_messages"] = []
        return state

    async def _parse_intent_node(self, state: MasterAgentState) -> MasterAgentState:
        """Parse user intent and create task plan.

        Dispatch precedence (first match wins):
          1. Explicit `agent_id` from UI — single task to that one agent.
          2. mode == "fast" — empty task_plan, falls through to Master LLM reply.
          3. mode == "expert" — fan out to every active sub-agent.
          4. mode == "normal" (default) — LLM intent parser decides.
        """
        state["current_state"] = AgentState.PARSE_INTENT

        user_input = state.get("user_input", "")
        user_id = state.get("user_id")
        mode = (state.get("mode") or "normal").lower()

        # ----- 1. Explicit agent selection from the WebUI -----
        explicit_agent_id = state.get("agent_id")
        if explicit_agent_id:
            try:
                aid = int(explicit_agent_id)
            except (TypeError, ValueError):
                aid = explicit_agent_id
            state["intent"] = "task_execution"
            state["task_plan"] = [{
                "agent_id": aid,
                "task": user_input,
                "requires_approval": False,
                "dispatch_source": "user_explicit",  # INV-21: user chose the agent
            }]
            await log_audit(
                user_id=user_id,
                agent_id=str(aid),
                action="parse_intent",
                input_data={"user_input": user_input, "explicit_agent_id": aid, "mode": mode},
                output_data={"intent": "task_execution", "bypassed_llm_parser": True},
                request_id=state.get("request_id"),
            )
            state["current_state"] = AgentState.ROUTE_TO_SUB
            return state

        # ----- 2. Fast mode — Master Agent only, skip sub-agents -----
        if mode == "fast":
            state["intent"] = "knowledge_query"
            state["task_plan"] = []
            await log_audit(
                user_id=user_id,
                agent_id=None,
                action="parse_intent",
                input_data={"user_input": user_input, "mode": "fast"},
                output_data={"intent": "knowledge_query", "bypassed_llm_parser": True},
                request_id=state.get("request_id"),
            )
            state["current_state"] = AgentState.ROUTE_TO_SUB
            return state

        # ----- 3. Expert mode — fan out to all active sub-agents -----
        if mode == "expert":
            from app.core.database import get_db_context
            from app.models.agent import AgentConfig
            from sqlalchemy import select

            active: List[Dict[str, Any]] = []
            try:
                async with get_db_context() as session:
                    result = await session.execute(
                        select(AgentConfig).where(AgentConfig.is_active.is_(True))
                    )
                    active = [
                        {"id": a.id, "agent_name": a.agent_name, "backend_type": a.backend_type}
                        for a in result.scalars().all()
                    ]
            except Exception as e:
                logger.warning(f"[expert mode] Failed to load active agents: {e}")

            if active:
                state["intent"] = "task_execution"
                state["task_plan"] = [
                    {
                        "agent_id": a["id"],
                        "agent_name": a["agent_name"],
                        "task": user_input,
                        "requires_approval": False,
                        "dispatch_source": "user_expert",  # INV-21: user chose fan-out
                    }
                    for a in active
                ]
            else:
                # No active sub-agents — degrade to Master LLM with a note.
                state["intent"] = "knowledge_query"
                state["task_plan"] = []
                state["expert_mode_no_agents"] = True

            await log_audit(
                user_id=user_id,
                agent_id=None,
                action="parse_intent",
                input_data={"user_input": user_input, "mode": "expert"},
                output_data={
                    "intent": state.get("intent"),
                    "fan_out_count": len(active),
                    "agents": [a["agent_name"] for a in active],
                },
                request_id=state.get("request_id"),
            )
            state["current_state"] = AgentState.ROUTE_TO_SUB
            return state

        # ----- 4. Normal mode — LLM intent parser decides -----
        if self.llm_router:
            try:
                parsed = await self.llm_router.parse_intent(
                    user_input,
                    provider_id=state.get("provider_id"),
                    model=state.get("model"),
                    intent_parser_prompt_override=state.get("intent_parser_prompt_override"),
                    temperature_override=state.get("temperature_override"),
                    model_override=state.get("model_override"),
                )
                state["intent"] = parsed.get("intent")
                raw_plan = parsed.get("task_plan", []) or []
                # INV-21: mark LLM-chosen targets so run_task applies the medium/L2 cap
                state["task_plan"] = [
                    {**t, "dispatch_source": t.get("dispatch_source") or "llm"}
                    if isinstance(t, dict)
                    else t
                    for t in raw_plan
                ]
            except Exception as e:
                state["error_message"] = f"Intent parsing failed: {e}"
                return state

        # INV-13: group chat only via structured intent (or UI-preset flag),
        # never via raw keyword match on user_input.
        intent = (state.get("intent") or "").strip().lower()
        if intent == "group_chat":
            state["group_chat_active"] = True
        # Preserve explicit UI / caller pre-set of group_chat_active (truthy only).

        # Log audit
        await log_audit(
            user_id=user_id,
            agent_id=None,
            action="parse_intent",
            input_data={"user_input": user_input},
            output_data={
                "intent": state.get("intent"),
                "task_plan": state.get("task_plan"),
                "group_chat_active": bool(state.get("group_chat_active")),
            },
            request_id=state.get("request_id"),
        )

        state["current_state"] = AgentState.ROUTE_TO_SUB
        return state

    async def _router_node(self, state: MasterAgentState) -> MasterAgentState:
        """Route tasks to sub-agents."""
        state["current_state"] = AgentState.ROUTE_TO_SUB

        task_plan = state.get("task_plan", [])
        if task_plan:
            # Mark which agents need to be called
            state["pending_agents"] = [t.get("agent_id") for t in task_plan]

        return state

    async def _sub_agent_executor_node(self, state: MasterAgentState) -> MasterAgentState:
        """Execute tasks on sub-agents (remote if available, local fallback)."""
        import asyncio
        import time

        state["current_state"] = AgentState.WAIT_FOR_SUB_RESULTS

        task_plan = list(state.get("task_plan", []) or [])
        user_id = state.get("user_id")
        request_id = state.get("request_id")
        provider_id = state.get("provider_id")
        dispatch_depth = int(state.get("dispatch_depth") or 0)

        if not task_plan:
            state["current_state"] = AgentState.VALIDATE_RESULTS
            return state

        # INV-23 · fan-out gates before any I/O
        from app.config import settings as app_settings
        from app.services.fanout_gate import apply_fanout_gates, limits_from_settings

        fanout_limits = limits_from_settings(app_settings)
        # Expert / explicit user fan-out: still concurrency-capped, but allow larger plans
        if any(
            (t.get("dispatch_source") if isinstance(t, dict) else None) == "user_expert"
            for t in task_plan
        ):
            fanout_limits.max_plan_size = max(fanout_limits.max_plan_size, 32)
            fanout_limits.require_target = True  # expert tasks carry agent_id
        gate = apply_fanout_gates(
            task_plan, limits=fanout_limits, dispatch_depth=dispatch_depth
        )
        task_plan = gate.accepted
        gated_denied: Dict[str, Any] = {}
        if gate.rejected:
            for i, item in enumerate(gate.rejected):
                t = item["task"] if isinstance(item.get("task"), dict) else {}
                key = str(
                    t.get("agent_id")
                    or t.get("agent_name")
                    or t.get("agent_type")
                    or f"rejected-{i}"
                )
                # uniquify key collisions among rejects
                base = key
                n = 1
                while key in gated_denied:
                    key = f"{base}#{n}"
                    n += 1
                gated_denied[key] = {
                    "status": "denied",
                    "output": None,
                    "error": f"INV-23 fan-out gate: {item.get('reason')}",
                }
            await log_audit(
                user_id=user_id,
                agent_id=None,
                action="fanout_gate",
                input_data={"plan_in": len(state.get("task_plan") or [])},
                output_data={
                    "accepted": len(gate.accepted),
                    "rejected": len(gate.rejected),
                    "reasons": [r.get("reason") for r in gate.rejected],
                },
                request_id=request_id,
            )
        if not task_plan:
            state["sub_results"] = gated_denied
            state["current_state"] = AgentState.VALIDATE_RESULTS
            return state

        # Fetch registered remote agents (by type and by name) from DB
        from app.core.database import get_db_context
        from app.models.agent import AgentConfig
        from sqlalchemy import select

        remote_agents: Dict[str, Dict] = {}
        remote_agents_by_name: Dict[str, Dict] = {}
        agents_by_id: Dict[int, Dict] = {}
        try:
            async with get_db_context() as session:
                result = await session.execute(select(AgentConfig).where(AgentConfig.is_active.is_(True)))
                for agent_obj in result.scalars().all():
                    backend = getattr(agent_obj, "backend_type", "general")
                    agent_dict = {
                        "id": agent_obj.id,
                        "agent_name": agent_obj.agent_name,
                        "backend_type": backend,
                        "endpoint_url": agent_obj.endpoint_url,
                        "permission_level": getattr(agent_obj, "permission_level", "medium") or "medium",
                        "autonomy_tier": getattr(agent_obj, "autonomy_tier", "L2") or "L2",
                    }
                    agents_by_id[int(agent_obj.id)] = agent_dict
                    if backend not in remote_agents:
                        remote_agents[backend] = agent_dict
                    remote_agents_by_name[agent_obj.agent_name] = agent_dict
        except Exception as e:
            # Functional degradation (route to local executor) is OK, but must be visible
            logger.warning(
                "sub-agent registry load failed; falling back to local executor: %s", e
            )

        from app.services.privilege_inherit import (
            check_dispatch,
            context_for_dispatch_source,
            snapshot_from_mapping,
            unbound_target_snapshot,
        )

        # Build execution coroutines
        async def run_task(task: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
            agent_type = task.get("agent_type", "general")
            task_desc = task.get("task", "")
            agent_id = task.get("agent_id")  # explicit ID override
            agent_name = task.get("agent_name")  # explicit name override
            dispatch_source = task.get("dispatch_source") or "llm"

            # Kill switch — do not dispatch new work while halted (NDB Std §Kill Switch).
            from app.services.kill_switch import is_halted
            if await is_halted(agent_id=agent_id):
                from app.core.audit import record_action
                await record_action(
                    user_id=user_id, agent_id=agent_id, agent_name=agent_name or agent_type,
                    action="dispatch:halted", action_category="annotate",
                    input_data={"task": task_desc[:500]}, output_data={"halted": True})
                return str(agent_id or agent_type), {"status": "halted",
                                                     "error": "kill switch engaged — dispatch refused"}

            # Resolve target agent config (for privilege + routing)
            target_cfg: Optional[Dict[str, Any]] = None
            if agent_id is not None:
                try:
                    aid_int = int(agent_id)
                    target_cfg = agents_by_id.get(aid_int)
                    # Not in the active map (or DB load failed earlier) — load by id
                    # so we still know target privilege before execute (INV-21).
                    if target_cfg is None:
                        loaded = await self.executor._load_config_dict(aid_int)
                        if loaded:
                            target_cfg = loaded
                            agents_by_id[aid_int] = loaded
                except (TypeError, ValueError):
                    target_cfg = None
            if target_cfg is None and agent_name and agent_name in remote_agents_by_name:
                target_cfg = remote_agents_by_name[agent_name]
            if target_cfg is None and agent_type in remote_agents:
                target_cfg = remote_agents[agent_type]

            # INV-21 · privilege inheritance (before any execute)
            source_priv = context_for_dispatch_source(dispatch_source)
            target_priv = (
                snapshot_from_mapping(target_cfg)
                if target_cfg is not None
                else unbound_target_snapshot()
            )
            allowed, deny_reason = check_dispatch(source_priv, target_priv)
            if not allowed:
                from app.core.audit import record_action
                await record_action(
                    user_id=user_id,
                    agent_id=agent_id or (target_cfg or {}).get("id"),
                    agent_name=agent_name or (target_cfg or {}).get("agent_name") or agent_type,
                    action="dispatch:denied_privilege",
                    action_category="annotate",
                    input_data={
                        "task": task_desc[:500],
                        "agent_type": agent_type,
                        "dispatch_source": dispatch_source,
                        "source_permission": source_priv.permission_level,
                        "source_autonomy": source_priv.autonomy_tier,
                        "target_permission": target_priv.permission_level,
                        "target_autonomy": target_priv.autonomy_tier,
                    },
                    output_data={"dispatched": False, "reason": deny_reason, "inv": "INV-21"},
                )
                key = str(agent_id or agent_name or agent_type)
                return key, {
                    "status": "denied",
                    "output": None,
                    "error": f"INV-21 privilege inheritance refused: {deny_reason}",
                    "agent_id": agent_id or (target_cfg or {}).get("id"),
                }

            # Audit the dispatch decision (NDB Std §Audit Trail).
            from app.core.audit import record_action
            await record_action(
                user_id=user_id, agent_id=agent_id, agent_name=agent_name or agent_type,
                action="dispatch", action_category="annotate",
                input_data={
                    "task": task_desc[:500],
                    "agent_type": agent_type,
                    "dispatch_source": dispatch_source,
                },
                output_data={"dispatched": True, "privilege_check": "ok"},
            )

            # Try remote if registered AND has endpoint URL
            if agent_id:
                result = await self.executor.execute(
                    agent_id=agent_id,
                    task=task_desc,
                    user_id=user_id,
                    context={"conversation_id": state.get("conversation_id")},
                )
                return str(agent_id), result

            # OpenClaw agents use the Gateway poll/report flow (no endpoint_url);
            # hermes/custom backends require an endpoint_url for direct HTTP push.
            def _routable(agent_dict: Dict[str, Any]) -> bool:
                return bool(agent_dict.get("endpoint_url")) or agent_dict.get("backend_type") == "openclaw"

            # Try by agent_name first (most specific — user named a specific agent)
            if agent_name and agent_name in remote_agents_by_name:
                agent = remote_agents_by_name[agent_name]
                if _routable(agent):
                    result = await self.executor.execute(
                        agent_id=agent["id"],
                        task=task_desc,
                        user_id=user_id,
                        context={"conversation_id": state.get("conversation_id")},
                    )
                    return agent_name, result

            # Fall back to backend type matching
            if agent_type in remote_agents:
                agent = remote_agents[agent_type]
                if _routable(agent):
                    result = await self.executor.execute(
                        agent_id=agent["id"],
                        task=task_desc,
                        user_id=user_id,
                        context={"conversation_id": state.get("conversation_id")},
                    )
                    return agent_type, result

            # Fallback: local LLM executor
            local_exec = self._get_local_executor()
            result = await local_exec.execute(
                task=task_desc,
                agent_type=agent_type,
                user_id=user_id,
                context=state.get("context"),
                provider_id=provider_id,
            )
            return agent_type, result

        start = time.monotonic()
        # INV-23 · concurrency cap (semaphore); order of results preserved via gather
        sem = asyncio.Semaphore(max(1, int(fanout_limits.max_concurrent)))

        async def run_task_limited(task: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
            async with sem:
                return await run_task(task)

        tasks = [run_task_limited(t) for t in task_plan]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: Dict[str, Any] = {}
        for i, r in enumerate(results_list):
            task_i = task_plan[i]
            agent_type = task_i.get("agent_type", "general")
            if isinstance(r, Exception):
                key = str(
                    task_i.get("agent_id")
                    or task_i.get("agent_name")
                    or agent_type
                )
                results[key] = {
                    "status": "failed",
                    "output": None,
                    "error": str(r),
                    "execution_time": time.monotonic() - start,
                }
            else:
                key, result = r
                results[key] = result

            # Log audit per task
            await log_audit(
                user_id=user_id,
                agent_id=str(results[key].get("agent_id", "") or key),
                action="sub_agent_execute",
                input_data={"task": task_i.get("task")},
                output_data=results[key],
                request_id=request_id,
            )

            if results[key].get("status") == "needs_approval":
                state["approval_required"] = True

        if gated_denied:
            # Preserve INV-23 rejections alongside executed results
            merged = dict(gated_denied)
            merged.update(results)
            state["sub_results"] = merged
        else:
            state["sub_results"] = results
        state["current_state"] = AgentState.VALIDATE_RESULTS
        return state

    def _get_local_executor(self):
        """Lazy-load local executor."""
        if not hasattr(self, "_local_executor"):
            from app.services.local_executor import get_local_executor
            self._local_executor = get_local_executor()
        return self._local_executor

    async def _group_chat_moderator_node(self, state: MasterAgentState) -> MasterAgentState:
        """Moderate group chat among agents."""
        state["current_state"] = AgentState.GROUP_CHAT_MODE

        messages = list(state.get("group_chat_messages", []))
        task_plan = state.get("task_plan", [])
        user_id = state.get("user_id")
        user_input = state.get("user_input", "")

        # Add user message
        messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Round-robin through agents
        for task in task_plan:
            agent_id = task["agent_id"]
            result = await self.executor.execute(
                agent_id=agent_id,
                task=f"Group chat response to: {user_input}",
                user_id=user_id,
                context={"conversation_id": state.get("conversation_id")},
            )

            messages.append({
                "role": "agent",
                "agent_id": agent_id,
                "content": result.get("output", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        state["group_chat_messages"] = messages
        state["current_state"] = AgentState.SUMMARIZE
        return state

    async def _validation_node(self, state: MasterAgentState) -> MasterAgentState:
        """Validate sub-agent results for consistency and structured risk."""
        state["current_state"] = AgentState.VALIDATE_RESULTS

        sub_results = state.get("sub_results", {}) or {}
        task_plan = state.get("task_plan", []) or []

        errors = []
        passed = True
        approval_required = bool(state.get("approval_required"))

        for agent_id, result in sub_results.items():
            if not isinstance(result, dict):
                continue
            status = (result.get("status") or "").lower()
            if status in ("failed", "denied", "halted", "error"):
                errors.append(f"Agent {agent_id} failed: {result.get('error')}")
                passed = False
            # INV-13: structured HITL signals only — never scan free-text output
            if status == "needs_approval" or result.get("requires_approval") is True:
                approval_required = True
            risk = str(
                result.get("risk_level") or result.get("risk_tier") or ""
            ).lower()
            if risk in ("high", "critical"):
                approval_required = True

        for task in task_plan:
            if isinstance(task, dict) and task.get("requires_approval"):
                approval_required = True

        state["approval_required"] = approval_required
        state["validation_passed"] = passed
        state["validation_errors"] = errors
        return state

    async def _summarizer_node(self, state: MasterAgentState) -> MasterAgentState:
        """Generate final summary and action items."""
        state["current_state"] = AgentState.SUMMARIZE

        sub_results = state.get("sub_results", {})
        group_chat_messages = state.get("group_chat_messages", [])

        if sub_results:
            if self.llm_router:
                try:
                    results_list = [
                        {"agent_name": str(k), "output": v.get("output")}
                        for k, v in sub_results.items()
                    ]
                    state["final_summary"] = await self.llm_router.generate_summary(
                        results_list,
                        provider_id=state.get("provider_id"),
                        summarizer_prompt_override=state.get("summarizer_prompt_override"),
                        temperature_override=state.get("temperature_override"),
                        model_override=state.get("model_override"),
                    )
                except Exception:
                    state["final_summary"] = "\n\n".join(
                        f"Agent {k}: {v.get('output', 'No output')}"
                        for k, v in sub_results.items()
                    )
            else:
                state["final_summary"] = "\n\n".join(
                    f"Agent {k}: {v.get('output', 'No output')}"
                    for k, v in sub_results.items()
                )
        elif group_chat_messages:
            state["final_summary"] = "\n".join(
                f"{m['role']}: {m['content']}"
                for m in group_chat_messages[-5:]
            )
        elif self.llm_router:
            # No sub-agents involved — respond directly via LLM
            user_input = state.get("user_input", "")
            logger.debug(f"_summarizer_node: llm_router exists, calling chat()...")
            try:
                # Build the system prompt: per-conversation override (if any) +
                # the live list of registered sub-agents so the LLM can answer
                # meta-questions like "what sub-agents do you have?" truthfully.
                system_prompt = await self.llm_router.build_chat_system_prompt(
                    base_prompt=state.get("system_prompt_override"),
                    mode=state.get("mode"),
                    expert_no_agents=bool(state.get("expert_mode_no_agents")),
                )
                history = state.get("conversation_history") or []
                # M0a-2: threshold from remaining budget (context_window - reserves)
                model_name = (
                    state.get("model_override")
                    or state.get("model")
                    or None
                )
                provider_id = state.get("provider_id")
                try:
                    from app.services.model_limits import limits_for_provider_model
                    from app.config import settings as _settings
                    _cw, _mo = await limits_for_provider_model(provider_id, model_name)
                    if not model_name:
                        _cw = int(getattr(_settings, "DEFAULT_CONTEXT_WINDOW", _cw))
                except Exception:
                    from app.config import settings as _settings
                    _cw = int(getattr(_settings, "DEFAULT_CONTEXT_WINDOW", 128000))
                    _mo = int(getattr(_settings, "CONTEXT_COMPRESS_RESERVE_OUTPUT", 1024))
                history, _compressed, _degraded = await maybe_compress(
                    history,
                    self.llm_router,
                    context_window=_cw,
                    reserve_output=_mo,
                )
                # Observability hook: set so callers (status surface, audit) can see
                # whether compression ran / whether the LLM call degraded.
                state["context_compression"] = {
                    "compressed": _compressed,
                    "degraded": _degraded,
                    "context_window": _cw,
                    "reserve_output": _mo,
                }
                from agent_core.messages import messages_for_model

                messages: List[Dict[str, str]] = [
                    {"role": "system", "content": system_prompt}
                ]
                # History may include exclude_from_context rows (evidence, etc.)
                messages.extend(messages_for_model(history))
                messages.append({"role": "user", "content": user_input})
                state["final_summary"] = await self.llm_router.chat(
                    messages=messages,
                    provider_id=state.get("provider_id"),
                    model=state.get("model"),
                    model_override=state.get("model_override"),
                    temperature_override=state.get("temperature_override"),
                    enable_prompt_cache=True,
                )
                logger.debug(f"_summarizer_node chat() returned: {state['final_summary'][:100]}")
            except Exception as e:
                logger.warning(f"_summarizer_node chat() exception: {e}")
                state["final_summary"] = f"无法处理您的请求，请检查 AI Provider 配置。错误: {e}"
        else:
            logger.debug("_summarizer_node: llm_router is None, returning fallback message")
            state["final_summary"] = "暂无 AI Provider 可用，请先在「AI Provider 配置」页面中添加一个 Provider。"

        state["risk_score"] = derive_risk_score(state.get("sub_results") or {})
        state["action_items"] = ["Review agent outputs", "Validate findings"]
        state["current_state"] = AgentState.END
        return state

    async def _approval_node(self, state: MasterAgentState) -> MasterAgentState:
        """Handle human approval for high-risk operations.

        Creates a DB record and WAITS until an admin approves/rejects via
        the REST API (POST /api/v1/approvals/{id}/decide) or the request expires.
        """
        state["current_state"] = AgentState.HUMAN_APPROVAL
        state["approval_status"] = "pending"

        request_id = state.get("request_id", "")

        # INV-13: risk_level from structured fields only (not free-text keywords)
        sub_results = state.get("sub_results", {}) or {}
        task_plan = state.get("task_plan", []) or []
        risk_level = "medium"
        for v in sub_results.values():
            if not isinstance(v, dict):
                continue
            if (v.get("status") or "").lower() == "needs_approval":
                risk_level = "high"
            rl = str(v.get("risk_level") or v.get("risk_tier") or "").lower()
            if rl in ("high", "critical"):
                risk_level = "high"
        if any(
            isinstance(t, dict) and t.get("requires_approval") for t in task_plan
        ):
            risk_level = "high"

        # Build a human-readable description
        if sub_results:
            descriptions = [
                f"{k}: {v.get('output', '')[:200]}"
                for k, v in sub_results.items()
                if isinstance(v, dict)
                and (
                    (v.get("status") or "").lower() == "needs_approval"
                    or v.get("requires_approval") is True
                    or str(v.get("risk_level") or v.get("risk_tier") or "").lower()
                    in ("high", "critical")
                )
            ]
            action_description = (
                "; ".join(descriptions) or "Agent execution requires approval"
            )
        else:
            action_description = "; ".join(
                t.get("task", "")[:200]
                for t in task_plan
                if isinstance(t, dict) and t.get("requires_approval")
            ) or "Task requires human approval"

        from app.services.approval_service import ApprovalService

        # Write pending request to DB (non-blocking notification via SSE)
        try:
            record = await ApprovalService.create_request(
                request_id=request_id,
                user_id=state.get("user_id", 0),
                action_type="agent_execution",
                action_description=action_description,
                agent_id=None,
                payload={
                    "sub_results": sub_results,
                    "task_plan": state.get("task_plan"),
                    "user_input": state.get("user_input"),
                },
                risk_level=risk_level,
                urgency="urgent" if risk_level == "high" else "normal",
                expires_in_minutes=60,
            )
            state["approval_record_id"] = record.id
        except Exception as e:
            # Log but don't hard-fail — admin can still manage via DB
            import logging
            logging.getLogger(__name__).error(f"[approval] Failed to create DB record: {e}")

        # WAIT for human decision (suspends graph execution, does NOT block event loop)
        try:
            status, comment = await ApprovalService.wait_for_decision(
                request_id=request_id,
                timeout_seconds=3600,  # 1 hour
            )
        except asyncio.TimeoutError:
            status = "expired"

        state["approval_status"] = status
        state["approval_comment"] = comment

        # Transition based on decision
        if status == "approved":
            state["validation_passed"] = True
            state["current_state"] = AgentState.SUMMARIZE
        else:
            # rejected or expired
            state["validation_passed"] = False
            state["error_message"] = f"Approval {status}: {comment or 'timeout'}"
            state["current_state"] = AgentState.ERROR

        return state

    async def _error_node(self, state: MasterAgentState) -> MasterAgentState:
        """Handle errors."""
        state["current_state"] = AgentState.ERROR
        return state

    async def run(self, user_input: str, user_id: int, **kwargs) -> Dict[str, Any]:
        """Run the master agent with user input."""
        from app.core.langfuse_tracing import trace_run

        initial_state = MasterAgentState(
            user_input=user_input,
            user_id=user_id,
            current_state=AgentState.START,
            group_chat_active=False,
            **kwargs,
        )

        session_id = str(kwargs.get("conversation_id") or uuid.uuid4())
        with trace_run(session_id=session_id, agent_name="master", user_id=user_id):
            result = await self.graph.ainvoke(initial_state)
        return result


# Singleton instance
_master_agent: Optional[MasterAgent] = None


def get_master_agent() -> MasterAgent:
    """Get or create master agent singleton."""
    global _master_agent
    if _master_agent is None:
        from app.services.llm_router import get_llm_router
        _master_agent = MasterAgent(llm_router=get_llm_router())
    return _master_agent