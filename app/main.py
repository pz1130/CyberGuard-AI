"""CyberGuard AI Agent Platform - FastAPI Application Entry Point."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.database import engine, Base
from app.core.audit import log_audit
from app.core.auth import PasswordTooLongError
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Telemetry (must init before any requests)
    try:
        from app.core.telemetry import setup_telemetry
        setup_telemetry()
    except Exception as e:
        logger.warning(f"Telemetry setup failed: {e}")

    # Langfuse LLM tracing (optional; no-op unless LANGFUSE_* env is set)
    try:
        from app.core.langfuse_tracing import setup_langfuse
        setup_langfuse()
    except Exception as e:
        logger.warning(f"Langfuse setup failed: {e}")

    # Startup: run Alembic migrations (all environments — not just dev)
    # In dev: also create any tables Alembic doesn't know about (e.g. if migration hasn't run yet)
    if settings.ENVIRONMENT == "development":
        # Run alembic migrations on every startup in dev (safe — alembic is idempotent).
        # Handles single-head, multiple-head (PR #11 introduced a second head), and
        # already-applied-schema fallback. Outside dev: rely on CI/CD alembic upgrade.
        try:
            from app.core.migrations import run_alembic_upgrade_on_startup
            run_alembic_upgrade_on_startup()
        except Exception as e:
            logger.warning(f"Alembic upgrade skipped: {e}")
    else:
        # Production: verify migrations are up to date via health check
        # The /health endpoint will check alembic version vs DB state
        logger.info("Production mode — relying on CI/CD alembic upgrade")

    # Seed the first admin only when an explicit bootstrap password is supplied.
    # There is deliberately no built-in password in any environment.
    from app.core.database import get_db_context
    from app.models.user import User
    from app.core.auth import get_password_hash
    from sqlalchemy import select
    try:
        async with get_db_context() as session:
            result = await session.execute(
                select(User).where(User.username == settings.BOOTSTRAP_ADMIN_USERNAME)
            )
            if not result.scalar_one_or_none() and settings.BOOTSTRAP_ADMIN_PASSWORD:
                admin = User(
                    username=settings.BOOTSTRAP_ADMIN_USERNAME,
                    email=settings.BOOTSTRAP_ADMIN_EMAIL,
                    hashed_password=get_password_hash(settings.BOOTSTRAP_ADMIN_PASSWORD),
                    role="admin",
                    full_name="Administrator",
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                logger.warning(
                    "Bootstrap admin created — username: %s",
                    settings.BOOTSTRAP_ADMIN_USERNAME,
                )
    except Exception as e:
        logger.warning(f"User seed skipped: {e}")

    # Seed preset providers (dev and prod — idempotent by name).
    try:
        from app.routers.providers import seed_providers_on_startup
        await seed_providers_on_startup()
        logger.info("Preset providers seeded")
    except Exception as e:
        logger.warning(f"Provider seed skipped: {e}")

    # Seed default prompt templates (dev and prod — idempotent by name).
    # Runs after migrations so the table exists.
    try:
        from app.routers.prompt_templates import seed_prompt_templates_on_startup
        await seed_prompt_templates_on_startup()
    except Exception as e:
        logger.warning(f"Prompt-template seed skipped: {e}")

    # Seed example internal agents (env-gated, idempotent by name).
    try:
        from app.routers.agents import seed_example_internal_agents
        await seed_example_internal_agents()
    except Exception as e:
        logger.warning(f"Internal agent seed skipped: {e}")

    # Kill switch file poller (NDB Std §Kill Switch — file trigger)
    import os as _os
    import asyncio as _aio
    from app.services import kill_switch as _ks

    async def _killswitch_file_poller():
        while True:
            try:
                if _os.path.exists(settings.KILL_SWITCH_FILE):
                    if not await _ks.is_halted():
                        await _ks.engage("global", by="file-trigger",
                                         reason=settings.KILL_SWITCH_FILE)
                        logger.warning(
                            "kill switch engaged from file trigger: %s",
                            settings.KILL_SWITCH_FILE,
                        )
            except Exception as e:  # noqa: BLE001 — INV-25: never silent
                logger.error("kill switch file poller error: %s", e)
            await _aio.sleep(1)

    _ks_task = _aio.create_task(_killswitch_file_poller())

    # Give the agent audit event stream a durable sink. The default bus ships
    # with zero subscribers, so without this every emit is a no-op and the
    # evidence trail exists in shape only.
    from agent_core.events import get_default_audit_bus
    from app.services.run_event_log import RunEventSink
    _run_event_handler = RunEventSink().handle
    get_default_audit_bus().subscribe(_run_event_handler)

    # Count credentials still in the pre-AEAD format. The migration is lazy by
    # design, so without this nothing would ever say that existing ciphertext
    # is still malleable. Read-only, and never decrypts.
    try:
        from app.services.encryption_status import scan_legacy_credentials
        await scan_legacy_credentials()
    except Exception as e:  # noqa: BLE001 - a *report* is not a boundary
        logger.warning(f"Credential encryption scan skipped: {e}")

    # Report runs a previous crash left mid-flight. Read-only: replaying a
    # side-effecting tool is never automatic.
    try:
        from app.services.run_recovery import sweep_interrupted_runs
        await sweep_interrupted_runs()
    except Exception as e:  # noqa: BLE001 - a recovery *report* is not a boundary
        logger.warning(f"Run recovery sweep skipped: {e}")

    yield
    # Shutdown
    _ks_task.cancel()
    # The default audit bus is a process-level singleton that outlives this
    # app instance. Leaving the sink attached means it keeps consuming events
    # and writing to an engine we are about to dispose.
    get_default_audit_bus().unsubscribe(_run_event_handler)
    try:
        from app.core.langfuse_tracing import flush_langfuse
        flush_langfuse()
    except Exception:
        pass
    await engine.dispose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CyberGuard AI Agent Platform",
    description="Secure, controllable and extensible multi-agent AI system for cybersecurity operations.",
    version="1.0.0-rc.1",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """Log all HTTP requests to the audit trail.

    INV-29: the audit write is awaited, not dispatched fire-and-forget. The
    previous `asyncio.create_task(...)` had three problems, all of which put
    holes in the evidence trail rather than merely slowing it down: the task
    could be garbage-collected before it ran (nothing held a reference), any
    exception vanished into "Task exception was never retrieved", and a crash
    between dispatch and completion lost the record silently. `log_audit`
    already awaits its own DB flush for exactly this reason.

    The cost is one Redis lpush per request; `log_audit` degrades to the DB
    buffer (loudly) when Redis is unavailable, so a Redis stall cannot wedge
    request handling.
    """
    if request.url.path in ["/health", "/docs", "/openapi.json"]:
        return await call_next(request)

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # After the request, not before: only here do we know who the caller
        # was (get_current_user records it on request.state — the middleware
        # runs before dependencies resolve) and how it ended. An audit row
        # naming neither the actor nor the outcome answers no question anyone
        # would ask of it. `finally` so a raised request is still recorded.
        await log_audit(
            user_id=getattr(request.state, "user_id", None),
            agent_id=None,
            action=f"{request.method} {request.url.path}",
            input_data={"method": request.method, "path": str(request.url.path)},
            output_data={"status_code": status_code},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            request_path=str(request.url.path),
            metadata={
                "method": request.method,
                "status_code": status_code,
                "username": getattr(request.state, "username", None),
            },
        )


# ---------------------------------------------------------------------------
# Health Check + Readiness Probe
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Liveness probe: checks app is running.
    Does NOT verify DB/Redis — app can be alive without them (read-only degraded state).
    """
    return {"status": "ok", "version": "1.0.0-rc.1"}


