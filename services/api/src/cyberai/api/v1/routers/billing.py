"""Tenant-scoped billing usage and limits API."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from cyberai.api.auth import CurrentUserDep, Permission, require_csrf, require_permission
from cyberai.api.deps import BillingProviderDep, BillingRepositoryDep, PlanCatalogDep, SettingsDep
from cyberai.core.errors import ConflictError, ServiceUnavailableError, ValidationFailedError
from cyberai.modules.billing.providers import StripeSignatureError, construct_stripe_event
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
    subscription_status: str
    quotas: list[QuotaOut]
    rag_allowed: bool
    document_limit: int
    allowed_models: list[str] | None
    checkout_available: bool = False
    portal_available: bool = False


class BillingUsageOut(BaseModel):
    plan: str
    subscription_status: str
    usage: list[QuotaOut]


class CheckoutRequest(BaseModel):
    plan: str


class BillingSessionOut(BaseModel):
    url: str


@router.get("/limits", response_model=BillingLimitsOut)
async def get_billing_limits(
    user: CurrentUserDep,
    repository: BillingRepositoryDep,
    plan_catalog: PlanCatalogDep,
    settings: SettingsDep,
) -> BillingLimitsOut:
    require_permission(user, Permission.BILLING_READ)
    subscription = await repository.get_subscription(user.org_id)
    plan = plan_catalog.get(subscription.plan_key)
    snapshots = await repository.snapshots(org_id=user.org_id, plan=plan)
    return BillingLimitsOut(
        plan=plan.key,
        subscription_status=subscription.status,
        quotas=[_quota_out(snapshot) for snapshot in snapshots],
        rag_allowed=plan.limits.rag_allowed,
        document_limit=plan.limits.document_limit,
        allowed_models=(
            sorted(plan.limits.allowed_models) if plan.limits.allowed_models is not None else None
        ),
        checkout_available=settings.billing.provider == "stripe",
        portal_available=settings.billing.provider == "stripe",
    )


@router.get("/usage", response_model=BillingUsageOut)
async def get_billing_usage(
    user: CurrentUserDep,
    repository: BillingRepositoryDep,
    plan_catalog: PlanCatalogDep,
) -> BillingUsageOut:
    require_permission(user, Permission.BILLING_READ)
    subscription = await repository.get_subscription(user.org_id)
    plan = plan_catalog.get(subscription.plan_key)
    snapshots = await repository.snapshots(org_id=user.org_id, plan=plan)
    return BillingUsageOut(
        plan=plan.key,
        subscription_status=subscription.status,
        usage=[_quota_out(snapshot) for snapshot in snapshots],
    )


@router.post("/checkout", response_model=BillingSessionOut)
async def create_checkout_session(
    payload: CheckoutRequest,
    request: Request,
    user: CurrentUserDep,
    provider: BillingProviderDep,
    repository: BillingRepositoryDep,
    plan_catalog: PlanCatalogDep,
    settings: SettingsDep,
) -> BillingSessionOut:
    require_permission(user, Permission.BILLING_READ)
    await require_csrf(request=request, db=repository.database, settings=settings)
    if provider is None:
        raise ServiceUnavailableError("Billing checkout is not configured.")
    if payload.plan == "free":
        raise ValidationFailedError("Free plan does not require checkout.")
    plan_catalog.get(payload.plan)
    if not settings.billing.checkout_success_url or not settings.billing.checkout_cancel_url:
        raise ServiceUnavailableError("Billing checkout is not configured.")

    customer = await repository.get_billing_customer(org_id=user.org_id, provider="stripe")
    if customer is None:
        customer_id = await provider.create_customer(
            name=f"CyberAI organization {user.org_id}",
            metadata={"org_id": str(user.org_id)},
            idempotency_key=f"stripe-customer:{user.org_id}",
        )
        customer = await repository.upsert_billing_customer(
            org_id=user.org_id,
            provider="stripe",
            provider_customer_id=customer_id,
        )
    session = await provider.create_checkout_session(
        customer_id=customer.provider_customer_id,
        plan_key=payload.plan,
        success_url=settings.billing.checkout_success_url,
        cancel_url=settings.billing.checkout_cancel_url,
        idempotency_key=f"stripe-checkout:{user.org_id}:{payload.plan}",
    )
    return BillingSessionOut(url=session.url)


@router.post("/portal", response_model=BillingSessionOut)
async def create_portal_session(
    request: Request,
    user: CurrentUserDep,
    provider: BillingProviderDep,
    repository: BillingRepositoryDep,
    settings: SettingsDep,
) -> BillingSessionOut:
    require_permission(user, Permission.BILLING_READ)
    await require_csrf(request=request, db=repository.database, settings=settings)
    if provider is None or not settings.billing.portal_return_url:
        raise ServiceUnavailableError("Billing portal is not configured.")
    customer = await repository.get_billing_customer(org_id=user.org_id, provider="stripe")
    if customer is None:
        raise ConflictError("No billing customer exists for this organization.")
    session = await provider.create_portal_session(
        customer_id=customer.provider_customer_id,
        return_url=settings.billing.portal_return_url,
        idempotency_key=f"stripe-portal:{user.org_id}",
    )
    return BillingSessionOut(url=session.url)


@router.post("/webhooks/stripe")
async def handle_stripe_webhook(
    request: Request,
    repository: BillingRepositoryDep,
    settings: SettingsDep,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, str]:
    if settings.billing.stripe_webhook_secret is None:
        raise ServiceUnavailableError("Stripe webhooks are not configured.")
    if stripe_signature is None:
        raise ValidationFailedError("Missing Stripe-Signature header.")
    raw_body = await request.body()
    try:
        event = construct_stripe_event(
            raw_body=raw_body,
            signature_header=stripe_signature,
            webhook_secret=settings.billing.stripe_webhook_secret.get_secret_value(),
        )
    except (StripeSignatureError, ValueError) as exc:
        raise ValidationFailedError("Invalid Stripe webhook signature.") from exc

    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    decision = await repository.begin_webhook_event(
        provider="stripe", event_id=event_id, event_type=event_type
    )
    if not decision.should_process:
        return {"status": decision.status}

    try:
        await _process_stripe_event(event, repository, settings)
    except Exception as exc:
        await repository.mark_webhook_event_failed(
            provider="stripe",
            event_id=event_id,
            error_code=type(exc).__name__,
        )
        raise
    await repository.mark_webhook_event_processed(provider="stripe", event_id=event_id)
    return {"status": "processed"}


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


async def _process_stripe_event(
    event: dict[str, object],
    repository: BillingRepositoryDep,
    settings: SettingsDep,
) -> None:
    event_type = str(event.get("type") or "")
    if event_type not in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        return
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("object"), dict):
        raise ValueError("invalid_stripe_event_object")
    subscription = data["object"]
    provider_customer_id = str(subscription["customer"])
    provider_subscription_id = str(subscription["id"])
    provider_status = str(subscription["status"])
    price_id = _subscription_price_id(subscription)
    plan_key = _plan_for_price(settings, price_id)
    await repository.sync_provider_subscription(
        provider="stripe",
        provider_customer_id=provider_customer_id,
        provider_subscription_id=provider_subscription_id,
        provider_status=provider_status,
        plan_key=plan_key,
        current_period_start=_timestamp(subscription.get("current_period_start")),
        current_period_end=_timestamp(subscription.get("current_period_end")),
    )


def _subscription_price_id(subscription: dict[str, object]) -> str:
    items = subscription.get("items")
    if not isinstance(items, dict) or not isinstance(items.get("data"), list):
        raise ValueError("missing_subscription_price")
    first = items["data"][0]
    if not isinstance(first, dict) or not isinstance(first.get("price"), dict):
        raise ValueError("missing_subscription_price")
    return str(first["price"]["id"])


def _plan_for_price(settings: SettingsDep, price_id: str) -> str:
    for plan_key, configured_price_id in settings.billing.stripe_price_ids.items():
        if configured_price_id == price_id:
            return plan_key
    raise ValueError("unknown_stripe_price")


def _timestamp(raw: object) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, int | str):
        raise ValueError("invalid_subscription_timestamp")
    return datetime.fromtimestamp(int(raw), tz=UTC)
