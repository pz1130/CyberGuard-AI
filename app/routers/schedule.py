"""Scheduled tasks router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.schemas.schedule import ScheduleTaskCreate, ScheduleTaskRead, ScheduleTaskListResponse
from app.models.schedule import ScheduledTask
from sqlalchemy import select
from datetime import datetime, timezone
import uuid

router = APIRouter()


@router.get("/schedule", response_model=ScheduleTaskListResponse)
async def list_scheduled_tasks(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_READ)),
):
    """List all scheduled tasks."""
    result = await db.execute(select(ScheduledTask))
    tasks = result.scalars().all()
    return ScheduleTaskListResponse(total=len(tasks), schedules=[ScheduleTaskRead.model_validate(t) for t in tasks])


@router.post("/schedule", response_model=ScheduleTaskRead, status_code=201)
async def create_scheduled_task(
    body: ScheduleTaskCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_WRITE)),
):
    """Create a new scheduled task."""
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    task = ScheduledTask(
        task_id=task_id,
        name=body.name,
        description=body.description,
        cron_expression=body.cron_expression,
        task_type=body.task_type,
        agent_id=body.agent_id,
        task_config=body.task_config,
        is_active=body.is_active,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return ScheduleTaskRead.model_validate(task)


@router.get("/schedule/{task_id}", response_model=ScheduleTaskRead)
async def get_scheduled_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_READ)),
):
    """Get scheduled task by ID (task_id is UUID string)."""
    result = await db.execute(select(ScheduledTask).where(ScheduledTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return ScheduleTaskRead.model_validate(task)


@router.put("/schedule/{task_id}", response_model=ScheduleTaskRead)
async def update_scheduled_task(
    task_id: str,
    body: ScheduleTaskCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_WRITE)),
):
    """Update an existing scheduled task."""
    result = await db.execute(select(ScheduledTask).where(ScheduledTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)
    return ScheduleTaskRead.model_validate(task)


@router.delete("/schedule/{task_id}", status_code=204)
async def delete_scheduled_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_WRITE)),
):
    """Delete scheduled task."""
    result = await db.execute(select(ScheduledTask).where(ScheduledTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    await db.delete(task)
    await db.commit()
