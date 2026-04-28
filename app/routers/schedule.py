"""Scheduled tasks router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.schemas.schedule import ScheduleTaskCreate, ScheduleTaskRead, ScheduleTaskListResponse
from app.schemas.task import TaskStatus
from app.models.agent import AgentExecution
from sqlalchemy import select, func
from datetime import datetime
import uuid

router = APIRouter()


# In-memory store for MVP (replace with DB table in production)
_scheduled_tasks = {}


@router.get("/schedule", response_model=ScheduleTaskListResponse)
async def list_scheduled_tasks(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_READ)),
):
    """List all scheduled tasks."""
    tasks = list(_scheduled_tasks.values())
    return ScheduleTaskListResponse(total=len(tasks), tasks=[ScheduleTaskRead(**t) for t in tasks])


@router.post("/schedule", response_model=ScheduleTaskRead, status_code=201)
async def create_scheduled_task(
    body: ScheduleTaskCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_WRITE)),
):
    """Create a new scheduled task."""
    task_id = str(uuid.uuid4())
    task_data = {
        "id": task_id,
        "name": body.name,
        "cron_expression": body.cron_expression,
        "task_type": body.task_type,
        "payload": body.payload,
        "enabled": body.enabled,
        "created_at": datetime.utcnow().isoformat(),
    }
    _scheduled_tasks[task_id] = task_data
    return ScheduleTaskRead(**task_data)


@router.get("/schedule/{task_id}", response_model=ScheduleTaskRead)
async def get_scheduled_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_READ)),
):
    """Get scheduled task by ID."""
    if task_id not in _scheduled_tasks:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return ScheduleTaskRead(**_scheduled_tasks[task_id])


@router.delete("/schedule/{task_id}", status_code=204)
async def delete_scheduled_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_WRITE)),
):
    """Delete scheduled task."""
    if task_id not in _scheduled_tasks:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    del _scheduled_tasks[task_id]
