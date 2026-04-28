"""Chat and Master Agent invocation router."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.task import TaskRead, TaskStatus
from app.models.agent import AgentExecution
from app.agents.master import get_master_agent

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """
    Submit a task to the Master Agent.
    Returns a task_id for polling the result.
    The Master Agent will parse intent, route to sub-agents, and return results.
    """
    master_agent = get_master_agent()
    user_id = current_user.user_id

    # Create execution record
    execution_id = str(uuid.uuid4())
    agent_id_for_exec = None  # Master Agent has no agent_configs row
    execution = AgentExecution(
        execution_id=execution_id,
        agent_id=agent_id_for_exec,
        status="pending",
        input_data={"user_input": body.message, "mode": body.mode, "provider_id": body.provider_id, "model": body.model},
    )
    db.add(execution)
    await db.commit()

    # Run master agent (async, fire-and-forget for MVP; use task queue in production)
    try:
        result = await master_agent.run(
            user_input=body.message,
            user_id=user_id,
            mode=body.mode or "normal",
            provider_id=body.provider_id,
            model=body.model,
        )

        # Update execution with result
        execution.status = "completed"
        execution.output_data = result
        execution.completed_at = datetime.utcnow()
        await db.commit()

        return ChatResponse(
            task_id=execution_id,
            status="completed",
            message=result.get("final_summary", ""),
            intent=result.get("intent"),
            risk_score=result.get("risk_score"),
            action_items=result.get("action_items", []),
        )

    except Exception as e:
        execution.status = "failed"
        execution.error_message = str(e)
        execution.completed_at = datetime.utcnow()
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Master agent execution failed: {e}")
