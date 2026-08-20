"""Redis-backed rate limiter adapter."""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis

from cyberai.core.logging import get_logger
from cyberai.modules.billing.rate_limit import RateLimiter, RateLimitRequest, RateLimitResult

logger = get_logger(__name__)


class RedisRateLimiter(RateLimiter):
    """Fixed-window Redis rate limiter with explicit dependency-failure behavior."""

    def __init__(self, client: Redis, *, fail_open: bool) -> None:
        self._client = client
        self._fail_open = fail_open

    async def check(self, request: RateLimitRequest) -> RateLimitResult:
        key = self._key(request)
        try:
            count = await self._client.incr(key)
            if count == 1:
                await self._client.expire(key, request.window_seconds)
            if count > request.limit:
                ttl = await self._client.ttl(key)
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=max(int(ttl), 0),
                )
            return RateLimitResult(allowed=True, remaining=max(request.limit - int(count), 0))
        except Exception as exc:
            logger.warning(
                "rate_limiter.redis_failed",
                error=type(exc).__name__,
                fail_open=self._fail_open,
            )
            if self._fail_open:
                return RateLimitResult(allowed=True, remaining=request.limit)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=request.window_seconds,
            )

    def _key(self, request: RateLimitRequest) -> str:
        scope = f"{request.org_id}:{request.user_id or ''}:{request.window_seconds}"
        digest = hashlib.sha256(scope.encode()).hexdigest()
        prefix = "user" if request.user_id is not None else "org"
        return f"billing:rate:{prefix}:{digest}"
