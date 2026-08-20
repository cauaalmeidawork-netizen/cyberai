"""Unit tests for rate limiting abstraction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cyberai.modules.billing.rate_limit import InMemoryRateLimiter, RateLimitRequest


async def test_in_memory_rate_limiter_enforces_org_window() -> None:
    limiter = InMemoryRateLimiter()
    org_id = uuid4()
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    request = RateLimitRequest(
        org_id=org_id,
        user_id=None,
        limit=2,
        window_seconds=60,
        now=now,
    )

    assert (await limiter.check(request)).allowed is True
    assert (await limiter.check(request)).allowed is True

    denied = await limiter.check(request)

    assert denied.allowed is False
    assert denied.remaining == 0
    assert denied.retry_after_seconds == 60


async def test_in_memory_rate_limiter_resets_after_window() -> None:
    limiter = InMemoryRateLimiter()
    org_id = uuid4()
    first = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

    assert (await limiter.check(_request(org_id, first))).allowed is True
    assert (await limiter.check(_request(org_id, first))).allowed is False

    later = first + timedelta(seconds=61)
    assert (await limiter.check(_request(org_id, later))).allowed is True


async def test_in_memory_rate_limiter_hashes_storage_keys() -> None:
    limiter = InMemoryRateLimiter()
    org_id = uuid4()

    await limiter.check(_request(org_id, datetime(2026, 8, 20, 12, 0, tzinfo=UTC)))

    key = next(iter(limiter.snapshot_keys()))
    assert str(org_id) not in key
    assert key.startswith("org:")


def _request(org_id: object, now: datetime) -> RateLimitRequest:
    return RateLimitRequest(
        org_id=org_id,
        user_id=None,
        limit=1,
        window_seconds=60,
        now=now,
    )
