"""Celery tasks for background agent execution."""
import asyncio
import logging
import os
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from app.workers.celery_app import celery_app
from app.core.time import utc_now

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)
_worker_async_loop = None
_worker_async_loop_pid = None


def _run_worker_async(coro):
    """Run a coroutine on one persistent event loop per Celery child process.

    The worker previously created and closed a loop for every task while
    module-level async DB/Redis clients survived between tasks. Reusing those
    clients on the next loop caused "Event loop is closed" and fail-closed
    Kill Switch responses. Celery prefork children execute one task at a time,
    so a process-local loop keeps each async resource on its owning loop.
    """
    global _worker_async_loop, _worker_async_loop_pid

    pid = os.getpid()
    if (
        _worker_async_loop is None
        or _worker_async_loop.is_closed()
        or _worker_async_loop_pid != pid
    ):
        _worker_async_loop = asyncio.new_event_loop()
        _worker_async_loop_pid = pid

    asyncio.set_event_loop(_worker_async_loop)
    return _worker_async_loop.run_until_complete(coro)


def _update_execution_status_sync(execution_id: str, status: str):
    """Sync helper to update execution status using a sync DB session."""
    from app.core.database import get_sync_session
    from app.models.agent import AgentExecution
    from sqlalchemy import select

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        result = session.execute(
            select(AgentExecution).where(AgentExecution.execution_id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if execution:
            execution.status = status
            if status == "running":
                execution.started_at = utc_now()
            session.commit()


def _update_execution_with_result_sync(execution_id: str, status: str, result_data, error_msg: str | None):
    """Sync helper to update execution with result or error."""
    from app.core.database import get_sync_session
    from app.models.agent import AgentExecution
    from sqlalchemy import select

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        result = session.execute(
            select(AgentExecution).where(AgentExecution.execution_id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if execution:
            execution.status = status
            execution.completed_at = utc_now()
            if result_data is not None:
                execution.output_data = result_data
            if error_msg is not None:
                execution.error_message = error_msg
            session.commit()


def _query_knowledge_base_sync(kb_id: int, query: str, top_k: int = 5) -> str:
    """Query knowledge base via pgvector ANN and return formatted context (sync wrapper for Celery)."""
    async def _async_query():
        from app.services.knowledge_service import get_knowledge_service
        from app.core.database import get_db_context
        async with get_db_context() as session:
            results = await get_knowledge_service().query(
                db=session,
                kb_id=kb_id,
                query=query,
                top_k=top_k,
                similarity_threshold=0.0,
            )
        return results

    try:
        results = _run_worker_async(_async_query())

        if not results:
            return ""
        contexts = [
            f"[{r['filename']} chunk {r['chunk_index']}]\n{r['content'][:400]}"
            for r in results
        ]
        return "\n\n---\n\n".join(contexts)
    except Exception as e:
        logger.warning(f"[KB query] Failed to query KB {kb_id}: {e}")
        return ""


def _save_to_conversation_async(conversation_id: int, user_input: str, result: dict):
    """Save user message and result to conversation (fire-and-forget, row-locked)."""
    import json
    import re
    try:
        from app.core.database import get_sync_session
        from app.services.conversation_messages import append_messages_locked_sync

        final_summary = result.get("final_summary", "")
        if isinstance(final_summary, dict):
            final_summary = json.dumps(final_summary)
        # Last-mile safety net: strip internal chain-of-thought blocks
        if final_summary:
            final_summary = re.sub(
                r"<think[^>]*>[\s\S]*?</think>\s*", "", final_summary, flags=re.IGNORECASE
            ).strip()
            final_summary = re.sub(
                r"<reasoning>[\s\S]*?</reasoning>\s*", "", final_summary, flags=re.IGNORECASE
            ).strip()

        SessionLocal = get_sync_session()
        with SessionLocal() as session:
            conv, _ = append_messages_locked_sync(
                session,
                conversation_id,
                [
                    {"role": "user", "content": user_input},
                    {
                        "role": "assistant",
                        "content": final_summary or str(result),
                    },
                ],
            )
            if not conv:
                return
            session.commit()
    except Exception as e:
        logger.warning(f"Failed to save to conversation {conversation_id}: {e}")


def _run_async_master_agent(execution_id: str, user_input: str, user_id: int, **kwargs):
    """Run the async master agent on the process-local worker loop."""
    import asyncio
    from app.agents.master import get_master_agent
    from app.core.guardrails import check_prompt_sync, GuardrailResult

    # P1-4: Prompt injection guardrail at the Celery task entry (blocking)
    guardrail_result: GuardrailResult = check_prompt_sync(user_input)
    if guardrail_result.blocked:
        _update_execution_with_result_sync(
            execution_id, "failed", None,
            f"Prompt injection blocked: {guardrail_result.message}"
        )
        return {"error": "blocked", "guardrail": guardrail_result.message}

    # Load per-conversation config, history, and knowledge base context
    conversation_id = kwargs.get("conversation_id")
    rag_context = ""
    conv_overrides = {}
    conversation_history: list[dict] = []

    if conversation_id:
        from app.core.database import get_sync_session
        from app.models.conversation import Conversation
        from sqlalchemy import select
        import json as _json

        SessionLocal = get_sync_session()
        with SessionLocal() as session:
            result = session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()

        if conv:
            # RAG: query knowledge base for relevant context
            if conv.knowledge_base_id:
                rag_context = _query_knowledge_base_sync(conv.knowledge_base_id, user_input)
                if rag_context:
                    logger.info(
                        f"[run_master_agent_task] KB/{conv.knowledge_base_id} "
                        f"retrieved {len(rag_context)} chars of context"
                    )

            # Per-conversation prompt / model overrides
            if conv.system_prompt_override:
                conv_overrides["system_prompt_override"] = conv.system_prompt_override
            if conv.intent_parser_prompt_override:
                conv_overrides["intent_parser_prompt_override"] = conv.intent_parser_prompt_override
            if conv.summarizer_prompt_override:
                conv_overrides["summarizer_prompt_override"] = conv.summarizer_prompt_override
            if conv.temperature_override is not None:
                conv_overrides["temperature_override"] = conv.temperature_override

            # Conversation history: last 20 messages (10 turns) so the LLM has
            # memory without blowing the context window.
            from app.services.conversation_messages import (
                fetch_recent_sync, to_llm_turns,
            )
            with SessionLocal() as session:
                conversation_history = to_llm_turns(
                    fetch_recent_sync(session, conversation_id, 20))

    # Prepend RAG context to user input if retrieved
    if rag_context:
        user_input = f"[知识库检索结果]\n{rag_context}\n\n[用户问题]\n{user_input}"

    async def _run():
        # Drop inherited/pre-fork DB connections before this process uses its
        # persistent event loop. Disposal and all later DB work now happen on
        # that same loop.
        from app.core.database import engine
        await engine.dispose()

        run_input = user_input
        attachments = kwargs.get("attachments")
        if attachments:
            from app.config import settings
            from app.services.attachment_extractor import build_attachment_section
            from app.services.ocr_service import load_ocr_config
            cfg = await load_ocr_config()
            section = await build_attachment_section(
                attachments, cfg,
                per_cap=settings.ATTACHMENT_MAX_CHARS,
                total_cap=settings.ATTACHMENT_TOTAL_MAX_CHARS,
            )
            run_input = f"{run_input}{section}"

        master_agent = get_master_agent()
        return await master_agent.run(
            user_input=run_input,
            user_id=user_id,
            conversation_history=conversation_history,
            # Carried into the approval payload so the decide endpoint can
            # resume this exact run and finish this exact execution.
            execution_id=execution_id,
            **{**kwargs, **conv_overrides},
        )

    return _run_worker_async(_run())


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
    default_retry_delay=10,
    ignore_result=True,
)
def run_master_agent_task(self, execution_id: str, user_input: str, user_id: int, **kwargs):
    """
    Background task to run the master agent.

    Updates AgentExecution status:
      pending -> running -> completed (or failed after retries exhausted)

    NOTE: Only retries on transient errors (ConnectionError, TimeoutError).
    Does NOT retry on RuntimeError (including "Event loop is closed" from
    asyncio cleanup) or API errors (401 auth failures, etc.).
    """
    logger.info(f"[run_master_agent_task] execution_id={execution_id} started")

    try:
        # Update status to running
        future = _executor.submit(_update_execution_status_sync, execution_id, "running")
        future.result()

        # Run master agent in thread pool (it's async but Celery is sync)
        result = _run_async_master_agent(execution_id, user_input, user_id, **kwargs)

        # Graph suspended on human approval — do NOT mark completed. The decide
        # endpoint resumes the graph and finishes the execution.
        if isinstance(result, dict) and result.get("interrupted"):
            future = _executor.submit(
                _update_execution_with_result_sync,
                execution_id, "waiting_approval", result, None,
            )
            future.result()
            logger.info(
                f"[run_master_agent_task] execution_id={execution_id} "
                f"waiting_approval request_id={result.get('request_id')}"
            )
            return {"status": "waiting_approval", "execution_id": execution_id,
                    "result": result}

        # Update status to completed with result
        future = _executor.submit(
            _update_execution_with_result_sync, execution_id, "completed", result, None
        )
        future.result()

        logger.info(f"[run_master_agent_task] execution_id={execution_id} completed")

        # Save to conversation if conversation_id was provided
        conversation_id = kwargs.get("conversation_id")
        if conversation_id and result:
            _save_to_conversation_async(conversation_id, user_input, result)
            _auto_title_conversation(conversation_id, user_input, result)

        return {"status": "completed", "execution_id": execution_id, "result": result}

    except Exception as e:
        error_msg = str(e)
        _update_execution_with_result_sync(execution_id, "failed", None, str(e))
        # Do NOT retry on event-loop errors or auth errors — they are not transient
        if "Event loop is closed" in error_msg or "401" in error_msg or "Unauthorized" in error_msg:
            logger.error(f"[run_master_agent_task] execution_id={execution_id} non-retryable error: {e}")
            raise
        logger.error(f"[run_master_agent_task] execution_id={execution_id} error: {e}")
        raise


def _auto_title_conversation(conversation_id: int, user_input: str, result: dict):
    """Generate a short conversation title from the first user message using LLM.

    Only runs while the conversation has no title of its own.
    Runs synchronously in the Celery worker on its process-local event loop.
    """
    try:
        from app.core.database import get_sync_session
        from app.models.conversation import Conversation
        from sqlalchemy import select

        SessionLocal = get_sync_session()
        with SessionLocal() as session:
            conv_result = session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = conv_result.scalar_one_or_none()
            if not conv or conv.title:
                return  # Already titled

        async def _generate():
            from app.services.llm_router import get_llm_router
            router = get_llm_router()
            prompt = (
                "Write a short title for this conversation, at most six words, "
                "in the same language as the message, with no surrounding "
                f"quotes:\n{user_input[:200]}"
            )
            try:
                title = await router.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature_override=0.3,
                )
                return title.strip().strip('"').strip("'")[:50] or None
            except Exception:
                return None

        title = _run_worker_async(_generate())

        if not title:
            return

        SessionLocal = get_sync_session()
        with SessionLocal() as session:
            conv_result = session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = conv_result.scalar_one_or_none()
            if conv and not conv.title:
                conv.title = title
                session.commit()
                logger.info(f"[auto-title] conv_id={conversation_id} → {title!r}")
    except Exception as e:
        logger.warning(f"[auto-title] Failed for conv {conversation_id}: {e}")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    default_retry_delay=30,
)
def cleanup_stale_executions_task(self):
    """
    Cleanup task for stale execution records.

    Marks executions as 'failed' if they have been in 'running' state
    for more than STALE_TIMEOUT minutes.
    """
    from app.core.database import get_sync_session
    from app.models.agent import AgentExecution
    from sqlalchemy import select

    STALE_TIMEOUT_MINUTES = 30

    logger.info("[cleanup_stale_executions_task] Running stale execution cleanup")

    stale_threshold = utc_now() - timedelta(minutes=STALE_TIMEOUT_MINUTES)

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        result = session.execute(
            select(AgentExecution).where(
                AgentExecution.status == "running",
                AgentExecution.started_at < stale_threshold,
            )
        )
        stale_executions = result.scalars().all()

        if stale_executions:
            for exec_record in stale_executions:
                exec_record.status = "failed"
                exec_record.error_message = "Execution timed out (stale cleanup)"
                exec_record.completed_at = utc_now()
                logger.warning(
                    f"[cleanup_stale_executions_task] Marked stale execution {exec_record.execution_id} as failed"
                )
            session.commit()

        logger.info(
            f"[cleanup_stale_executions_task] Cleaned up {len(stale_executions)} stale executions"
        )

    return {"cleaned": len(stale_executions)}


@celery_app.task(bind=True, max_retries=1)
def anchor_conversation_chains_task(self):
    """Write moved conversation chain heads into the global audit chain.

    Sync, like every other beat task here: Celery has no event loop of its own,
    and `get_sync_session` avoids binding the shared async engine to a
    throwaway loop.
    """
    from app.core.database import get_sync_session
    from app.services.conversation_anchor import anchor_pending

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        summary = anchor_pending(session)
        session.commit()
    return summary


# Celery Beat schedule for periodic tasks
@celery_app.task(name="app.workers.tasks.expire_approval_requests_task")
def expire_approval_requests_task():
    from app.core.database import engine
    from app.services.approval_service import ApprovalService

    async def run():
        await engine.dispose()
        try:
            return {"expired": await ApprovalService.expire_pending()}
        finally:
            await engine.dispose()
    return _run_worker_async(run())


celery_app.conf.beat_schedule = {
    "expire-approval-requests-every-minute": {
        "task": "app.workers.tasks.expire_approval_requests_task",
        "schedule": 60.0,
    },
    "cleanup-stale-executions-every-15-min": {
        "task": "app.workers.tasks.cleanup_stale_executions_task",
        "schedule": 900.0,  # 15 minutes
    },
    "anchor-conversation-chains-every-15-min": {
        "task": "app.workers.tasks.anchor_conversation_chains_task",
        "schedule": 900.0,  # 15 minutes
    },
}


# ---------------------------------------------------------------------------
# OCR Ingest Task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=1)
def ocr_ingest_task(self, document_id, kb_id, raw_b64, filename, mime_type):
    """OCR a scanned PDF and ingest it into an existing (processing) Document row.

    Uses asyncio.run() with a NullPool engine for all DB access so that every
    connection is opened and closed within the same event loop — preventing
    "Future attached to a different loop" errors that arise when a shared
    connection-pool engine is used from multiple event loops (e.g. in tests).
    """
    import base64
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.models.knowledge import Document
    from app.services import ocr_service
    from app.services.knowledge_service import get_knowledge_service
    from app.config import settings

    raw = base64.b64decode(raw_b64)

    async def _run():
        # NullPool: each connection is opened and closed within this event loop
        # only — no pool state leaks to any other loop.
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            poolclass=NullPool,
        )
        _Session = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        try:
            # Load OCR config using the private session (avoids the shared
            # module-level engine which may be bound to a different event loop).
            from app.models.ocr import OcrConfig
            async with _Session() as _db:
                row = (await _db.execute(select(OcrConfig))).scalar_one_or_none()
            cfg = ocr_service.settings_from_row(row)

            text = await ocr_service.ocr_pdf(raw, cfg)
            if not text.strip():
                raise ValueError("OCR 未识别出文字")
            async with _Session() as db:
                await get_knowledge_service().ingest_document(
                    db=db, kb_id=kb_id, filename=filename, content=text,
                    mime_type=mime_type, document_id=document_id)
            # ingest_document already set status="ready" on the row
        except Exception as e:
            async with _Session() as db:
                await db.execute(
                    update(Document).where(Document.id == document_id)
                    .values(status="failed", status_detail=str(e)[:500]))
                await db.commit()
        finally:
            await _engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=2,
    default_retry_delay=5,
)
def resume_master_agent_task(
    self,
    thread_id: str,
    decision: str,
    comment: str | None = None,
    execution_id: str | None = None,
    conversation_id: int | None = None,
    user_id: int | None = None,
    user_input: str | None = None,
):
    """Resume a master graph suspended on approval (checkpointer + interrupt).

    The decision arrives in the API process; the run lives here. The durable
    checkpointer is what lets a different process pick it back up.
    """
    from app.agents.master import get_master_agent

    logger.info(
        "[resume_master_agent_task] thread_id=%s decision=%s execution_id=%s",
        thread_id, decision, execution_id,
    )

    async def _run():
        from app.core.database import engine
        await engine.dispose()
        return await get_master_agent().resume(
            thread_id, decision=decision, comment=comment, user_id=user_id)

    try:
        result = _run_worker_async(_run())
    except Exception as e:
        logger.error("[resume_master_agent_task] failed: %s", e)
        if execution_id:
            _update_execution_with_result_sync(execution_id, "failed", None, str(e))
        raise

    if isinstance(result, dict) and result.get("interrupted"):
        # The run hit a second gate — still waiting on a human.
        if execution_id:
            _update_execution_with_result_sync(
                execution_id, "waiting_approval", result, None)
        return {"status": "waiting_approval", "result": result}

    approved = decision == "approved"
    status = "completed" if approved else "failed"
    if execution_id:
        err = None if approved else (
            (result or {}).get("error_message") or f"Approval {decision}")
        _update_execution_with_result_sync(execution_id, status, result, err)

    if conversation_id and result and approved:
        _save_to_conversation_async(conversation_id, user_input or "", result)

    return {"status": status, "execution_id": execution_id, "result": result}


@celery_app.task(name="app.workers.tasks.archive_audit_evidence_task")
def archive_audit_evidence_task():
    """Opt-in periodic archival; failures are surfaced as failed tasks."""
    import os
    if os.environ.get('AUDIT_WORM_AUTO_EXPORT', '').lower() != 'true':
        return {'status': 'disabled'}
    from app.core.database import engine
    from app.services.audit_worm import export_new

    async def run():
        await engine.dispose()
        try:
            return await export_new(retain_days=int(os.environ.get('AUDIT_WORM_RETAIN_DAYS', '365')))
        finally:
            await engine.dispose()
    return _run_worker_async(run())


import os as _audit_schedule_os
if _audit_schedule_os.environ.get('AUDIT_WORM_AUTO_EXPORT', '').lower() == 'true':
    celery_app.conf.beat_schedule['archive-audit-evidence-every-15-min'] = {
        'task': 'app.workers.tasks.archive_audit_evidence_task',
        'schedule': 900.0,
    }
