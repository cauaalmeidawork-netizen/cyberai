"""External billing provider boundary and Stripe adapter."""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol

import httpx


class StripeSignatureError(ValueError):
    """Raised when a Stripe webhook signature cannot be verified."""


@dataclass(frozen=True, slots=True)
class BillingSession:
    id: str
    url: str


class BillingProvider(Protocol):
    async def create_customer(
        self,
        *,
        name: str,
        metadata: dict[str, str],
        idempotency_key: str,
    ) -> str: ...

    async def create_checkout_session(
        self,
        *,
        customer_id: str,
        plan_key: str,
        success_url: str,
        cancel_url: str,
        idempotency_key: str,
    ) -> BillingSession: ...

    async def create_portal_session(
        self,
        *,
        customer_id: str,
        return_url: str,
        idempotency_key: str,
    ) -> BillingSession: ...


class StripeBillingProvider:
    """Stripe adapter. No domain or orchestrator code imports Stripe details."""

    def __init__(
        self,
        *,
        api_key: str,
        price_ids: dict[str, str],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._price_ids = price_ids
        self._client = client or httpx.AsyncClient(base_url="https://api.stripe.com", timeout=15.0)

    async def create_customer(
        self,
        *,
        name: str,
        metadata: dict[str, str],
        idempotency_key: str,
    ) -> str:
        data: dict[str, str] = {"name": name}
        for key, value in metadata.items():
            data[f"metadata[{key}]"] = value
        response = await self._client.post(
            "/v1/customers",
            headers=self._headers(idempotency_key),
            data=data,
        )
        response.raise_for_status()
        return str(response.json()["id"])

    async def create_checkout_session(
        self,
        *,
        customer_id: str,
        plan_key: str,
        success_url: str,
        cancel_url: str,
        idempotency_key: str,
    ) -> BillingSession:
        price_id = self._price_ids[plan_key]
        response = await self._client.post(
            "/v1/checkout/sessions",
            headers=self._headers(idempotency_key),
            data={
                "mode": "subscription",
                "customer": customer_id,
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "allow_promotion_codes": "true",
            },
        )
        response.raise_for_status()
        data = response.json()
        return BillingSession(id=str(data["id"]), url=str(data["url"]))

    async def create_portal_session(
        self,
        *,
        customer_id: str,
        return_url: str,
        idempotency_key: str,
    ) -> BillingSession:
        response = await self._client.post(
            "/v1/billing_portal/sessions",
            headers=self._headers(idempotency_key),
            data={
                "customer": customer_id,
                "return_url": return_url,
            },
        )
        response.raise_for_status()
        data = response.json()
        return BillingSession(id=str(data["id"]), url=str(data["url"]))

    def _headers(self, idempotency_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": idempotency_key,
        }


def construct_stripe_event(
    *,
    raw_body: bytes,
    signature_header: str,
    webhook_secret: str,
    now: datetime | None = None,
    tolerance: timedelta = timedelta(minutes=5),
) -> dict[str, Any]:
    timestamp, signatures = _parse_signature_header(signature_header)
    current = now or datetime.now(UTC)
    signed_at = datetime.fromtimestamp(timestamp, tz=UTC)
    if abs((current - signed_at).total_seconds()) > tolerance.total_seconds():
        raise StripeSignatureError("Stripe webhook timestamp is outside tolerance.")

    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode()
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise StripeSignatureError("Stripe webhook signature is invalid.")

    data = json.loads(raw_body.decode("utf-8"))
    if not isinstance(data, dict):
        raise StripeSignatureError("Stripe webhook payload is invalid.")
    return data


def _parse_signature_header(header: str) -> tuple[int, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            timestamp = int(value)
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or not signatures:
        raise StripeSignatureError("Stripe webhook signature header is invalid.")
    return timestamp, signatures
