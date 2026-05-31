"""Celery tasks for background agent execution."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


# ---------------------------------------------------------------------------
# Scheduled Task Execution Engine
# ---------------------------------------------------------------------------

def _evaluate_cron_should_fire(cron_expr: str, last_run_at: datetime | None) -> bool:
    """
    Determine if a cron expression should fire at the current time.

    Returns True if the cron schedule's next run time is within the last 90 seconds
    and is after the last recorded run time.
    """
    try:
        from croniter import croniter
    except ImportError:
        logger.warning("[scheduler] croniter not installed, skipping cron evaluation")
        return False

    try:
        tz = timezone.utc
        cron = croniter(cron_expr, datetime.now(tz))
        next_run = cron.get_next(datetime)
        prev_run = cron.get_prev(datetime)

        now = datetime.now(tz)
        # Fire if prev_run was within the last 90 seconds
        delta = (now - prev_run).total_seconds()
        if delta > 90:
            return False

        # Don't re-fire if last_run_at is more recent than prev_run
        if last_run_at and last_run_at >= prev_run:
            return False

        return True
    except Exception as e:
        logger.warning(f"[scheduler] Invalid cron expression '{cron_expr}': {e}")
        return False


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    default_retry_delay=30,
)
def sync_scheduled_jobs_task(self):
    """
    Celery Beat task that runs every minute.

    Reads all active ScheduledTasks from DB and fires any that match
    the current time window based on their cron_expression.
    """
    import uuid
    from app.core.database import get_sync_session
    from app.models.schedule import ScheduledTask
    from app.models.agent import AgentExecution
    from sqlalchemy import select
    from croniter import croniter

    logger.debug("[sync_scheduled_jobs_task] Syncing scheduled jobs")

    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        result = session.execute(
            select(ScheduledTask).where(ScheduledTask.is_active.is_(True))
        )
        tasks = result.scalars().all()

        fired_count = 0
        for task in tasks:
            should_fire = _evaluate_cron_should_fire(
                task.cron_expression, task.last_run_at
            )
            if not should_fire:
                continue

            logger.info(
                f"[sync_scheduled_jobs_task] Firing task: {task.name} "
                f"(cron={task.cron_expression})"
            )

            # Update last_run_at and compute next_run_at
            now = datetime.now(timezone.utc)
            task.last_run_at = now
            try:
                cron = croniter(task.cron_expression, now)
                task.next_run_at = cron.get_next(datetime)
            except Exception:
                task.next_run_at = None

            # Create execution record for the scheduled task
            execution_id = str(uuid.uuid4())
            task_config = task.task_config or {}
            prompt = task_config.get("prompt", task_config.get("message", f"Scheduled task: {task.name}"))

            exec_record = AgentExecution(
                execution_id=execution_id,
                agent_id=task.agent_id,
                status="pending",
                input_data={"user_input": prompt, "source": "scheduled", "scheduled_task_id": task.task_id},
            )
            session.add(exec_record)
            session.commit()

            # Dispatch to run_master_agent_task
            run_master_agent_task.apply_async(
                args=[execution_id, prompt, 0],
                kwargs={
                    "agent_id": task.agent_id,
                    "source": "scheduled",
                    "task_name": task.name,
                },
            )
            fired_count += 1

        if fired_count:
            session.commit()

        logger.info(
            f"[sync_scheduled_jobs_task] Synced {len(tasks)} tasks, fired {fired_count}"
        )
        return {"total": len(tasks), "fired": fired_count}


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
                execution.started_at = datetime.now(timezone.utc)
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
            execution.completed_at = datetime.now(timezone.utc)
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(_async_query())
        finally:
            loop.close()

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
    """Save user message and result to conversation (fire-and-forget)."""
    import json
    from datetime import datetime, timezone
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
            if not conv:
                return

            messages = json.loads(conv.messages_json or "[]")

            # Add user message
            messages.append({
                "role": "user",
                "content": user_input,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

            # Add assistant response
            final_summary = result.get("final_summary", "")
            if isinstance(final_summary, dict):
                final_summary = json.dumps(final_summary)
            messages.append({
                "role": "assistant",
                "content": final_summary or str(result),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

            conv.messages_json = json.dumps(messages, ensure_ascii=False)
            conv.updated_at = datetime.now(timezone.utc)
            session.commit()
    except Exception as e:
        logger.warning(f"Failed to save to conversation {conversation_id}: {e}")


def _run_async_master_agent(execution_id: str, user_input: str, user_id: int, **kwargs):
    """Run async master agent in a thread pool."""
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
            if conv.model_override:
                conv_overrides["model_override"] = conv.model_override
            if conv.temperature_override is not None:
                conv_overrides["temperature_override"] = conv.temperature_override

            # Conversation history: pass last N turns so the LLM has memory
            try:
                all_messages = _json.loads(conv.messages_json or "[]")
                # Keep at most 20 messages (10 turns) to avoid blowing context window
                conversation_history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in all_messages[-20:]
                    if m.get("role") in ("user", "assistant") and m.get("content")
                ]
            except Exception:
                conversation_history = []

    # Prepend RAG context to user input if retrieved
    if rag_context:
        user_input = f"[知识库检索结果]\n{rag_context}\n\n[用户问题]\n{user_input}"

    # Inject attachment content into user_input when attachments are present
    attachments = kwargs.get("attachments")
    if attachments:
        attachment_lines = []
        for att in attachments:
            filename = att.get("filename", "attachment")
            # Router stores base64 content under "data" key
            b64_content = att.get("data", "")
            mime_type = att.get("content_type", "")
            # Decode base64 to get text content
            try:
                import base64 as b64_mod
                content = b64_mod.b64decode(b64_content).decode("utf-8", errors="replace")
            except Exception:
                content = ""
            # Truncate very long content
            truncated = content[:1000] if content else ""
            attachment_lines.append(f"[附件: {filename}] (type: {mime_type})\n{truncated}")

        attachment_desc = "\n\n".join(attachment_lines)
        user_input = f"{user_input}\n\n--- 附件信息 ---\n{attachment_desc}"

    async def _run():
        master_agent = get_master_agent()
        return await master_agent.run(
            user_input=user_input,
            user_id=user_id,
            conversation_history=conversation_history,
            **{**kwargs, **conv_overrides},
        )

    # Create a fresh event loop to avoid "Event loop is closed" errors
    # that occur when Celery's main process loop conflicts with async redis client
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


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

        # Email admin if this was a scheduled task
        if kwargs.get("source") == "scheduled":
            task_name = kwargs.get("task_name", execution_id)
            _notify_task_done(task_name, execution_id, "completed")

        return {"status": "completed", "execution_id": execution_id, "result": result}

    except Exception as e:
        error_msg = str(e)
        _update_execution_with_result_sync(execution_id, "failed", None, str(e))
        if kwargs.get("source") == "scheduled":
            task_name = kwargs.get("task_name", execution_id)
            _notify_task_done(task_name, execution_id, "failed", error=error_msg)
        # Do NOT retry on event-loop errors or auth errors — they are not transient
        if "Event loop is closed" in error_msg or "401" in error_msg or "Unauthorized" in error_msg:
            logger.error(f"[run_master_agent_task] execution_id={execution_id} non-retryable error: {e}")
            raise
        logger.error(f"[run_master_agent_task] execution_id={execution_id} error: {e}")
        raise


def _auto_title_conversation(conversation_id: int, user_input: str, result: dict):
    """Generate a short conversation title from the first user message using LLM.

    Only runs when the conversation still has the default title ('新对话').
    Runs synchronously in the Celery worker — uses a fresh event loop.
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
            if not conv or conv.title != "新对话":
                return  # Already has a custom title

        async def _generate():
            from app.services.llm_router import get_llm_router
            router = get_llm_router()
            prompt = (
                f"请为以下对话生成一个简洁的标题（10字以内，不加引号）：\n{user_input[:200]}"
            )
            try:
                title = await router.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature_override=0.3,
                )
                return title.strip().strip('"').strip("'")[:50] or "新对话"
            except Exception:
                return None

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            title = loop.run_until_complete(_generate())
        finally:
            loop.close()

        if not title:
            return

        SessionLocal = get_sync_session()
        with SessionLocal() as session:
            conv_result = session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = conv_result.scalar_one_or_none()
            if conv and conv.title == "新对话":
                conv.title = title
                session.commit()
                logger.info(f"[auto-title] conv_id={conversation_id} → {title!r}")
    except Exception as e:
        logger.warning(f"[auto-title] Failed for conv {conversation_id}: {e}")


