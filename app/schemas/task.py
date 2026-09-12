"""Pydantic schemas for asynchronous execution tracking."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ExecutionRead(BaseModel):
    """Execution record schema matching AgentExecution ORM model."""
    id: int
    execution_id: str
    agent_id: Optional[int]
    status: str
    input_data: Optional[dict[str, Any]]
    output_data: Optional[dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    """Paginated execution list."""
    total: int
    tasks: list[ExecutionRead]
