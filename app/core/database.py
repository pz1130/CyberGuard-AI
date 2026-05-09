"""Database connection and session management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Synchronous engine for Celery workers
_sync_engine = None
_SyncSessionLocal = None


def get_sync_engine():
    """Get or create synchronous engine for sync contexts (Celery workers)."""
    global _sync_engine
    if _sync_engine is None:
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        _sync_engine = create_engine(
            sync_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _sync_engine


def get_sync_session():
    """Get a synchronous session factory for Celery workers."""
    global _SyncSessionLocal
    if _SyncSessionLocal is None:
        _SyncSessionLocal = sessionmaker(bind=get_sync_engine())
    return _SyncSessionLocal


# Base class for models
Base = declarative_base()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context():
    """Context manager for database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()