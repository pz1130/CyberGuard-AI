"""LangGraph Master Agent state definitions."""
from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class AgentState(str, Enum):
    """Agent execution states."""
    START = "start"
    PARSE_INTENT = "parse_intent"
    ROUTE_TO_SUB = "route_to_sub"
    WAIT_FOR_SUB_RESULTS = "wait_for_sub_results"
    VALIDATE_RESULTS = "validate_results"
    SUMMARIZE = "summarize"
    HUMAN_APPROVAL = "human_approval"
    END = "end"
    ERROR = "error"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


class MasterAgentState(TypedDict, total=False):
    """State dict for LangGraph Master Agent."""

    # User input
    user_input: str
    user_id: int

    # Parsed intent
    intent: Optional[str]
    task_plan: Optional[List[Dict[str, Any]]]  # [{"agent_type": "threat_intel", "task": "...", "requires_approval": false}]

    # Sub-agent results
    sub_results: Dict[int, Any]  # agent_id -> result

    # Current state
    current_state: AgentState

    # Validation
    validation_passed: bool
    validation_errors: List[str]

    # Final output
    final_summary: Optional[str]
    risk_score: Optional[float]
    action_items: List[str]

    # Context-compression observability (set when maybe_compress runs)
    context_compression: Dict[str, bool]

    # Human approval
    approval_required: bool
    approval_status: Optional[str]  # approved, rejected, pending, expired
    approval_comment: Optional[str]
    approval_record_id: Optional[int]
    # Which gate of this run we are on. A decision is valid only for the round
    # it was granted in, so one approval cannot stand in for every later gate.
    approval_round: int
    approval_granted_round: Optional[int]
    approval_request_id: Optional[str]
    # Set after a human approves; consumed by the next dispatch and then cleared.
    pre_approved: bool
    # True while the graph is suspended on interrupt() awaiting a human.
    interrupted: bool
    # Checkpoint thread — how a different process finds this run to resume it.
    thread_id: Optional[str]
    execution_id: Optional[str]

    # Error handling
    error_message: Optional[str]

    # Metadata
    request_id: str

    # LLM provider selection
    provider_id: Optional[int]
    model: Optional[str]
    timestamp: str

    # Explicit sub-agent selection from the WebUI (bypasses intent parsing)
    agent_id: Optional[str]

    # Chat dispatch mode: "normal" (LLM decides) | "fast" (master only)
    # | "expert" (fan out to all active sub-agents)
    mode: Optional[str]

    # INV-23 nesting: master turn starts at 0; sub-agent-spawned plans would be 1+
    dispatch_depth: Optional[int]

    # Conversation history (list of {"role": "user"/"assistant", "content": str})
    # Injected from the conversations table so the LLM has multi-turn memory
    conversation_history: Optional[List[Dict[str, Any]]]

    # Conversation ID — used to thread memory slices for internal agents
    conversation_id: Optional[int]

    # Per-conversation config overrides
    system_prompt_override: Optional[str]
    intent_parser_prompt_override: Optional[str]
    summarizer_prompt_override: Optional[str]
    model_override: Optional[str]
    temperature_override: Optional[float]


class SubAgentResult(TypedDict):
    """Result from a sub-agent execution."""
    agent_id: int
    agent_name: str
    status: str
    output: Optional[Any]
    error: Optional[str]
    execution_time: float
    timestamp: str
