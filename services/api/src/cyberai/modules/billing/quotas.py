"""Quota periods and in-memory quota store used by unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from cyberai.modules.billing.errors import BillingQuotaExceededError
from cyberai.modules.billing.types import (
    BillingPeriod,
    BillingReservation,
    Plan,
    QuotaResource,
    QuotaSnapshot,
    TokenEstimate,
)


def monthly_period(now: datetime | None = None) -> BillingPeriod:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("monthly_period requires a timezone-aware datetime")
    current = current.astimezone(UTC)
    start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return BillingPeriod(start=start, end=end)


@dataclass(slots=True)
class _Counters:
    used_requests: int = 0
    used_input_tokens: int = 0
    used_output_tokens: int = 0
    used_total_tokens: int = 0
    reserved_requests: int = 0
    reserved_input_tokens: int = 0
    reserved_output_tokens: int = 0
    reserved_total_tokens: int = 0


class InMemoryQuotaStore:
    """Simple quota store with reservation semantics for unit tests."""

    def __init__(self) -> None:
        self._counters: dict[tuple[UUID, datetime], _Counters] = {}

    def force_usage(self, *, org_id: UUID, plan: Plan, requests: int = 0) -> None:
        period = monthly_period()
        counters = self._get(org_id, period)
        counters.used_requests = requests
        counters.used_input_tokens = plan.limits.monthly_input_tokens if requests else 0
        counters.used_output_tokens = 0
        counters.used_total_tokens = counters.used_input_tokens

    async def reserve(
        self,
        *,
        org_id: UUID,
        request_id: str,
        plan: Plan,
        estimate: TokenEstimate,
        now: datetime | None = None,
    ) -> BillingReservation:
        period = monthly_period(now)
        counters = self._get(org_id, period)
        proposed = {
            QuotaResource.REQUESTS: counters.used_requests + counters.reserved_requests + 1,
            QuotaResource.INPUT_TOKENS: (
                counters.used_input_tokens + counters.reserved_input_tokens + estimate.input_tokens
            ),
            QuotaResource.OUTPUT_TOKENS: (
                counters.used_output_tokens
                + counters.reserved_output_tokens
                + estimate.reserved_output_tokens
            ),
            QuotaResource.TOTAL_TOKENS: (
                counters.used_total_tokens
                + counters.reserved_total_tokens
                + estimate.total_reserved_tokens
            ),
        }
        for resource, value in proposed.items():
            if value > plan.limits.limit_for(resource):
                raise BillingQuotaExceededError(
                    f"Quota exceeded for {resource.value}.",
                    extra={"resource": resource.value},
                )
        counters.reserved_requests += 1
        counters.reserved_input_tokens += estimate.input_tokens
        counters.reserved_output_tokens += estimate.reserved_output_tokens
        counters.reserved_total_tokens += estimate.total_reserved_tokens
        return BillingReservation(
            org_id=org_id,
            request_id=request_id,
            plan_key=plan.key,
            period_start=period.start,
            period_end=period.end,
            input_tokens=estimate.input_tokens,
            output_tokens=estimate.reserved_output_tokens,
            total_tokens=estimate.total_reserved_tokens,
        )

    async def snapshots(
        self,
        *,
        org_id: UUID,
        plan: Plan,
        now: datetime | None = None,
    ) -> tuple[QuotaSnapshot, ...]:
        period = monthly_period(now)
        counters = self._get(org_id, period)
        return (
            QuotaSnapshot(
                QuotaResource.REQUESTS,
                counters.used_requests,
                counters.reserved_requests,
                plan.limits.monthly_requests,
                period.start,
                period.end,
            ),
            QuotaSnapshot(
                QuotaResource.INPUT_TOKENS,
                counters.used_input_tokens,
                counters.reserved_input_tokens,
                plan.limits.monthly_input_tokens,
                period.start,
                period.end,
            ),
            QuotaSnapshot(
                QuotaResource.OUTPUT_TOKENS,
                counters.used_output_tokens,
                counters.reserved_output_tokens,
                plan.limits.monthly_output_tokens,
                period.start,
                period.end,
            ),
            QuotaSnapshot(
                QuotaResource.TOTAL_TOKENS,
                counters.used_total_tokens,
                counters.reserved_total_tokens,
                plan.limits.monthly_total_tokens,
                period.start,
                period.end,
            ),
        )

    def _get(self, org_id: UUID, period: BillingPeriod) -> _Counters:
        key = (org_id, period.start)
        counters = self._counters.get(key)
        if counters is None:
            counters = _Counters()
            self._counters[key] = counters
        return counters
