"""CyberGuard AI Agent Platform - FastAPI Application Entry Point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.database import engine, Base
from app.core.audit import log_audit


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup: create tables if they don't exist (dev only)
    if settings.ENVIRONMENT == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Seed default admin user
        from app.core.database import get_db_context
        from app.models.user import User
        import bcrypt
        from sqlalchemy import select
        try:
            async with get_db_context() as session:
                result = await session.execute(select(User).where(User.username == "admin"))
                if not result.scalar_one_or_none():
                    admin = User(
                        username="admin",
                        email="admin@cyberguard.local",
                        hashed_password=bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode(),
                        role="admin",
                        full_name="Administrator",
                        is_active=True,
                    )
                    session.add(admin)
                    await session.commit()
                    print("[CyberGuard] Default admin user created: admin / admin123")
        except Exception as e:
            print(f"[CyberGuard] User seed skipped: {e}")
    yield
    # Shutdown
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
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Routers (imported here to avoid circular imports)
# ---------------------------------------------------------------------------
from app.routers import auth, users, agents, skills, knowledge, chat, tasks, groupchat, schedule, audit, backup, config, providers, mcp, envvars

app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1", tags=["Users"])
app.include_router(agents.router, prefix="/api/v1", tags=["Agents"])
app.include_router(skills.router, prefix="/api/v1", tags=["Skills & Tools"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["Knowledge Base"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
app.include_router(schedule.router, prefix="/api/v1", tags=["Scheduled Tasks"])
app.include_router(audit.router, prefix="/api/v1", tags=["Audit"])
app.include_router(backup.router, prefix="/api/v1", tags=["Backup"])
app.include_router(config.router, prefix="/api/v1", tags=["Configuration"])
app.include_router(providers.router, prefix="/api/v1", tags=["AI Providers"])
app.include_router(mcp.router, prefix="/api/v1", tags=["MCP"])
app.include_router(envvars.router, prefix="/api/v1", tags=["Environment Variables"])

# WebSocket routes under /ws (proxied by Vite: /ws → ws://localhost:8000/ws)
app.include_router(groupchat.router, prefix="/ws", tags=["Group Chat WS"])


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc)},
    )
