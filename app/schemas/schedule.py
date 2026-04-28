"""Pydantic schemas for scheduled tasks and cron jobs."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ScheduleBase(BaseModel):
    """Base schedule schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    cron_expression: str = Field(..., description="Cron expression (e.g., '0 * * * *')")
    task_type: str = Field(..., description="agent_execution, backup, report_generation")


class ScheduleCreate(ScheduleBase):
    """Schedule creation schema."""
    agent_id: Optional[int] = None
    task_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    run_immediately: bool = False


class ScheduleUpdate(BaseModel):
    """Schedule update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    cron_expression: Optional[str] = None
    task_type: Optional[str] = None
    agent_id: Optional[int] = None
    task_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ScheduleResponse(BaseModel):
    """Schedule response schema."""
    id: int
    name: str
    description: Optional[str]
    cron_expression: str
    task_type: str
    agent_id: Optional[int]
    task_config: Dict[str, Any]
    is_active: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduleExecutionResponse(BaseModel):
    """Schedule execution response schema."""
    execution_id: str
    schedule_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ScheduleListResponse(BaseModel):
    """Paginated schedule list response."""
    total: int
    schedules: list[ScheduleResponse]

# Aliases
ScheduleTaskCreate = ScheduleCreate
ScheduleTaskRead = ScheduleResponse
ScheduleTaskListResponse = ScheduleListResponse
