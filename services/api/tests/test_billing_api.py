"""Integration tests for tenant-scoped billing API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_billing_usage_and_limits_are_scoped_to_authenticated_tenant(
    app_client: AsyncClient,
    test_user_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {test_user_token}"}

    limits = await app_client.get("/api/v1/billing/limits?org_id=ignored", headers=headers)
    usage = await app_client.get("/api/v1/billing/usage?org_id=ignored", headers=headers)

    assert limits.status_code == 200
    assert usage.status_code == 200
    limits_body = limits.json()
    usage_body = usage.json()
    assert limits_body["plan"] == "free"
    assert {entry["resource"] for entry in limits_body["quotas"]} == {
        "requests",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }
    assert usage_body["plan"] == "free"
    assert all(entry["used"] == 0 for entry in usage_body["usage"])
