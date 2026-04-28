"""LangGraph Master Agent state definitions."""
from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class AgentState(str, Enum):
    """Agent execution states."""
    START = "start"
    PARSE_INTENT = "parse_intent"
    ROUTE_TO_SUB = "route_to_sub"
    WAIT_FOR_SUB_RESULTS = "wait_for_sub_results"
    GROUP_CHAT_MODE = "group_chat_mode"
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
    task_plan: Optional[List[Dict[str, Any]]]  # [{"agent_id": 1, "task": "..."}]

    # Sub-agent results
    sub_results: Dict[int, Any]  # agent_id -> result

    # Current state
    current_state: AgentState

    # Group chat
    group_chat_active: bool
    group_chat_messages: List[Dict[str, Any]]

    # Validation
    validation_passed: bool
    validation_errors: List[str]

    # Final output
    final_summary: Optional[str]
    risk_score: Optional[float]
    action_items: List[str]

    # Human approval
    approval_required: bool
    approval_status: Optional[str]  # approved, rejected, pending
    approval_comment: Optional[str]

    # Error handling
    error_message: Optional[str]

    # Metadata
    request_id: str
    timestamp: str


class SubAgentResult(TypedDict):
    """Result from a sub-agent execution."""
    agent_id: int
    agent_name: str
    status: str
    output: Optional[Any]
    error: Optional[str]
    execution_time: float
    timestamp: str