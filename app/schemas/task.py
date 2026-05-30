"""Pydantic schemas for task management."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TaskPriority(str, Enum):
    """Task priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    """Task status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskBase(BaseModel):
    """Base task schema."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM


class TaskCreate(TaskBase):
    """Task creation schema."""
    agent_id: Optional[int] = None
    input_data: Optional[Dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None


class TaskUpdate(BaseModel):
    """Task update schema."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    output_data: Optional[Dict[str, Any]] = None


class ExecutionRead(BaseModel):
    """Execution record schema matching AgentExecution ORM model."""
    id: int
    execution_id: str
    agent_id: Optional[int]
    status: str
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    """Task response schema."""
    id: int
    title: str
    description: Optional[str]
    status: str
    priority: str
    agent_id: Optional[int]
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    """Paginated task list response."""
    total: int
    tasks: list[TaskResponse]


class TaskExecuteRequest(BaseModel):
    """Task execution request schema."""
    task_id: int
    input_override: Optional[Dict[str, Any]] = None


class TaskExecuteResponse(BaseModel):
    """Task execution response schema."""
    task_id: int
    execution_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None

# Aliases
TaskRead = TaskResponse
