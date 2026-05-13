"""Chat and Master Agent invocation router."""
import uuid
import base64
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, rate_limit, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.core.guardrails import check_prompt_sync, GuardrailResult
from app.schemas.chat import ChatAttachmentsResponse, ChatRequest, ChatResponse
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
            "agent_id": body.agent_id,
        },
    )

    return ChatResponse(
        task_id=execution_id,
        status="pending",
        message="Task dispatched to worker",
    )


ALLOWED_ATTACHMENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file


@router.post("/chat/attachments", response_model=ChatAttachmentsResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat_attachments(
    message: str = Form(...),
    conversation_id: Optional[int] = Form(None),
    agent_id: Optional[str] = Form(None),
    provider_id: Optional[int] = Form(None),
    model: Optional[str] = Form(None),
    mode: Optional[str] = Form("normal"),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        rate_limit(requests_per_minute=30, requests_per_hour=500, burst_limit=5)(
            require_permission(Permission.TASK_EXECUTE)
        )
    ),
):
    """
    Submit a task with file attachments to the Master Agent via Celery worker.

    Accepts up to 10 files. Supported types: images (png/jpeg/gif/webp),
    documents (pdf, doc, docx, txt, md, csv, json, xls, xlsx, ppt, pptx).
    File contents are base64-encoded and passed to the worker via kwargs.
    """
    user_id = current_user.user_id

    # Validate max 10 files
    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 files allowed per request",
        )

    # Validate file types and encode as base64
    attachments = []
    for f in files:
        if f.content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {f.content_type}. Allowed: {', '.join(sorted(ALLOWED_ATTACHMENT_TYPES))}",
            )
        # Check file size before reading into memory
        if f.size is not None and f.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{f.filename}' exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB",
            )
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{f.filename}' exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB",
            )
        attachments.append(
            {
                "filename": f.filename,
                "content_type": f.content_type,
                "data": base64.b64encode(content).decode("utf-8"),
            }
        )

    # P1-4: Prompt injection guardrail
    guardrail_result: GuardrailResult = check_prompt_sync(message)
    if guardrail_result.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Input blocked by security filter: {guardrail_result.message} "
                f"(risk={guardrail_result.risk_level}, score={guardrail_result.score})"
            ),
        )

    # Create execution record
    execution_id = str(uuid.uuid4())
    agent_id_for_exec = None
    execution = AgentExecution(
        execution_id=execution_id,
        agent_id=agent_id_for_exec,
        status="pending",
        input_data={
            "user_input": message,
            "mode": "normal",
            "provider_id": provider_id,
            "model": model,
            "agent_id": agent_id,
            "attachments": attachments,
        },
    )
    db.add(execution)
    await db.commit()

    # Dispatch to Celery worker
    # NOTE: run_master_agent_task accepts **kwargs, so attachments can be passed
    # via kwargs. However, the task does not yet process attachments — it will
    # need to be updated separately to handle the 'attachments' kwarg.
    from app.workers.tasks import run_master_agent_task
    run_master_agent_task.apply_async(
        args=[execution_id, message, user_id],
        kwargs={
            "mode": mode or "normal",
            "provider_id": provider_id,
            "model": model,
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "attachments": attachments,
        },
    )

    return ChatAttachmentsResponse(
        task_id=execution_id,
        status="pending",
        message="Task with attachments dispatched to worker",
    )
