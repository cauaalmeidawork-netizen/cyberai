"""Billing and entitlement errors."""

from __future__ import annotations

from cyberai.core.errors import ForbiddenError, QuotaExceededError, RateLimitedError


class EntitlementDeniedError(ForbiddenError):
    code = "entitlement_denied"
    title = "Entitlement Denied"
    default_detail = "The current plan does not allow this operation."


class BillingQuotaExceededError(QuotaExceededError):
    code = "quota_exceeded"


class BillingRateLimitExceededError(RateLimitedError):
    code = "rate_limited"
