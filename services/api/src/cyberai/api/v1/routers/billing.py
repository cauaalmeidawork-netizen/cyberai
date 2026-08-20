"""Tenant-scoped billing usage and limits API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cyberai.api.auth import CurrentUserDep
from cyberai.api.deps import BillingRepositoryDep, PlanCatalogDep
from cyberai.modules.billing.types import QuotaSnapshot

router = APIRouter(tags=["billing"], prefix="/billing")


class QuotaOut(BaseModel):
    resource: str
    used: int
    reserved: int
    limit: int
    remaining: int
    period_start: datetime
    period_end: datetime


class BillingLimitsOut(BaseModel):
    plan: str
    quotas: list[QuotaOut]
    rag_allowed: bool
    document_limit: int
    allowed_models: list[str] | None


class BillingUsageOut(BaseModel):
    plan: str
    usage: list[QuotaOut]


@router.get("/limits", response_model=BillingLimitsOut)
async def get_billing_limits(
    user: CurrentUserDep,
    repository: BillingRepositoryDep,
    plan_catalog: PlanCatalogDep,
) -> BillingLimitsOut:
    subscription = await repository.get_subscription(user.org_id)
    plan = plan_catalog.get(subscription.plan_key)
    snapshots = await repository.snapshots(org_id=user.org_id, plan=plan)
    return BillingLimitsOut(
        plan=plan.key,
        quotas=[_quota_out(snapshot) for snapshot in snapshots],
        rag_allowed=plan.limits.rag_allowed,
        document_limit=plan.limits.document_limit,
        allowed_models=(
            sorted(plan.limits.allowed_models) if plan.limits.allowed_models is not None else None
        ),
    )


@router.get("/usage", response_model=BillingUsageOut)
async def get_billing_usage(
    user: CurrentUserDep,
    repository: BillingRepositoryDep,
    plan_catalog: PlanCatalogDep,
) -> BillingUsageOut:
    subscription = await repository.get_subscription(user.org_id)
    plan = plan_catalog.get(subscription.plan_key)
    snapshots = await repository.snapshots(org_id=user.org_id, plan=plan)
    return BillingUsageOut(
        plan=plan.key,
        usage=[_quota_out(snapshot) for snapshot in snapshots],
    )


def _quota_out(snapshot: QuotaSnapshot) -> QuotaOut:
    return QuotaOut(
        resource=snapshot.resource.value,
        used=snapshot.used,
        reserved=snapshot.reserved,
        limit=snapshot.limit,
        remaining=snapshot.remaining,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
    )
