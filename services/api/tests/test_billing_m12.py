"""M12 real billing provider and webhook tests."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import parse_qs
from uuid import uuid4

import pytest
from httpx import AsyncClient, MockTransport, Request, Response
from sqlalchemy import select, text

from cyberai.core.config import Environment, load_settings
from cyberai.modules.billing.providers import (
    BillingSession,
    StripeBillingProvider,
    StripeSignatureError,
    construct_stripe_event,
)
from cyberai.modules.billing.repository import BillingRepository
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.models import (
    BillingWebhookEventModel,
    Organization,
    SubscriptionModel,
)


def test_stripe_signature_is_verified_against_raw_body() -> None:
    body = b'{"id":"evt_1","type":"customer.subscription.updated","data":{"object":{}}}'
    header = _stripe_signature(body, "whsec_test", timestamp=1_800_000_000)

    event = construct_stripe_event(
        raw_body=body,
        signature_header=header,
        webhook_secret="whsec_test",
        now=datetime.fromtimestamp(1_800_000_010, tz=UTC),
    )

    assert event["id"] == "evt_1"


def test_stripe_signature_rejects_invalid_body_before_parsing() -> None:
    tampered_body = b'{"id":'
    header = _stripe_signature(b'{"id":"evt_1"}', "whsec_test", timestamp=1_800_000_000)

    with pytest.raises(StripeSignatureError):
        construct_stripe_event(
            raw_body=tampered_body,
            signature_header=header,
            webhook_secret="whsec_test",
            now=datetime.fromtimestamp(1_800_000_010, tz=UTC),
        )


@pytest.mark.asyncio
async def test_stripe_provider_creates_checkout_and_portal_sessions() -> None:
    requests: list[Request] = []

    def handler(request: Request) -> Response:
        requests.append(request)
        if request.url.path.endswith("/v1/checkout/sessions"):
            return Response(200, json={"id": "cs_test", "url": "https://checkout.stripe.test"})
        if request.url.path.endswith("/v1/billing_portal/sessions"):
            return Response(200, json={"id": "bps_test", "url": "https://portal.stripe.test"})
        return Response(404)

    provider = StripeBillingProvider(
        api_key="sk_test",
        price_ids={"pro": "price_pro"},
        client=AsyncClient(transport=MockTransport(handler), base_url="https://api.stripe.com"),
    )

    checkout = await provider.create_checkout_session(
        customer_id="cus_1",
        plan_key="pro",
        success_url="https://app.test/billing/success",
        cancel_url="https://app.test/billing/cancel",
        idempotency_key="org-1:pro",
    )
    portal = await provider.create_portal_session(
        customer_id="cus_1",
        return_url="https://app.test/billing",
        idempotency_key="org-1:portal",
    )

    assert checkout.url == "https://checkout.stripe.test"
    assert portal.url == "https://portal.stripe.test"
    assert requests[0].headers["idempotency-key"] == "org-1:pro"
    checkout_form = parse_qs(requests[0].content.decode("utf-8"))
    assert checkout_form["line_items[0][price]"] == ["price_pro"]
    assert requests[1].headers["idempotency-key"] == "org-1:portal"


@pytest.mark.asyncio
async def test_webhook_event_is_persistently_idempotent(db: Database) -> None:
    repository = BillingRepository(db)
    org = await _create_org(db)
    event_id = f"evt_{uuid4().hex}"
    await repository.upsert_billing_customer(
        org_id=org.id,
        provider="stripe",
        provider_customer_id=f"cus_{uuid4().hex}",
    )

    first = await repository.begin_webhook_event(provider="stripe", event_id=event_id)
    duplicate = await repository.begin_webhook_event(provider="stripe", event_id=event_id)

    assert first.should_process is True
    assert duplicate.should_process is False

    await repository.mark_webhook_event_failed(
        provider="stripe",
        event_id=event_id,
        error_code="sync_failed",
    )

    async with db.session() as session:
        row = await session.scalar(
            select(BillingWebhookEventModel).where(BillingWebhookEventModel.event_id == event_id)
        )
        assert row is not None
        assert row.status == "failed"
        assert row.error_code == "sync_failed"

    await _cleanup_org(db, org.id)


@pytest.mark.asyncio
async def test_subscription_sync_keeps_entitlements_local(db: Database) -> None:
    repository = BillingRepository(db)
    org = await _create_org(db)
    provider_customer_id = f"cus_{uuid4().hex}"
    provider_subscription_id = f"sub_{uuid4().hex}"
    await repository.upsert_billing_customer(
        org_id=org.id,
        provider="stripe",
        provider_customer_id=provider_customer_id,
    )

    await repository.sync_provider_subscription(
        provider="stripe",
        provider_customer_id=provider_customer_id,
        provider_subscription_id=provider_subscription_id,
        provider_status="active",
        plan_key="pro",
        current_period_start=datetime(2026, 8, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert (await repository.get_subscription(org.id)).plan_key == "pro"

    await repository.sync_provider_subscription(
        provider="stripe",
        provider_customer_id=provider_customer_id,
        provider_subscription_id=provider_subscription_id,
        provider_status="past_due",
        plan_key="pro",
        current_period_start=datetime(2026, 8, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert (await repository.get_subscription(org.id)).plan_key == "free"

    async with db.session(TenantContext(org_id=org.id)) as session:
        row = await session.scalar(
            select(SubscriptionModel).where(
                SubscriptionModel.org_id == org.id,
                SubscriptionModel.provider_subscription_id == provider_subscription_id,
            )
        )
        assert row is not None
        assert row.status == "past_due"
        assert row.provider_status == "past_due"

    await _cleanup_org(db, org.id)


def test_production_requires_stripe_secrets_when_billing_provider_is_stripe() -> None:
    with pytest.raises(ValueError, match="stripe_secret_key"):
        load_settings(
            environment=Environment.PRODUCTION,
            database={"url": "postgresql+asyncpg://cyberai:secure-password@db:5432/cyberai"},
            redis={"url": "redis://redis:6379/0"},
            app={
                "cors_origins": ["https://app.cyberai.dev"],
                "trusted_hosts": ["api.cyberai.dev"],
                "expose_docs": False,
            },
            logging={"format": "json"},
            auth=_prod_auth(),
            models={"default_model": "openai-compatible-chat", "fallback_models": []},
            openai_compatible={"enabled": True, "api_key": "test-key"},
            billing={"provider": "stripe"},
        )


@pytest.mark.asyncio
async def test_billing_provider_can_create_customer() -> None:
    captured: list[Request] = []

    def handler(request: Request) -> Response:
        captured.append(request)
        return Response(200, json={"id": "cus_created"})

    provider = StripeBillingProvider(
        api_key="sk_test",
        price_ids={"pro": "price_pro"},
        client=AsyncClient(transport=MockTransport(handler), base_url="https://api.stripe.com"),
    )

    customer_id = await provider.create_customer(
        name="Acme",
        metadata={"org_id": "org-1"},
        idempotency_key="customer:org-1",
    )

    assert customer_id == "cus_created"
    assert captured[0].url.path.endswith("/v1/customers")
    assert captured[0].headers["idempotency-key"] == "customer:org-1"


class FakeBillingProvider:
    def __init__(self) -> None:
        self.created_customers: list[dict[str, object]] = []
        self.checkout_calls: list[dict[str, object]] = []
        self.portal_calls: list[dict[str, object]] = []

    async def create_customer(
        self,
        *,
        name: str,
        metadata: dict[str, str],
        idempotency_key: str,
    ) -> str:
        self.created_customers.append(
            {"name": name, "metadata": metadata, "idempotency_key": idempotency_key}
        )
        return "cus_fake"

    async def create_checkout_session(
        self,
        *,
        customer_id: str,
        plan_key: str,
        success_url: str,
        cancel_url: str,
        idempotency_key: str,
    ) -> BillingSession:
        self.checkout_calls.append(
            {
                "customer_id": customer_id,
                "plan_key": plan_key,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "idempotency_key": idempotency_key,
            }
        )
        return BillingSession(id="cs_fake", url="https://checkout.test")

    async def create_portal_session(
        self,
        *,
        customer_id: str,
        return_url: str,
        idempotency_key: str,
    ) -> BillingSession:
        self.portal_calls.append(
            {
                "customer_id": customer_id,
                "return_url": return_url,
                "idempotency_key": idempotency_key,
            }
        )
        return BillingSession(id="bps_fake", url="https://portal.test")


def _stripe_signature(body: bytes, secret: str, *, timestamp: int) -> str:
    signed = f"{timestamp}.{body.decode('utf-8')}".encode()
    digest = hmac.new(secret.encode("utf-8"), signed, sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _prod_auth() -> dict[str, object]:
    return {
        "jwt_secret": "prod-jwt-secret-with-enough-entropy",
        "legacy_bearer_enabled": False,
        "oidc_enabled": True,
        "oidc_issuer": "https://idp.example.com",
        "oidc_client_id": "cyberai",
        "oidc_client_secret": "super-secret",
        "session_secret": "session-secret-with-enough-entropy",
        "csrf_secret": "csrf-secret-with-enough-entropy",
        "session_secure_cookie": True,
    }


async def _create_org(db: Database) -> Organization:
    org = Organization(slug=f"billing-{uuid4().hex[:8]}", display_name="Billing Org")
    async with db.session() as session:
        session.add(org)
        await session.flush()
    return org


async def _cleanup_org(db: Database, org_id: object) -> None:
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM subscriptions WHERE org_id = :org_id"), {"org_id": org_id}
        )
        await session.execute(
            text("DELETE FROM billing_customers WHERE org_id = :org_id"), {"org_id": org_id}
        )
        await session.execute(
            text("DELETE FROM usage_reservations WHERE org_id = :org_id"), {"org_id": org_id}
        )
        await session.execute(
            text("DELETE FROM usage_records WHERE org_id = :org_id"), {"org_id": org_id}
        )
        await session.execute(
            text("DELETE FROM usage_aggregates WHERE org_id = :org_id"), {"org_id": org_id}
        )
        await session.execute(
            text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org_id}
        )
