"""LangGraph Master Agent implementation."""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.agents.states import MasterAgentState, AgentState, SubAgentResult
from app.services.agent_executor import AgentExecutor
from app.core.audit import log_audit


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
            return "end"

        # Check if any task requires approval
        for task in task_plan:
            if task.get("requires_approval", False):
                state["approval_required"] = True
                return "approval"

        return "sub_agents"

    def _validation_decision(self, state: MasterAgentState) -> str:
        """Decide based on validation result."""
        if state.get("validation_passed", False):
            return "approved"
        return "rejected"

    async def _start_node(self, state: MasterAgentState) -> MasterAgentState:
        """Start node - initialize state."""
        state["current_state"] = AgentState.START
        state["request_id"] = str(uuid.uuid4())
        state["timestamp"] = datetime.utcnow().isoformat()
        state["sub_results"] = {}
        state["group_chat_messages"] = []
        return state

    async def _parse_intent_node(self, state: MasterAgentState) -> MasterAgentState:
        """Parse user intent and create task plan."""
        state["current_state"] = AgentState.PARSE_INTENT

        user_input = state.get("user_input", "")
        user_id = state.get("user_id")

        # Use LLM to parse intent if available
        if self.llm_router and user_input:
            try:
                parsed = await self.llm_router.parse_intent(user_input)
                state["intent"] = parsed.get("intent")
                state["task_plan"] = parsed.get("task_plan", [])
            except Exception as e:
                state["error_message"] = f"Intent parsing failed: {e}"
                return state

        # Check for group chat trigger
        if any(keyword in user_input.lower() for keyword in ["group chat", "discuss", "all agents"]):
            state["group_chat_active"] = True

        # Log audit
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
        """Route tasks to sub-agents."""
        state["current_state"] = AgentState.ROUTE_TO_SUB

        task_plan = state.get("task_plan", [])
        if task_plan:
            # Mark which agents need to be called
            state["pending_agents"] = [t["agent_id"] for t in task_plan]

        return state

    async def _sub_agent_executor_node(self, state: MasterAgentState) -> MasterAgentState:
        """Execute tasks on sub-agents."""
        state["current_state"] = AgentState.WAIT_FOR_SUB_RESULTS

        task_plan = state.get("task_plan", [])
        user_id = state.get("user_id")
        request_id = state.get("request_id")

        results = dict(state.get("sub_results", {}))

        for task in task_plan:
            agent_id = task["agent_id"]
            task_description = task["task"]

            # Execute sub-agent
            result = await self.executor.execute(
                agent_id=agent_id,
                task=task_description,
                user_id=user_id,
            )

            results[agent_id] = result

            # Log audit
            await log_audit(
                user_id=user_id,
                agent_id=str(agent_id),
                action="sub_agent_execute",
                input_data={"task": task_description},
                output_data=result,
                request_id=request_id,
            )

            # Check for approval requirement
            if result.get("status") == "needs_approval":
                state["approval_required"] = True

        state["sub_results"] = results
        state["current_state"] = AgentState.VALIDATE_RESULTS
        return state

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
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Round-robin through agents
        for task in task_plan:
            agent_id = task["agent_id"]
            result = await self.executor.execute(
                agent_id=agent_id,
                task=f"Group chat response to: {user_input}",
                user_id=user_id,
            )

            messages.append({
                "role": "agent",
                "agent_id": agent_id,
                "content": result.get("output", ""),
                "timestamp": datetime.utcnow().isoformat(),
            })

        state["group_chat_messages"] = messages
        state["current_state"] = AgentState.SUMMARIZE
        return state

    async def _validation_node(self, state: MasterAgentState) -> MasterAgentState:
        """Validate sub-agent results for consistency and hallucinations."""
        state["current_state"] = AgentState.VALIDATE_RESULTS

        sub_results = state.get("sub_results", {})

        errors = []
        passed = True

        # Basic validation
        for agent_id, result in sub_results.items():
            if result.get("status") == "failed":
                errors.append(f"Agent {agent_id} failed: {result.get('error')}")
                passed = False

        # Check for high-risk indicators
        for agent_id, result in sub_results.items():
            output = str(result.get("output", ""))
            if any(kw in output.lower() for kw in ["critical", "emergency", "immediate action"]):
                # Flag for human review
                state["approval_required"] = True

        state["validation_passed"] = passed
        state["validation_errors"] = errors
        return state

    async def _summarizer_node(self, state: MasterAgentState) -> MasterAgentState:
        """Generate final summary and action items."""
        state["current_state"] = AgentState.SUMMARIZE

        sub_results = state.get("sub_results", {})
        group_chat_messages = state.get("group_chat_messages", [])

        # Build summary from results
        if sub_results:
            summary_parts = []
            for agent_id, result in sub_results.items():
                summary_parts.append(f"Agent {agent_id}: {result.get('output', 'No output')}")
            state["final_summary"] = "\n\n".join(summary_parts)
        elif group_chat_messages:
            # Summarize group chat
            state["final_summary"] = "\n".join([
                f"{m['role']}: {m['content']}"
                for m in group_chat_messages[-5:]  # Last 5 messages
            ])

        # Calculate risk score (simplified)
        state["risk_score"] = 0.5  # Default medium risk

        state["action_items"] = [
            "Review agent outputs",
            "Validate findings",
        ]

        state["current_state"] = AgentState.END
        return state

    async def _approval_node(self, state: MasterAgentState) -> MasterAgentState:
        """Handle human approval for high-risk operations."""
        state["current_state"] = AgentState.HUMAN_APPROVAL
        state["approval_status"] = "pending"

        # This would typically block and wait for human input
        # For now, mark as requiring approval
        return state

    async def _error_node(self, state: MasterAgentState) -> MasterAgentState:
        """Handle errors."""
        state["current_state"] = AgentState.ERROR
        return state

    async def run(self, user_input: str, user_id: int, **kwargs) -> Dict[str, Any]:
        """Run the master agent with user input."""
        initial_state = MasterAgentState(
            user_input=user_input,
            user_id=user_id,
            current_state=AgentState.START,
            group_chat_active=False,
            **kwargs,
        )

        result = await self.graph.ainvoke(initial_state)
        return result


# Singleton instance
_master_agent: Optional[MasterAgent] = None


def get_master_agent() -> MasterAgent:
    """Get or create master agent singleton."""
    global _master_agent
    if _master_agent is None:
        _master_agent = MasterAgent()
    return _master_agent