def _notify_task_done(task_name: str, execution_id: str, status: str, error: str | None = None):
    """Fire-and-forget email when a scheduled task finishes (sync wrapper)."""
    async def _send():
        from app.services.email_service import notify_scheduled_task_done
        await notify_scheduled_task_done(task_name, execution_id, status, error)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_send())
        finally:
            loop.close()
    except Exception as e:
        logger.warning(f"[email] notify_task_done failed: {e}")


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

    stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=STALE_TIMEOUT_MINUTES)

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
                exec_record.completed_at = datetime.now(timezone.utc)
                logger.warning(
                    f"[cleanup_stale_executions_task] Marked stale execution {exec_record.execution_id} as failed"
                )
            session.commit()

        logger.info(
            f"[cleanup_stale_executions_task] Cleaned up {len(stale_executions)} stale executions"
        )

    return {"cleaned": len(stale_executions)}


# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "cleanup-stale-executions-every-15-min": {
        "task": "app.workers.tasks.cleanup_stale_executions_task",
        "schedule": 900.0,  # 15 minutes
    },
    "sync-scheduled-jobs-every-minute": {
        "task": "app.workers.tasks.sync_scheduled_jobs_task",
        "schedule": 60.0,  # 1 minute
    },
}


# ---------------------------------------------------------------------------
# Outgoing webhook delivery
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
    default_retry_delay=30,
    ignore_result=True,
)
def deliver_webhook_task(self, webhook_id: int, event: str, payload: dict):
    """Async outgoing webhook delivery with retries.

    Retries on transient network errors only. Permanent failures (HTTP 4xx/5xx
    from the target server) are recorded on the webhook row and *not* retried —
    by design, so that a buggy receiver doesn't burn the queue.
    """
    from app.services.webhook_service import deliver_sync

    result = deliver_sync(webhook_id=webhook_id, event=event, payload=payload)
    if not result["success"]:
        logger.warning(
            "[deliver_webhook_task] webhook=%s event=%s failed: %s",
            webhook_id, event, result.get("error"),
        )
    return result


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
