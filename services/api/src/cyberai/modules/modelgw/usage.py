"""Usage and cost accounting.

Every model call produces exactly one ``UsageRecord``. This is the raw material
for cost per request, per user, per organization, per model and per provider,
and therefore for gross margin - so it is captured from the first milestone,
before there is anything to bill.

Two properties are deliberate:

* the record is provider-neutral. Billing must never depend on the response
  shape of a particular vendor, because the vendor is expected to change;
* ``estimated_cost_usd`` is computed from our own price table, while
  ``actual_cost_usd`` stays empty until a provider reports a real figure. Being
  able to compare the two is how pricing drift gets caught.

M0 writes records to the log. The persistent ledger arrives with the metering
module; the shape does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from cyberai.core.logging import get_logger
from cyberai.modules.inference import TokenUsage

logger = get_logger(__name__)

_TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)


class UsageStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


def estimate_cost_usd(
    usage: TokenUsage,
    *,
    input_cost_per_mtok: Decimal,
    output_cost_per_mtok: Decimal,
    cached_input_cost_per_mtok: Decimal = Decimal("0"),
) -> Decimal:
    """Cost of one call from our own price table, in USD.

    Cached input tokens are priced separately: on providers that support prompt
    caching they are a fraction of the normal input price, and a long, stable
    system prompt makes them the majority of the input.
    """
    billable_input = Decimal(usage.billable_input_tokens)
    cached_input = Decimal(usage.cached_input_tokens)
    output = Decimal(usage.output_tokens)

    total = (
        billable_input * input_cost_per_mtok
        + cached_input * cached_input_cost_per_mtok
        + output * output_cost_per_mtok
    ) / _TOKENS_PER_PRICE_UNIT
    return total.quantize(Decimal("0.00000001"))


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """One accounted model call."""

    request_id: str | None
    organization_id: str | None
    user_id: str | None

    provider: str
    model_key: str
    provider_model: str
    task: str

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int

    latency_ms: float
    time_to_first_token_ms: float | None
    attempts: int
    used_fallback: bool

    status: UsageStatus
    finish_reason: str | None
    error_code: str | None

    estimated_cost_usd: Decimal
    actual_cost_usd: Decimal | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_log_fields(self) -> dict[str, Any]:
        """Flat representation for logs and, later, for the ledger table."""
        return {
            "request_id": self.request_id,
            "org_id": self.organization_id,
            "user_id": self.user_id,
            "provider": self.provider,
            "model_key": self.model_key,
            "provider_model": self.provider_model,
            "task": self.task,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "ttft_ms": (
                round(self.time_to_first_token_ms, 2)
                if self.time_to_first_token_ms is not None
                else None
            ),
            "attempts": self.attempts,
            "used_fallback": self.used_fallback,
            "status": self.status.value,
            "finish_reason": self.finish_reason,
            "error_code": self.error_code,
            "estimated_cost_usd": str(self.estimated_cost_usd),
            "actual_cost_usd": (
                str(self.actual_cost_usd) if self.actual_cost_usd is not None else None
            ),
            "occurred_at": self.occurred_at.isoformat(),
        }


class UsageSink(Protocol):
    """Where usage records go. Must never raise into the request path."""

    async def record(self, record: UsageRecord) -> None: ...


class LoggingUsageSink:
    """Writes the record as a structured log event (M0 default)."""

    async def record(self, record: UsageRecord) -> None:
        logger.info("inference.usage", **record.as_log_fields())


class NullUsageSink:
    """Discards records. Used by tests that assert on behaviour, not accounting."""

    async def record(self, record: UsageRecord) -> None:
        return None


class CollectingUsageSink:
    """Keeps records in memory so tests can assert on the ledger."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    async def record(self, record: UsageRecord) -> None:
        self.records.append(record)
