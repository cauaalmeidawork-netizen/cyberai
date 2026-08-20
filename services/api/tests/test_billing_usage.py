"""Integration tests for persistent billing usage recording."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from cyberai.modules.billing.plans import StaticPlanCatalog
from cyberai.modules.billing.repository import BillingRepository
from cyberai.modules.billing.types import TokenEstimate
from cyberai.modules.modelgw.usage import UsageRecord, UsageStatus
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.models import Organization, UsageAggregateModel, UsageRecordModel, User

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_usage_recorder_is_idempotent_by_org_and_request_id(
    db: Database,
    test_org: Organization,
    test_user: User,
) -> None:
    repository = BillingRepository(db)
    record = UsageRecord(
        request_id="req-idempotent",
        organization_id=str(test_org.id),
        user_id=str(test_user.id),
        provider="mock",
        model_key="mock-analyst-1",
        provider_model="mock-analyst-1",
        task="chat",
        input_tokens=11,
        output_tokens=7,
        cached_input_tokens=0,
        latency_ms=42.0,
        time_to_first_token_ms=10.0,
        attempts=1,
        used_fallback=False,
        status=UsageStatus.SUCCESS,
        finish_reason="stop",
        error_code=None,
        estimated_cost_usd=Decimal("0"),
        occurred_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )

    plan = StaticPlanCatalog().get("free")
    await repository.reserve(
        org_id=test_org.id,
        request_id="req-idempotent",
        plan=plan,
        estimate=TokenEstimate(
            input_tokens=11,
            reserved_output_tokens=100,
            source="test",
            is_conservative=True,
        ),
    )

    assert await repository.record_usage_once(record) is True
    assert await repository.record_usage_once(record) is False

    async with db.session(TenantContext(org_id=test_org.id)) as session:
        count = await session.scalar(
            select(func.count())
            .select_from(UsageRecordModel)
            .where(
                UsageRecordModel.request_id == "req-idempotent",
                UsageRecordModel.org_id == test_org.id,
            )
        )
        aggregate = await session.scalar(
            select(UsageAggregateModel).where(UsageAggregateModel.org_id == test_org.id)
        )

    assert count == 1
    assert aggregate is not None
    assert aggregate.used_requests == 1
    assert aggregate.used_input_tokens == 11
    assert aggregate.used_output_tokens == 7
    assert aggregate.used_total_tokens == 18
    assert aggregate.reserved_requests == 0
    assert aggregate.reserved_input_tokens == 0
    assert aggregate.reserved_output_tokens == 0
    assert aggregate.reserved_total_tokens == 0
