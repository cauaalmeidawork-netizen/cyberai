"""Unit tests for billing enforcement before inference."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from cyberai.core.errors import QuotaExceededError
from cyberai.modules.billing.enforcement import LimitEnforcer
from cyberai.modules.billing.entitlements import EntitlementService
from cyberai.modules.billing.errors import EntitlementDeniedError
from cyberai.modules.billing.plans import StaticPlanCatalog
from cyberai.modules.billing.quotas import InMemoryQuotaStore
from cyberai.modules.billing.rate_limit import InMemoryRateLimiter
from cyberai.modules.billing.token_estimator import StaticTokenEstimator
from cyberai.modules.billing.types import Subscription
from cyberai.modules.inference import Message, Role, TextDelta
from cyberai.modules.modelgw import GatewayEvent, RequestPrincipal
from cyberai.modules.orchestrator.service import OrchestratorService
from cyberai.observability.metrics import InMemoryMetricsRecorder


@pytest.mark.asyncio
async def test_limit_enforcer_blocks_before_model_gateway_is_called() -> None:
    org_id = uuid4()
    quota_store = InMemoryQuotaStore()
    catalog = StaticPlanCatalog()
    subscription = Subscription(org_id=org_id, plan_key="free")
    free_plan = catalog.get("free")
    quota_store.force_usage(
        org_id=org_id,
        plan=free_plan,
        requests=free_plan.limits.monthly_requests,
    )
    metrics = InMemoryMetricsRecorder()
    enforcer = LimitEnforcer(
        plan_catalog=catalog,
        entitlement_service=EntitlementService(catalog),
        quota_store=quota_store,
        rate_limiter=InMemoryRateLimiter(),
        token_estimator=StaticTokenEstimator(input_tokens=1),
        subscription_provider=StaticSubscriptionProvider(subscription),
        metrics=metrics,
    )
    gateway = RecordingGateway()
    orchestrator = OrchestratorService(gateway, limit_enforcer=enforcer)

    with pytest.raises(QuotaExceededError):
        async for _event in orchestrator.stream_chat(
            messages=(Message(role=Role.USER, content="hello"),),
            model=None,
            max_tokens=16,
            temperature=0.2,
            principal=RequestPrincipal(
                org_id=str(org_id),
                user_id=str(uuid4()),
                request_id="req-blocked",
            ),
        ):
            pass

    assert gateway.called is False
    assert any(sample.name == "billing_quota_exceeded_total" for sample in metrics.samples)


@pytest.mark.asyncio
async def test_limit_enforcer_denies_disallowed_rag() -> None:
    org_id = uuid4()
    catalog = StaticPlanCatalog()
    enforcer = LimitEnforcer(
        plan_catalog=catalog,
        entitlement_service=EntitlementService(catalog),
        quota_store=InMemoryQuotaStore(),
        rate_limiter=InMemoryRateLimiter(),
        token_estimator=StaticTokenEstimator(input_tokens=1),
        subscription_provider=StaticSubscriptionProvider(
            Subscription(org_id=org_id, plan_key="free")
        ),
    )

    with pytest.raises(EntitlementDeniedError, match="RAG"):
        await enforcer.reserve_for_request(
            principal=RequestPrincipal(org_id=str(org_id), user_id=None, request_id="req-rag"),
            messages=(Message(role=Role.USER, content="hello"),),
            requested_model=None,
            max_output_tokens=16,
            rag_enabled=True,
        )


@dataclass(slots=True)
class StaticSubscriptionProvider:
    subscription: Subscription

    async def get_subscription(self, org_id: UUID) -> Subscription:
        assert org_id == self.subscription.org_id
        return self.subscription


class RecordingGateway:
    def __init__(self) -> None:
        self.called = False

    async def stream(self, _request: object) -> AsyncIterator[GatewayEvent]:
        self.called = True
        yield TextDelta(text="should not happen")
