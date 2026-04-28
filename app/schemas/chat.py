"""Pydantic schemas for chat and messaging."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatMessageRequest(BaseModel):
    """Chat message request schema."""
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ChatMessageResponse(BaseModel):
    """Chat message response schema."""
    session_id: str
    message: str
    agent_response: Optional[str] = None
    intent: Optional[str] = None
    task_plan: Optional[List[Dict[str, Any]]] = None
    risk_score: Optional[float] = None
    requires_approval: bool = False
    timestamp: str


class ChatSessionResponse(BaseModel):
    """Chat session response schema."""
    session_id: str
    messages: List[Dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime


class IntentParsingRequest(BaseModel):
    """Intent parsing request schema."""
    user_input: str = Field(..., min_length=1)


class IntentParsingResponse(BaseModel):
    """Intent parsing response schema."""
    intent: str
    task_plan: List[Dict[str, Any]]
    reasoning: str


class GroupChatCreateRequest(BaseModel):
    """Group chat creation request schema."""
    agent_ids: List[int] = Field(..., min_length=1)
    initial_message: str = Field(..., min_length=1)
    max_rounds: int = Field(default=5, ge=1, le=20)


class GroupChatMessageRequest(BaseModel):
    """Group chat message addition request schema."""
    session_id: str
    content: str
    role: str = "user"


class GroupChatResponse(BaseModel):
    """Group chat response schema."""
    session_id: str
    status: str
    messages: List[Dict[str, Any]]
    current_round: int
    max_rounds: int


class GroupChatRoundResponse(BaseModel):
    """Group chat round response schema."""
    session_id: str
    round: int
    responses: List[Dict[str, Any]]


class AgentChatRequest(BaseModel):
    """Direct agent chat request schema."""
    agent_id: int
    message: str
    context: Optional[Dict[str, Any]] = None


class AgentChatResponse(BaseModel):
    """Direct agent chat response schema."""
    agent_id: int
    agent_name: str
    response: str
    status: str

# Aliases
ChatRequest = AgentChatRequest
ChatResponse = AgentChatResponse
