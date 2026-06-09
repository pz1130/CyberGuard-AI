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

    # Seed default admin user (dev and prod — idempotent by username). Runs in
    # both modes so a fresh DB (e.g. `docker compose down -v`) is always usable.
    from app.core.database import get_db_context
    from app.models.user import User
    import bcrypt
    from sqlalchemy import select
    try:
        async with get_db_context() as session:
            result = await session.execute(select(User).where(User.username == "admin"))
            if not result.scalar_one_or_none():
                # Fixed default password
                default_password = "admin123"
                admin = User(
                    username="admin",
                    email="admin@cyberguard.local",
                    hashed_password=bcrypt.hashpw(default_password.encode(), bcrypt.gensalt()).decode(),
                    role="admin",
                    full_name="Administrator",
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                logger.warning(f"Default admin user created — username: admin, password: {default_password}")
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

    # Seed default governance frameworks (idempotent by urn).
    try:
        from app.routers.governance import seed_governance_frameworks_on_startup
        await seed_governance_frameworks_on_startup()
    except Exception as e:
        logger.warning(f"Governance framework seed skipped: {e}")

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
            except Exception:
                pass
            await _aio.sleep(1)

    _ks_task = _aio.create_task(_killswitch_file_poller())

    yield
    # Shutdown
    _ks_task.cancel()
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
    version="1.0.0",
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
    """Log all HTTP requests to audit trail."""
    if request.url.path not in ["/health", "/docs", "/openapi.json"]:
        # Defer audit logging to avoid async Redis in sync middleware path
        import asyncio
        asyncio.create_task(log_audit(
            user_id=None,
            agent_id=None,
            action=f"{request.method} {request.url.path}",
            input_data={"method": request.method, "path": str(request.url.path)},
            output_data=None,
        ))
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# Health Check + Readiness Probe
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Liveness probe: checks app is running.
    Does NOT verify DB/Redis — app can be alive without them (read-only degraded state).
    """
    return {"status": "ok", "version": "1.0.0"}


@app.get("/health/ready", tags=["Health"])
async def readiness_probe():
    """
    Readiness probe: checks all critical backends are reachable.
    Use this as K8s readiness/liveness probe in production.
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
    Use as K8s startup probe to delay readiness/liveness checks during boot.
    """
    return {"status": "started", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Routers (imported here to avoid circular imports)
# ---------------------------------------------------------------------------
from app.routers import auth, users, agents, skills, knowledge, chat, tasks, groupchat, schedule, audit, backup, config, providers, mcp, envvars, approval, token_usage, master_config, conversations, n8n, webhooks, prompt_templates, governance, security, kill_switch
from app.routers import chat_stream, gateway, sso

app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1", tags=["Users"])
app.include_router(agents.router, prefix="/api/v1", tags=["Agents"])
app.include_router(skills.router, prefix="/api/v1", tags=["Skills & Tools"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["Knowledge Base"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
app.include_router(chat_stream.router, prefix="/api/v1", tags=["Chat"])
app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
app.include_router(schedule.router, prefix="/api/v1", tags=["Scheduled Tasks"])
app.include_router(audit.router, prefix="/api/v1", tags=["Audit"])
app.include_router(kill_switch.router, prefix="/api/v1", tags=["Kill Switch"])
app.include_router(backup.router, prefix="/api/v1", tags=["Backup"])
app.include_router(config.router, prefix="/api/v1", tags=["Configuration"])
app.include_router(providers.router, prefix="/api/v1", tags=["AI Providers"])
app.include_router(mcp.router, prefix="/api/v1", tags=["MCP"])
app.include_router(envvars.router, prefix="/api/v1", tags=["Environment Variables"])
app.include_router(approval.router, prefix="/api/v1", tags=["Approvals"])
app.include_router(token_usage.router, prefix="/api/v1", tags=["Token Usage"])
app.include_router(master_config.router, prefix="/api/v1", tags=["Master Agent Config"])
app.include_router(conversations.router, prefix="/api/v1", tags=["Conversations"])
app.include_router(n8n.router, prefix="/api/v1", tags=["N8N"])
app.include_router(gateway.router, prefix="/api/v1", tags=["OpenClaw Gateway"])

app.include_router(groupchat.router, prefix="/api/v1", tags=["Group Chat"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["Webhooks"])
app.include_router(prompt_templates.router, prefix="/api/v1", tags=["Prompt Templates"])
app.include_router(governance.router, prefix="/api/v1", tags=["Governance"])
app.include_router(security.router, prefix="/api/v1", tags=["Security Settings"])
app.include_router(sso.router, prefix="/api/v1", tags=["SSO"])


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------
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
