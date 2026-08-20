"""Unit tests for billing plans, entitlements, quotas and token estimates."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from cyberai.modules.billing.entitlements import EntitlementService
from cyberai.modules.billing.plans import StaticPlanCatalog
from cyberai.modules.billing.quotas import monthly_period
from cyberai.modules.billing.types import QuotaResource, Subscription, TokenEstimate


def test_static_plan_catalog_contains_enterprise_plans() -> None:
    catalog = StaticPlanCatalog()

    assert {plan.key for plan in catalog.list_plans()} == {
        "free",
        "pro",
        "business",
        "enterprise",
    }
    assert catalog.get("free").limits.monthly_requests > 0
    assert catalog.get("enterprise").limits.allowed_models is None


def test_entitlements_enforce_model_and_rag_restrictions() -> None:
    catalog = StaticPlanCatalog()
    service = EntitlementService(catalog)
    subscription = Subscription(org_id=uuid4(), plan_key="free")

    assert service.can_use_model(subscription, "mock-analyst-1").allowed is True
    denied_model = service.can_use_model(subscription, "openai-compatible-chat")
    assert denied_model.allowed is False
    assert denied_model.reason == "model_not_allowed"

    denied_rag = service.can_use_rag(subscription)
    assert denied_rag.allowed is False
    assert denied_rag.reason == "rag_not_allowed"


def test_entitlements_enforce_document_limit() -> None:
    catalog = StaticPlanCatalog()
    service = EntitlementService(catalog)
    subscription = Subscription(org_id=uuid4(), plan_key="free")
    limit = catalog.get("free").limits.document_limit

    assert service.can_ingest_document(subscription, limit - 1).allowed is True
    denied = service.can_ingest_document(subscription, limit)

    assert denied.allowed is False
    assert denied.reason == "document_limit_exceeded"


def test_monthly_period_uses_utc_boundaries() -> None:
    now = datetime(2026, 8, 20, 12, 30, tzinfo=UTC)

    period = monthly_period(now)

    assert period.start == datetime(2026, 8, 1, tzinfo=UTC)
    assert period.end == datetime(2026, 9, 1, tzinfo=UTC)


def test_monthly_period_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        monthly_period(datetime.fromisoformat("2026-08-20T12:30:00"))


def test_token_estimate_is_explicitly_conservative() -> None:
    estimate = TokenEstimate(
        input_tokens=10,
        reserved_output_tokens=128,
        source="provider_count_tokens",
        is_conservative=True,
    )

    assert estimate.total_reserved_tokens == 138
    assert estimate.resource_amount(QuotaResource.INPUT_TOKENS) == 10
    assert estimate.resource_amount(QuotaResource.OUTPUT_TOKENS) == 128
    assert estimate.resource_amount(QuotaResource.TOTAL_TOKENS) == 138
