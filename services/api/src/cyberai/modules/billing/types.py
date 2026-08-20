"""Provider-neutral billing and quota types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class QuotaResource(StrEnum):
    REQUESTS = "requests"
    INPUT_TOKENS = "input_tokens"
    OUTPUT_TOKENS = "output_tokens"
    TOTAL_TOKENS = "total_tokens"
    DOCUMENTS = "documents"


@dataclass(frozen=True, slots=True)
class PlanLimits:
    monthly_requests: int
    monthly_input_tokens: int
    monthly_output_tokens: int
    monthly_total_tokens: int
    allowed_models: frozenset[str] | None
    rag_allowed: bool
    document_limit: int
    storage_bytes: int | None = None
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    def limit_for(self, resource: QuotaResource) -> int:
        if resource is QuotaResource.REQUESTS:
            return self.monthly_requests
        if resource is QuotaResource.INPUT_TOKENS:
            return self.monthly_input_tokens
        if resource is QuotaResource.OUTPUT_TOKENS:
            return self.monthly_output_tokens
        if resource is QuotaResource.TOTAL_TOKENS:
            return self.monthly_total_tokens
        if resource is QuotaResource.DOCUMENTS:
            return self.document_limit
        raise ValueError(f"Unsupported quota resource: {resource}")


@dataclass(frozen=True, slots=True)
class Plan:
    key: str
    display_name: str
    limits: PlanLimits


@dataclass(frozen=True, slots=True)
class Subscription:
    org_id: UUID
    plan_key: str


@dataclass(frozen=True, slots=True)
class EntitlementDecision:
    allowed: bool
    reason: str | None = None
    resource: str | None = None


@dataclass(frozen=True, slots=True)
class BillingPeriod:
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    resource: QuotaResource
    used: int
    reserved: int
    limit: int
    period_start: datetime
    period_end: datetime

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used - self.reserved, 0)


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    input_tokens: int
    reserved_output_tokens: int
    source: str
    is_conservative: bool

    @property
    def total_reserved_tokens(self) -> int:
        return self.input_tokens + self.reserved_output_tokens

    def resource_amount(self, resource: QuotaResource) -> int:
        if resource is QuotaResource.INPUT_TOKENS:
            return self.input_tokens
        if resource is QuotaResource.OUTPUT_TOKENS:
            return self.reserved_output_tokens
        if resource is QuotaResource.TOTAL_TOKENS:
            return self.total_reserved_tokens
        if resource is QuotaResource.REQUESTS:
            return 1
        raise ValueError(f"Token estimate does not cover resource: {resource}")


@dataclass(frozen=True, slots=True)
class BillingReservation:
    org_id: UUID
    request_id: str
    plan_key: str
    period_start: datetime
    period_end: datetime
    input_tokens: int
    output_tokens: int
    total_tokens: int
