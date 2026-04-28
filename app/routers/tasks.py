"""Task execution tracking router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.schemas.task import TaskRead, TaskListResponse
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
    return TaskListResponse(total=total, tasks=[TaskRead.model_validate(t) for t in tasks])


@router.get("/tasks/{task_id}", response_model=TaskRead)
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
    return TaskRead.model_validate(task)
