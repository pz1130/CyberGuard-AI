"""Task execution tracking router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from celery.result import AsyncResult
from app.workers.celery_app import celery_app
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.time import utc_now
from app.schemas.task import ExecutionRead, TaskListResponse
from app.models.agent import AgentExecution
from sqlalchemy import select, func

router = APIRouter()


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_READ)),
):
    """List all task executions."""
    total_result = await db.execute(select(func.count(AgentExecution.id)))
    total = total_result.scalar()
    result = await db.execute(
        select(AgentExecution)
        .order_by(AgentExecution.created_at.desc())
        .offset(skip).limit(limit)
    )
    tasks = result.scalars().all()
    return TaskListResponse(total=total, tasks=[ExecutionRead.model_validate(t) for t in tasks])


@router.get("/tasks/{task_id}", response_model=ExecutionRead)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_READ)),
):
    """Get task execution result by task ID."""
    result = await db.execute(
        select(AgentExecution).where(AgentExecution.execution_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return ExecutionRead.model_validate(task)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.TASK_WRITE)),
):
    """Cancel/revoke a running Celery task by revoking it and updating DB status."""
    # Revoke the Celery task (ignore if already done)
    celery_app.control.revoke(task_id, terminate=True)

    # Update DB execution record to cancelled
    result = await db.execute(
        select(AgentExecution).where(AgentExecution.execution_id == task_id)
    )
    execution = result.scalar_one_or_none()
    if execution:
        execution.status = "cancelled"
        execution.completed_at = utc_now()
        await db.commit()

    return {"task_id": task_id, "status": "cancelled"}
