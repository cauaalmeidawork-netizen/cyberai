"""Database engine lifecycle and session scoping."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cyberai.core.config import DatabaseSettings
from cyberai.core.logging import get_logger
from cyberai.platform.db.tenant import TenantContext, apply_tenant_context

logger = get_logger(__name__)

_PING = text("SELECT 1")


class Database:
    """Owns the async engine and hands out transaction-scoped sessions."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine = create_async_engine(
            settings.url,
            echo=settings.echo,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout_seconds,
            pool_recycle=settings.pool_recycle_seconds,
            pool_pre_ping=True,
            connect_args={
                "server_settings": {
                    "application_name": "cyberai-api",
                    # A runaway query must not hold a pool connection forever.
                    "statement_timeout": str(settings.statement_timeout_ms),
                },
            },
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @asynccontextmanager
    async def session(self, tenant: TenantContext | None = None) -> AsyncIterator[AsyncSession]:
        """Open a unit of work.

        The transaction is committed on success and rolled back on any
        exception. When a tenant is supplied it is bound to the transaction
        before any statement runs, so Row Level Security applies to everything
        inside the block.
        """
        async with self._session_factory() as session, session.begin():
            if tenant is not None:
                await apply_tenant_context(session, tenant)
            yield session

    async def check_health(self) -> bool:
        """Return True when the database answers a trivial query."""
        try:
            async with self._engine.connect() as connection:
                await connection.execute(_PING)
        except Exception as exc:
            logger.warning(
                "database.health_check_failed",
                error=type(exc).__name__,
                database_url=self._settings.masked_url,
            )
            return False
        return True

    async def dispose(self) -> None:
        await self._engine.dispose()
        logger.info("database.disposed")
