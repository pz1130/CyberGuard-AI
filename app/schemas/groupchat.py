"""Pydantic schemas for agent group chat."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class GroupChatMessageResponse(BaseModel):
    """Group chat message response schema."""
    role: str
    content: str
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    timestamp: str


class GroupChatSessionResponse(BaseModel):
    """Group chat session response schema."""
    session_id: str
    user_id: int
    agent_ids: List[int]
    status: str
    current_round: int
    max_rounds: int
    messages: List[GroupChatMessageResponse]
    created_at: str
    # True while a background completion run is in flight; the frontend polls
    # the session until this flips to false.
    running: bool = False


class GroupChatCreateRequest(BaseModel):
    """Group chat creation request schema."""
    agent_ids: List[int] = Field(..., min_length=1)
    initial_message: str = Field(..., min_length=1)
    max_rounds: int = Field(default=5, ge=1, le=20)


class GroupChatAddMessageRequest(BaseModel):
    """Group chat message addition request schema."""
    session_id: str
    content: str
    role: str = "user"
    agent_id: Optional[int] = None


class GroupChatRunRoundRequest(BaseModel):
    """Group chat round run request schema."""
    session_id: str


class GroupChatRunToCompletionRequest(BaseModel):
    """Group chat run to completion request schema."""
    session_id: str


class GroupChatRoundResponse(BaseModel):
    """Group chat round response schema."""
    session_id: str
    round: int
    responses: List[Dict[str, Any]]


class GroupChatCancelRequest(BaseModel):
    """Group chat cancellation request schema."""
    session_id: str