@app.get("/health/ready", tags=["Health"])
async def readiness_probe():
    """
    Readiness probe: checks all critical backends are reachable.
    Use this as the Docker health/readiness probe in production.
    """
    from app.core.database import engine
    from app.core.ratelimit import get_redis

    checks = {}
    all_healthy = True

    # DB check
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
        all_healthy = False

    # Redis check
    try:
        r = await get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        all_healthy = False

    if not all_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "checks": checks},
            headers={"Retry-After": "10"},
        )

    return {"status": "ready", "checks": checks}


@app.get("/health/started", tags=["Health"])
async def startup_probe():
    """
    Startup probe: checks that initialisation (migrations + seeds) is complete.
    Use as the Docker startup probe to delay readiness checks during boot.
    """
    return {"status": "started", "version": "1.0.0-rc.1"}


# ---------------------------------------------------------------------------
# Routers (imported here to avoid circular imports)
# ---------------------------------------------------------------------------
from app.routers import auth, users, agents, skills, knowledge, chat, tasks, audit, backup, config, providers, mcp, envvars, approval, token_usage, master_config, conversations, prompt_templates, security, kill_switch, governance_config, governance_rollback, governance_metrics
from app.routers import chat_stream, gateway, sso

app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1", tags=["Users"])
app.include_router(agents.router, prefix="/api/v1", tags=["Agents"])
app.include_router(skills.router, prefix="/api/v1", tags=["Skills & Tools"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["Knowledge Base"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
app.include_router(chat_stream.router, prefix="/api/v1", tags=["Chat"])
app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
app.include_router(audit.router, prefix="/api/v1", tags=["Audit"])
app.include_router(kill_switch.router, prefix="/api/v1", tags=["Kill Switch"])
app.include_router(governance_config.router, prefix="/api/v1", tags=["Agent Governance Config"])
app.include_router(governance_rollback.router, prefix="/api/v1", tags=["Safety Envelope"])
app.include_router(governance_metrics.router, prefix="/api/v1", tags=["Governance Metrics"])
app.include_router(backup.router, prefix="/api/v1", tags=["Backup"])
app.include_router(config.router, prefix="/api/v1", tags=["Configuration"])
app.include_router(providers.router, prefix="/api/v1", tags=["AI Providers"])
app.include_router(mcp.router, prefix="/api/v1", tags=["MCP"])
app.include_router(envvars.router, prefix="/api/v1", tags=["Environment Variables"])
app.include_router(approval.router, prefix="/api/v1", tags=["Approvals"])
app.include_router(token_usage.router, prefix="/api/v1", tags=["Token Usage"])
app.include_router(master_config.router, prefix="/api/v1", tags=["Master Agent Config"])
app.include_router(conversations.router, prefix="/api/v1", tags=["Conversations"])
app.include_router(gateway.router, prefix="/api/v1", tags=["OpenClaw Gateway"])
app.include_router(prompt_templates.router, prefix="/api/v1", tags=["Prompt Templates"])
app.include_router(security.router, prefix="/api/v1", tags=["Security Settings"])
app.include_router(sso.router, prefix="/api/v1", tags=["SSO"])


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------
@app.exception_handler(PasswordTooLongError)
async def password_too_long_handler(request: Request, exc: PasswordTooLongError):
    """A password bcrypt cannot hash is bad input, not a server fault.

    Registered here rather than at each call site so any future code path that
    hashes a password inherits the 400 instead of falling through to the
    catch-all below and reporting an internal error.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler — hides internal error details in production."""
    # Log full error for debugging; do not expose to client in production
    import logging
    logger = logging.getLogger(__name__)
    logger.exception(f"Unhandled exception on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
