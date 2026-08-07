"""LangGraph Master Agent implementation.

Phase-3 orchestration notes
---------------------------
* Compiled with a durable checkpointer so ``interrupt()`` can suspend for
  human approval without blocking a worker for up to an hour (#19 / #20).
* Validation can re-plan once on failure (#18) and routes
  ``approval_required`` to the approval node (was intentionally deferred
  until the blocking wait was replaced).
* ``_validation_node`` uses language-agnostic scoring (#21).
* Unused ``ToolNode`` import removed; loop events are surfaced into state
  from ``agent_run_events`` when a run_id is present (#22).
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command

from app.agents.states import MasterAgentState, AgentState
from app.agents.validation import score_results
from app.services.agent_executor import AgentExecutor
from app.core.audit import log_audit
from app.core.context_compressor import maybe_compress

logger = logging.getLogger(__name__)

# Cap back-edge re-plans so a permanently-broken tool cannot loop forever.
_DEFAULT_MAX_REPLANS = 1


def approval_request_id(run_request_id: str, approval_round: int) -> str:
    """Stable, per-gate approval id.

    ``approval_requests.request_id`` is ``String(36)``, so the round cannot be a
    suffix — a uuid plus ``-ap1`` overflows the column. A uuid5 keeps the width
    and stays deterministic, which is what makes the create idempotent when
    ``interrupt()`` re-runs the node on resume.
    """
    if not approval_round:
        return run_request_id
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"cyberguard/approval/{run_request_id}/{approval_round}"))


class MasterAgent:
    """
    LangGraph-based Master Agent for task orchestration.

    State machine (forward + back edges)::

        START -> PARSE_INTENT -> ROUTE
            |-> sub_agents -> VALIDATE -+-> summarizer -> END
            |                           |-> approval -> (resume) -> re-exec / summarize / error
            |                           +-> replan -> PARSE_INTENT
            |-> group_chat -> summarizer -> END
            |-> approval (pre-exec) -> ...
            +-> summarize_direct -> END
    """

    def __init__(self, llm_router=None, checkpointer=None):
        self.executor = AgentExecutor()
        self.llm_router = llm_router
        # Optional injected checkpointer (tests pass MemorySaver). When None,
        # ``run`` / ``resume`` open one via graph_checkpoint.open_checkpointer.
        self._checkpointer = checkpointer

    def _build_graph(self, checkpointer):
        """Build and compile the LangGraph state machine with *checkpointer*."""
        workflow = StateGraph(MasterAgentState)

        workflow.add_node("start_node", self._start_node)
        workflow.add_node("parse_intent_node", self._parse_intent_node)
        workflow.add_node("router_node", self._router_node)
        workflow.add_node("sub_agent_executor_node", self._sub_agent_executor_node)
        workflow.add_node("group_chat_moderator_node", self._group_chat_moderator_node)
        workflow.add_node("validation_node", self._validation_node)
        workflow.add_node("summarizer_node", self._summarizer_node)
        workflow.add_node("approval_node", self._approval_node)
        workflow.add_node("error_node", self._error_node)

        workflow.set_entry_point("start_node")

        workflow.add_edge("start_node", "parse_intent_node")
        workflow.add_edge("parse_intent_node", "router_node")

        workflow.add_conditional_edges(
            "router_node",
            self._route_decision,
            {
                "sub_agents": "sub_agent_executor_node",
                "group_chat": "group_chat_moderator_node",
                "approval": "approval_node",
                "summarize_direct": "summarizer_node",
                "end": END,
            },
        )

        workflow.add_edge("sub_agent_executor_node", "validation_node")
        workflow.add_conditional_edges(
            "validation_node",
            self._validation_decision,
            {
                "approved": "summarizer_node",
                "needs_approval": "approval_node",
                "replan": "parse_intent_node",
                "failed_final": "summarizer_node",
            },
        )

        workflow.add_edge("group_chat_moderator_node", "summarizer_node")
        workflow.add_edge("summarizer_node", END)

        # Approval node uses interrupt(); on resume it routes onward.
        workflow.add_conditional_edges(
            "approval_node",
            self._approval_decision,
            {
                "re_execute": "sub_agent_executor_node",
                "summarize": "summarizer_node",
                "rejected": "error_node",
            },
        )
        workflow.add_edge("error_node", END)

        return workflow.compile(checkpointer=checkpointer)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _route_decision(self, state: MasterAgentState) -> str:
        if state.get("group_chat_active"):
            return "group_chat"

        task_plan = state.get("task_plan") or []
        if not task_plan:
            return "summarize_direct"

        for task in task_plan:
            if task.get("requires_approval") and not state.get("pre_approved"):
                return "approval"

        return "sub_agents"

    def _validation_decision(self, state: MasterAgentState) -> str:
        """Route after validation.

        Order matters: an approval pause outranks a clean pass (tool did not
        run / high-risk content needs a human), and re-plan is only offered
        while under the replan budget.
        """
        if state.get("approval_required") and not self._approval_is_current(state):
            return "needs_approval"

        if state.get("validation_passed", False):
            return "approved"

        replan_count = int(state.get("replan_count") or 0)
        max_replans = int(state.get("max_replans") if state.get("max_replans") is not None
                          else _DEFAULT_MAX_REPLANS)
        if replan_count < max_replans:
            return "replan"
        return "failed_final"

    @staticmethod
    def _approval_is_current(state: MasterAgentState) -> bool:
        """Whether a human decision covers *this* gate.

        A decision is spent once the dispatch it authorised has run. Comparing
        only ``approval_status == "approved"`` made the first approval stand in
        for every later gate in the thread, so a second high-risk action was
        never shown to anyone.
        """
        if state.get("approval_status") != "approved":
            return False
        granted = state.get("approval_granted_round")
        return granted is not None and int(granted) == int(state.get("approval_round") or 0)

    def _approval_decision(self, state: MasterAgentState) -> str:
        status = state.get("approval_status")
        if status == "approved":
            # Re-dispatch when a tool was blocked before execution; otherwise
            # the human only signed off on high-risk *output* and we summarize.
            sub_results = state.get("sub_results") or {}
            if any(
                isinstance(r, dict) and r.get("status") == "needs_approval"
                for r in sub_results.values()
            ) or any(
                t.get("requires_approval")
                for t in (state.get("task_plan") or [])
            ):
                return "re_execute"
            return "summarize"
        return "rejected"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _start_node(self, state: MasterAgentState) -> MasterAgentState:
        state["current_state"] = AgentState.START
        if not state.get("request_id"):
            state["request_id"] = str(uuid.uuid4())
        state["timestamp"] = datetime.now(timezone.utc).isoformat()
        state.setdefault("sub_results", {})
        state.setdefault("group_chat_messages", [])
        state.setdefault("replan_count", 0)
        state.setdefault("max_replans", _DEFAULT_MAX_REPLANS)
        state.setdefault("pre_approved", False)
        state.setdefault("interrupted", False)
        state.setdefault("loop_events", [])
        return state

    async def _parse_intent_node(self, state: MasterAgentState) -> MasterAgentState:
        """Parse user intent and create task plan.

        Dispatch precedence (first match wins):
          1. Explicit ``agent_id`` from UI — single task to that one agent.
          2. mode == "fast" — empty task_plan, falls through to Master LLM reply.
          3. mode == "expert" — fan out to every active sub-agent.
          4. mode == "normal" (default) — LLM intent parser decides.
        """
        state["current_state"] = AgentState.PARSE_INTENT

        # Re-plan path: bump the counter so the validation back-edge cannot
        # loop forever. Only count when we already have prior sub_results.
        if state.get("sub_results") and state.get("validation_passed") is False:
            state["replan_count"] = int(state.get("replan_count") or 0) + 1
            state["sub_results"] = {}
            state["validation_errors"] = []
            state["approval_required"] = False

        user_input = state.get("user_input", "")
        user_id = state.get("user_id")
        mode = (state.get("mode") or "normal").lower()

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
                    }
                    for a in active
                ]
            else:
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
                state["task_plan"] = parsed.get("task_plan", [])
            except Exception as e:
                state["error_message"] = f"Intent parsing failed: {e}"
                return state

        if any(keyword in user_input.lower() for keyword in ["group chat", "discuss", "all agents"]):
            state["group_chat_active"] = True

        await log_audit(
            user_id=user_id,
            agent_id=None,
            action="parse_intent",
            input_data={"user_input": user_input},
            output_data={"intent": state.get("intent"), "task_plan": state.get("task_plan")},
            request_id=state.get("request_id"),
        )

        state["current_state"] = AgentState.ROUTE_TO_SUB
        return state

    async def _router_node(self, state: MasterAgentState) -> MasterAgentState:
        state["current_state"] = AgentState.ROUTE_TO_SUB
        task_plan = state.get("task_plan") or []
        if task_plan:
            state["pending_agents"] = [t.get("agent_id") for t in task_plan]
        return state

    async def _sub_agent_executor_node(self, state: MasterAgentState) -> MasterAgentState:
        """Execute tasks on sub-agents (remote if available, local fallback)."""
        import time

        state["current_state"] = AgentState.WAIT_FOR_SUB_RESULTS

        task_plan = state.get("task_plan") or []
        user_id = state.get("user_id")
        request_id = state.get("request_id")
        provider_id = state.get("provider_id")
        pre_approved = bool(state.get("pre_approved"))

        if not task_plan:
            state["current_state"] = AgentState.VALIDATE_RESULTS
            return state

        from app.core.database import get_db_context
        from app.models.agent import AgentConfig
        from sqlalchemy import select

        remote_agents: Dict[str, Dict] = {}
        remote_agents_by_name: Dict[str, Dict] = {}
        try:
            async with get_db_context() as session:
                result = await session.execute(
                    select(AgentConfig).where(AgentConfig.is_active.is_(True))
                )
                for agent_obj in result.scalars().all():
                    backend = getattr(agent_obj, "backend_type", "general")
                    agent_dict = {
                        "id": agent_obj.id,
                        "agent_name": agent_obj.agent_name,
                        "backend_type": backend,
                        "endpoint_url": agent_obj.endpoint_url,
                    }
                    if backend not in remote_agents:
                        remote_agents[backend] = agent_dict
                    remote_agents_by_name[agent_obj.agent_name] = agent_dict
        except Exception:
            pass

        async def run_task(task: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
            agent_type = task.get("agent_type", "general")
            task_desc = task.get("task", "")
            agent_id = task.get("agent_id")
            agent_name = task.get("agent_name")

            from app.services.kill_switch import is_halted
            if await is_halted(agent_id=agent_id):
                from app.core.audit import record_action
                await record_action(
                    user_id=user_id, agent_id=agent_id,
                    agent_name=agent_name or agent_type,
                    action="dispatch:halted", action_category="annotate",
                    input_data={"task": task_desc[:500]},
                    output_data={"halted": True})
                return str(agent_id or agent_type), {
                    "status": "halted",
                    "error": "kill switch engaged — dispatch refused",
                }

            from app.core.audit import record_action
            await record_action(
                user_id=user_id, agent_id=agent_id,
                agent_name=agent_name or agent_type,
                action="dispatch", action_category="annotate",
                input_data={"task": task_desc[:500], "agent_type": agent_type},
                output_data={"dispatched": True, "pre_approved": pre_approved})

            context = {
                "conversation_id": state.get("conversation_id"),
                "pre_approved": pre_approved,
                "request_id": request_id,
            }

            if agent_id:
                result = await self.executor.execute(
                    agent_id=agent_id, task=task_desc, user_id=user_id,
                    context=context,
                )
                return str(agent_id), result

            def _routable(agent_dict: Dict[str, Any]) -> bool:
                return bool(agent_dict.get("endpoint_url")) or agent_dict.get("backend_type") == "openclaw"

            if agent_name and agent_name in remote_agents_by_name:
                agent = remote_agents_by_name[agent_name]
                if _routable(agent):
                    result = await self.executor.execute(
                        agent_id=agent["id"], task=task_desc, user_id=user_id,
                        context=context,
                    )
                    return agent_name, result

            if agent_type in remote_agents:
                agent = remote_agents[agent_type]
                if _routable(agent):
                    result = await self.executor.execute(
                        agent_id=agent["id"], task=task_desc, user_id=user_id,
                        context=context,
                    )
                    return agent_type, result

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
        tasks = [run_task(t) for t in task_plan]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: Dict[str, Any] = {}
        for i, r in enumerate(results_list):
            agent_type = task_plan[i].get("agent_type", "general")
            # `key` must be bound on every branch: the audit + approval checks
            # below read results[key], and a bare `except` branch used to leave
            # it holding the *previous* iteration's value (or unbound on the
            # first task, raising NameError and killing the whole node).
            if isinstance(r, Exception):
                key = agent_type
                results[key] = {
                    "status": "failed",
                    "output": None,
                    "error": str(r),
                    "execution_time": time.monotonic() - start,
                }
            else:
                key, result = r
                results[key] = result

            await log_audit(
                user_id=user_id,
                agent_id=str(results[key].get("agent_id", "")),
                action="sub_agent_execute",
                input_data={"task": task_plan[i].get("task")},
                output_data=results[key],
                request_id=request_id,
            )

            if results[key].get("status") == "needs_approval":
                state["approval_required"] = True

            # Surface tool-loop events when the sub-agent recorded a run_id (#22)
            run_id = results[key].get("run_id")
            if run_id:
                events = await self._fetch_loop_events(run_id)
                if events:
                    loop_events = list(state.get("loop_events") or [])
                    loop_events.extend(events)
                    state["loop_events"] = loop_events

        state["sub_results"] = results
        # A human decision authorises exactly one re-dispatch. Retire the whole
        # decision here — clearing `pre_approved` alone was not enough, because
        # `_validation_decision` treats a lingering approval_status="approved"
        # as standing permission and would wave the next gate through without
        # anyone seeing it. Bumping the round also gives the next approval its
        # own request_id instead of reusing the spent one.
        if pre_approved:
            state["pre_approved"] = False
            state["approval_record_id"] = None
            state["approval_round"] = int(state.get("approval_round") or 0) + 1
        state["current_state"] = AgentState.VALIDATE_RESULTS
        return state

    async def _fetch_loop_events(self, run_id: str, *, limit: int = 40) -> List[Dict[str, Any]]:
        """Pull a compact view of agent_run_events for the graph state."""
        try:
            from app.services.run_event_log import get_run_events
            rows = await get_run_events(run_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("loop_events fetch failed for %s: %s", run_id, e)
            return []
        out: List[Dict[str, Any]] = []
        for row in rows[-limit:]:
            out.append({
                "run_id": run_id,
                "seq": row.seq,
                "event_type": row.event_type,
                "payload": row.payload,
                "replay": row.replay,
            })
        return out

    def _get_local_executor(self):
        if not hasattr(self, "_local_executor"):
            from app.services.local_executor import get_local_executor
            self._local_executor = get_local_executor()
        return self._local_executor

    async def _group_chat_moderator_node(self, state: MasterAgentState) -> MasterAgentState:
        state["current_state"] = AgentState.GROUP_CHAT_MODE

        messages = list(state.get("group_chat_messages") or [])
        task_plan = state.get("task_plan") or []
        user_id = state.get("user_id")
        user_input = state.get("user_input", "")

        messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

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
        """Validate sub-agent results for consistency and risk (#21)."""
        state["current_state"] = AgentState.VALIDATE_RESULTS

        sub_results = state.get("sub_results") or {}
        passed, errors, risk_score, action_items, risk_approval = score_results(sub_results)

        if risk_approval:
            state["approval_required"] = True

        state["validation_passed"] = passed
        state["validation_errors"] = errors
        state["risk_score"] = risk_score
        state["action_items"] = action_items
        return state

    async def _summarizer_node(self, state: MasterAgentState) -> MasterAgentState:
        """Generate final summary and action items."""
        state["current_state"] = AgentState.SUMMARIZE

        sub_results = state.get("sub_results") or {}
        group_chat_messages = state.get("group_chat_messages") or []

        if sub_results:
            if self.llm_router:
                try:
                    results_list = [
                        {"agent_name": str(k), "output": v.get("output")}
                        for k, v in sub_results.items()
                    ]
                    summary = await self.llm_router.generate_summary(
                        results_list,
                        provider_id=state.get("provider_id"),
                        summarizer_prompt_override=state.get("summarizer_prompt_override"),
                        temperature_override=state.get("temperature_override"),
                        model_override=state.get("model_override"),
                    )
                    # Prefer structured payload when the router returns one.
                    if isinstance(summary, dict):
                        state["final_summary"] = summary.get("summary") or json.dumps(
                            summary, ensure_ascii=False)
                        if summary.get("action_items"):
                            state["action_items"] = list(summary["action_items"])
                        if summary.get("risk_score") is not None:
                            state["risk_score"] = float(summary["risk_score"])
                    else:
                        state["final_summary"] = summary
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
            # Keep validation-derived risk/action_items when the LLM did not
            # overwrite them (and when validation never ran, fall back).
            if state.get("risk_score") is None:
                state["risk_score"] = 0.5
            if not state.get("action_items"):
                state["action_items"] = ["Review agent outputs"]
            if state.get("validation_errors"):
                errs = "; ".join(state["validation_errors"])
                state["final_summary"] = (
                    f"{state.get('final_summary') or ''}\n\n[validation] {errs}"
                ).strip()
        elif group_chat_messages:
            state["final_summary"] = "\n".join(
                f"{m['role']}: {m['content']}"
                for m in group_chat_messages[-5:]
            )
            state.setdefault("risk_score", 0.3)
            state.setdefault("action_items", ["Review group discussion"])
        elif self.llm_router:
            user_input = state.get("user_input", "")
            logger.debug("_summarizer_node: llm_router exists, calling chat()...")
            try:
                system_prompt = await self.llm_router.build_chat_system_prompt(
                    base_prompt=state.get("system_prompt_override"),
                    mode=state.get("mode"),
                    expert_no_agents=bool(state.get("expert_mode_no_agents")),
                )
                history = state.get("conversation_history") or []
                history, _compressed, _degraded = await maybe_compress(history, self.llm_router)
                state["context_compression"] = {
                    "compressed": _compressed, "degraded": _degraded,
                }
                messages: List[Dict[str, str]] = [
                    {"role": "system", "content": system_prompt}
                ]
                messages.extend(history)
                messages.append({"role": "user", "content": user_input})
                state["final_summary"] = await self.llm_router.chat(
                    messages=messages,
                    provider_id=state.get("provider_id"),
                    model=state.get("model"),
                    model_override=state.get("model_override"),
                    temperature_override=state.get("temperature_override"),
                )
            except Exception as e:
                logger.warning(f"_summarizer_node chat() exception: {e}")
                state["final_summary"] = f"无法处理您的请求，请检查 AI Provider 配置。错误: {e}"
            state.setdefault("risk_score", 0.2)
            state.setdefault("action_items", [])
        else:
            logger.debug("_summarizer_node: llm_router is None, returning fallback message")
            state["final_summary"] = "暂无 AI Provider 可用，请先在「AI Provider 配置」页面中添加一个 Provider。"
            state.setdefault("risk_score", 0.0)
            state.setdefault("action_items", [])

        state["current_state"] = AgentState.END
        state["interrupted"] = False
        return state

    async def _approval_node(self, state: MasterAgentState) -> MasterAgentState:
        """Human-in-the-loop approval via LangGraph ``interrupt()`` (#19/#20).

        Creates a DB approval record, then suspends the graph. The worker
        returns immediately with ``interrupted=True``; when an admin decides,
        ``MasterAgent.resume`` feeds the decision back through ``Command``.

        ``interrupt()`` re-runs the node from the top on resume *and discards
        the writes it made before suspending*, so "create only once" cannot be a
        state flag — on resume the flag is gone and we would open a duplicate,
        leaving a dangling pending approval behind every approved run.
        Idempotency therefore comes from a deterministic per-round request_id
        that is looked up before creating.
        """
        state["current_state"] = AgentState.HUMAN_APPROVAL

        # Already decided *for this gate* (e.g. AUTO_APPROVE settled it before
        # the interrupt). A decision from an earlier gate must not short-circuit
        # this one, so the check is round-scoped rather than status-only.
        if state.get("approval_status") in ("rejected", "expired") or \
                self._approval_is_current(state):
            return state

        run_request_id = state.get("request_id") or str(uuid.uuid4())
        state["request_id"] = run_request_id
        # Each gate in a run gets its own approval; the round is bumped by the
        # executor node when it retires a spent decision.
        approval_round = int(state.get("approval_round") or 0)
        request_id = approval_request_id(run_request_id, approval_round)
        state["approval_request_id"] = request_id

        from app.config import settings
        from app.services.approval_service import ApprovalService

        existing = None
        try:
            existing = await ApprovalService.get_by_request_id(request_id)
        except Exception as e:                      # noqa: BLE001
            logger.warning("[approval] lookup of %s failed: %s", request_id, e)

        if existing is not None:
            state["approval_record_id"] = existing.id
        else:
            sub_results = state.get("sub_results") or {}
            risk_keywords = [
                "critical", "emergency", "delete", "deploy", "drop", "truncate",
                "严重", "紧急", "删除", "部署",
            ]
            risk_level = "high" if any(
                kw in str(sub_results).lower() or kw in str(state.get("user_input", "")).lower()
                for kw in risk_keywords
            ) else "medium"
            if state.get("risk_score") is not None and state["risk_score"] >= 0.7:
                risk_level = "high"

            if sub_results:
                descriptions = [
                    f"{k}: {str(v.get('output', ''))[:200]}"
                    for k, v in sub_results.items()
                    if isinstance(v, dict) and v.get("status") == "needs_approval"
                ]
                action_description = (
                    "; ".join(descriptions) or "Agent execution requires approval"
                )
            else:
                task_plan = state.get("task_plan") or []
                action_description = "; ".join(
                    t.get("task", "")[:200] for t in task_plan if t.get("requires_approval")
                ) or "Task requires human approval"

            try:
                record = await ApprovalService.create_request(
                    request_id=request_id,
                    user_id=state.get("user_id") or 0,
                    action_type="agent_execution",
                    action_description=action_description,
                    agent_id=None,
                    payload={
                        "sub_results": sub_results,
                        "task_plan": state.get("task_plan"),
                        "user_input": state.get("user_input"),
                        "thread_id": state.get("thread_id") or request_id,
                        "execution_id": state.get("execution_id"),
                        "conversation_id": state.get("conversation_id"),
                        "risk_score": state.get("risk_score"),
                        "validation_errors": state.get("validation_errors"),
                    },
                    risk_level=risk_level,
                    urgency="urgent" if risk_level == "high" else "normal",
                    expires_in_minutes=60,
                )
                state["approval_record_id"] = record.id
            except Exception as e:
                logger.error("[approval] Failed to create DB record: %s", e)

            if settings.AUTO_APPROVE:
                try:
                    await ApprovalService.decide(
                        request_id, "approved", approver_id=0,
                        comment="Auto-approved by system",
                    )
                except Exception as e:
                    logger.warning("[approval] AUTO_APPROVE decide failed: %s", e)
                state["approval_status"] = "approved"
                state["approval_comment"] = "Auto-approved by system"
                state["approval_granted_round"] = approval_round
                state["approval_required"] = False
                state["pre_approved"] = True
                state["validation_passed"] = True
                return state

        # Suspend here. Resume value: {"status": "approved"|"rejected", "comment": ...}
        decision = interrupt({
            "kind": "approval",
            "request_id": request_id,
            "approval_record_id": state.get("approval_record_id"),
            "action": "agent_execution",
        })

        if isinstance(decision, dict):
            status = decision.get("status") or decision.get("decision") or "rejected"
            comment = decision.get("comment")
        else:
            status = str(decision or "rejected")
            comment = None

        state["approval_status"] = status
        state["approval_comment"] = comment
        state["interrupted"] = False

        if status == "approved":
            # Scope the decision to this gate; the executor spends it and bumps
            # the round, so the next gate has to ask again.
            state["approval_granted_round"] = approval_round
            state["approval_required"] = False
            state["pre_approved"] = True
            state["validation_passed"] = True
            state["current_state"] = AgentState.SUMMARIZE
        else:
            state["validation_passed"] = False
            state["error_message"] = f"Approval {status}: {comment or 'no comment'}"
            state["current_state"] = AgentState.ERROR

        return state

    async def _error_node(self, state: MasterAgentState) -> MasterAgentState:
        """Terminal error node — reachable from approval rejection."""
        state["current_state"] = AgentState.ERROR
        state["interrupted"] = False
        if not state.get("final_summary"):
            state["final_summary"] = state.get("error_message") or "Run failed"
        return state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _thread_config(self, thread_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    async def run(self, user_input: str, user_id: int, **kwargs) -> Dict[str, Any]:
        """Run the master agent with user input.

        When the graph suspends on approval, the returned dict has
        ``interrupted=True`` and ``approval_status="pending"`` — the caller
        (Celery task) must mark the execution as waiting rather than complete.
        """
        from app.core.langfuse_tracing import trace_run
        from app.core.graph_checkpoint import open_checkpointer

        request_id = kwargs.pop("request_id", None) or str(uuid.uuid4())
        thread_id = kwargs.pop("thread_id", None) or request_id
        execution_id = kwargs.get("execution_id")

        initial_state: Dict[str, Any] = {
            "user_input": user_input,
            "user_id": user_id,
            "current_state": AgentState.START,
            "group_chat_active": False,
            "request_id": request_id,
            "thread_id": thread_id,
            "execution_id": execution_id,
            "replan_count": 0,
            "max_replans": kwargs.pop("max_replans", _DEFAULT_MAX_REPLANS),
            "pre_approved": False,
            "interrupted": False,
            **kwargs,
        }

        session_id = str(kwargs.get("conversation_id") or uuid.uuid4())
        config = self._thread_config(thread_id)

        async def _invoke(checkpointer):
            graph = self._build_graph(checkpointer)
            with trace_run(session_id=session_id, agent_name="master", user_id=user_id):
                return await graph.ainvoke(initial_state, config=config)

        if self._checkpointer is not None:
            result = await _invoke(self._checkpointer)
        else:
            async with open_checkpointer() as checkpointer:
                result = await _invoke(checkpointer)

        return self._normalize_result(result, thread_id=thread_id, request_id=request_id)

    async def resume(
        self,
        thread_id: str,
        *,
        decision: str,
        comment: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Resume a graph suspended on approval (``Command(resume=...)``)."""
        from app.core.langfuse_tracing import trace_run
        from app.core.graph_checkpoint import open_checkpointer

        resume_value = {"status": decision, "comment": comment}
        config = self._thread_config(thread_id)

        async def _invoke(checkpointer):
            graph = self._build_graph(checkpointer)
            with trace_run(
                session_id=thread_id,
                agent_name="master",
                user_id=user_id or 0,
            ):
                return await graph.ainvoke(Command(resume=resume_value), config=config)

        if self._checkpointer is not None:
            result = await _invoke(self._checkpointer)
        else:
            async with open_checkpointer() as checkpointer:
                result = await _invoke(checkpointer)

        return self._normalize_result(
            result, thread_id=thread_id,
            request_id=(result or {}).get("request_id") or thread_id,
        )

    def _normalize_result(
        self, result: Dict[str, Any], *, thread_id: str, request_id: str,
    ) -> Dict[str, Any]:
        """Flag interrupted runs so the worker does not mark them completed."""
        if not isinstance(result, dict):
            return {"final_summary": str(result), "thread_id": thread_id,
                    "request_id": request_id}

        interrupts = result.get("__interrupt__") or []
        if interrupts:
            result = dict(result)
            result["interrupted"] = True
            result["approval_status"] = result.get("approval_status") or "pending"
            result["current_state"] = AgentState.HUMAN_APPROVAL
            result["thread_id"] = thread_id
            result["request_id"] = request_id
            # Drop the non-JSON-friendly Interrupt objects for Celery/DB storage.
            result["interrupt_payload"] = [
                getattr(i, "value", i) for i in interrupts
            ]
            result.pop("__interrupt__", None)
        else:
            result = dict(result)
            result.setdefault("interrupted", False)
            result.setdefault("thread_id", thread_id)
            result.setdefault("request_id", request_id)
            result.pop("__interrupt__", None)
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
