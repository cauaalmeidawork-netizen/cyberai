"""Pre-inference billing enforcement."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cyberai.core.errors import QuotaExceededError
from cyberai.modules.billing.entitlements import EntitlementService
from cyberai.modules.billing.errors import BillingRateLimitExceededError, EntitlementDeniedError
from cyberai.modules.billing.plans import StaticPlanCatalog
from cyberai.modules.billing.rate_limit import RateLimiter, RateLimitRequest
from cyberai.modules.billing.token_estimator import TokenEstimator
from cyberai.modules.billing.types import (
    BillingReservation,
    EntitlementDecision,
    Plan,
    Subscription,
    TokenEstimate,
)
from cyberai.modules.inference import Message
from cyberai.modules.modelgw import RequestPrincipal
from cyberai.observability.metrics import MetricsRecorder, NoopMetricsRecorder


class SubscriptionProvider(Protocol):
    async def get_subscription(self, org_id: UUID) -> Subscription: ...


class QuotaStore(Protocol):
    async def reserve(
        self,
        *,
        org_id: UUID,
        request_id: str,
        plan: Plan,
        estimate: TokenEstimate,
    ) -> BillingReservation: ...


class LimitEnforcer:
    def __init__(
        self,
        *,
        plan_catalog: StaticPlanCatalog,
        entitlement_service: EntitlementService,
        quota_store: QuotaStore,
        rate_limiter: RateLimiter,
        token_estimator: TokenEstimator,
        subscription_provider: SubscriptionProvider,
        default_model_key: str = "mock-analyst-1",
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._plan_catalog = plan_catalog
        self._entitlements = entitlement_service
        self._quota_store = quota_store
        self._rate_limiter = rate_limiter
        self._token_estimator = token_estimator
        self._subscription_provider = subscription_provider
        self._default_model_key = default_model_key
        self._metrics = metrics or NoopMetricsRecorder()

    async def reserve_for_request(
        self,
        *,
        principal: RequestPrincipal,
        messages: tuple[Message, ...],
        requested_model: str | None,
        max_output_tokens: int,
        rag_enabled: bool,
    ) -> BillingReservation | None:
        if principal.org_id is None or principal.request_id is None:
            return None
        org_id = UUID(principal.org_id)
        model_key = requested_model or self._default_model_key
        subscription = await self._subscription_provider.get_subscription(org_id)
        plan = self._plan_catalog.get(subscription.plan_key)

        self._check_entitlements(subscription, model_key=model_key, rag_enabled=rag_enabled)

        rate_status = "allowed"
        rate = await self._rate_limiter.check(
            RateLimitRequest(
                org_id=org_id,
                user_id=principal.user_id,
                limit=plan.limits.rate_limit_requests,
                window_seconds=plan.limits.rate_limit_window_seconds,
            )
        )
        if not rate.allowed:
            rate_status = "exceeded"
            self._metrics.counter(
                "rate_limit_checks_total", labels={"scope": "org", "status": rate_status}
            ).add()
            self._metrics.counter(
                "rate_limit_exceeded_total", labels={"scope": "org", "status": rate_status}
            ).add()
            raise BillingRateLimitExceededError(
                extra={"retry_after_seconds": rate.retry_after_seconds}
            )
        self._metrics.counter(
            "rate_limit_checks_total", labels={"scope": "org", "status": rate_status}
        ).add()

        estimate = self._token_estimator.estimate(
            messages=messages,
            model_key=model_key,
            max_output_tokens=max_output_tokens,
        )
        try:
            reservation = await self._quota_store.reserve(
                org_id=org_id,
                request_id=principal.request_id,
                plan=plan,
                estimate=estimate,
            )
        except QuotaExceededError:
            self._metrics.counter(
                "billing_quota_exceeded_total",
                labels={"plan": plan.key, "resource": "monthly", "status": "exceeded"},
            ).add()
            self._metrics.counter(
                "billing_quota_checks_total",
                labels={"plan": plan.key, "resource": "monthly", "status": "exceeded"},
            ).add()
            raise
        self._metrics.counter(
            "billing_quota_checks_total",
            labels={"plan": plan.key, "resource": "monthly", "status": "allowed"},
        ).add()
        return reservation

    async def check_entitlements(
        self,
        *,
        principal: RequestPrincipal,
        requested_model: str | None,
        rag_enabled: bool,
    ) -> None:
        if principal.org_id is None:
            return
        org_id = UUID(principal.org_id)
        model_key = requested_model or self._default_model_key
        subscription = await self._subscription_provider.get_subscription(org_id)
        self._check_entitlements(subscription, model_key=model_key, rag_enabled=rag_enabled)

    def _check_entitlements(
        self,
        subscription: Subscription,
        *,
        model_key: str,
        rag_enabled: bool,
    ) -> None:
        self._deny_if_needed(self._entitlements.can_make_request(subscription), resource="request")
        self._deny_if_needed(
            self._entitlements.can_use_model(subscription, model_key), resource="model"
        )
        if rag_enabled:
            self._deny_if_needed(
                self._entitlements.can_use_rag(subscription),
                detail="RAG is not allowed by the current plan.",
                resource="rag",
            )

    def _deny_if_needed(
        self,
        decision: EntitlementDecision,
        detail: str | None = None,
        resource: str = "unknown",
    ) -> None:
        if decision.allowed:
            return
        self._metrics.counter(
            "billing_entitlement_denied_total",
            labels={"resource": resource, "status": "denied"},
        ).add()
        raise EntitlementDeniedError(
            detail or f"Operation denied by plan entitlement: {decision.reason}.",
            extra={"reason": decision.reason},
        )


class NoopLimitEnforcer:
    async def check_entitlements(
        self,
        *,
        principal: RequestPrincipal,
        requested_model: str | None,
        rag_enabled: bool,
    ) -> None:
        return None

    async def reserve_for_request(
        self,
        *,
        principal: RequestPrincipal,
        messages: tuple[Message, ...],
        requested_model: str | None,
        max_output_tokens: int,
        rag_enabled: bool,
    ) -> None:
        return None
