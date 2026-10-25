"""
OmniSight — Database Connection & Session Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Async SQLAlchemy engine and session factory for SQLite.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

connect_args = {}
if "sqlite" in settings.database_url:
    connect_args = {"check_same_thread": False, "timeout": 30.0}

# ── Async Engine ─────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    future=True,
    connect_args=connect_args,
)

# ── Session Factory ──────────────────────────────────────────
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Declarative Base ─────────────────────────────────────────
class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""

    pass


# ── Dependency ───────────────────────────────────────────────
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("🗄️  Database tables initialized")
