"""Chat and Master Agent invocation router."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, rate_limit, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.core.guardrails import check_prompt_sync, GuardrailResult
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.task import TaskRead, TaskStatus
from app.models.agent import AgentExecution

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        rate_limit(requests_per_minute=30, requests_per_hour=500, burst_limit=5)(
            require_permission(Permission.TASK_EXECUTE)
        )
    ),
):
    """
    Submit a task to the Master Agent via Celery worker.
    Returns a task_id (execution_id) for polling the result.
    The Master Agent will parse intent, route to sub-agents, and return results.
    """
    user_id = current_user.user_id

    # P1-4: Prompt injection guardrail (synchronous, no LLM classifier in REST path)
    guardrail_result: GuardrailResult = check_prompt_sync(body.message)
    if guardrail_result.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Input blocked by security filter: {guardrail_result.message} "
                f"(risk={guardrail_result.risk_level}, score={guardrail_result.score})"
            ),
        )
    # Log medium/high risk (non-blocking) for audit
    if guardrail_result.risk_level in ("high", "critical"):
        import logging
        logging.getLogger(__name__).warning(
            f"[guardrail] user_id={user_id} risk={guardrail_result.risk_level} "
            f"score={guardrail_result.score} flags={guardrail_result.flags} "
            f"message={guardrail_result.message}"
        )

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

    # Dispatch to Celery worker — returns immediately with 202
    from app.workers.tasks import run_master_agent_task
    run_master_agent_task.apply_async(
        args=[execution_id, body.message, user_id],
        kwargs={
            "mode": body.mode or "normal",
            "provider_id": body.provider_id,
            "model": body.model,
            "conversation_id": body.conversation_id,
        },
    )

    return ChatResponse(
        task_id=execution_id,
        status="pending",
        message="Task dispatched to worker",
    )
