"""Redis client lifecycle.

Redis is the shared state that lets the API stay stateless: nothing that must
survive a process restart or be visible to a sibling instance is kept in
process memory. In M0 it only backs health checks; rate limiting, quota
counters and the job queue plug into the same client later.
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from cyberai.core.config import RedisSettings
from cyberai.core.logging import get_logger

logger = get_logger(__name__)


class RedisCache:
    """Thin, typed wrapper around the async Redis client."""

    def __init__(self, settings: RedisSettings) -> None:
        self._settings = settings
        self._pool = ConnectionPool.from_url(
            settings.url,
            max_connections=settings.max_connections,
            socket_timeout=settings.socket_timeout_seconds,
            socket_connect_timeout=settings.socket_connect_timeout_seconds,
            decode_responses=True,
        )
        self._client: Redis = Redis(connection_pool=self._pool)

    @property
    def client(self) -> Redis:
        return self._client

    async def check_health(self) -> bool:
        """Return True when Redis answers PING."""
        try:
            await self._client.ping()
        except Exception as exc:
            logger.warning(
                "redis.health_check_failed",
                error=type(exc).__name__,
                redis_url=self._settings.masked_url,
            )
            return False
        return True

    async def close(self) -> None:
        await self._client.aclose()
        await self._pool.disconnect()
        logger.info("redis.closed")
