"""Rate limiter abstraction for billing enforcement."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitRequest:
    org_id: object
    user_id: object | None
    limit: int
    window_seconds: int
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int | None = None


class RateLimiter(Protocol):
    async def check(self, request: RateLimitRequest) -> RateLimitResult: ...


class InMemoryRateLimiter:
    """Deterministic in-process limiter for tests and local fallback."""

    def __init__(self) -> None:
        self._windows: dict[str, tuple[datetime, int]] = {}

    async def check(self, request: RateLimitRequest) -> RateLimitResult:
        now = request.now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("rate limit timestamps must be timezone-aware")
        now = now.astimezone(UTC)
        key = self._key(request)
        current = self._windows.get(key)
        if current is None or (now - current[0]).total_seconds() >= request.window_seconds:
            self._windows[key] = (now, 1)
            return RateLimitResult(True, remaining=max(request.limit - 1, 0))
        window_start, count = current
        if count >= request.limit:
            elapsed = int((now - window_start).total_seconds())
            return RateLimitResult(
                False,
                remaining=0,
                retry_after_seconds=max(request.window_seconds - elapsed, 0),
            )
        self._windows[key] = (window_start, count + 1)
        return RateLimitResult(True, remaining=max(request.limit - count - 1, 0))

    def snapshot_keys(self) -> tuple[str, ...]:
        return tuple(self._windows.keys())

    def _key(self, request: RateLimitRequest) -> str:
        scope = f"{request.org_id}:{request.user_id or ''}:{request.window_seconds}"
        digest = hashlib.sha256(scope.encode()).hexdigest()
        prefix = "user" if request.user_id is not None else "org"
        return f"{prefix}:{digest}"
