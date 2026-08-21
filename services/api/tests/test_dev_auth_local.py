"""Local-only development authentication tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from cyberai.core.config import Environment, load_settings
from cyberai.main import create_app
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.models import Identity, Membership, Organization, User


@pytest.mark.asyncio
async def test_dev_login_is_blocked_outside_local(db: Database) -> None:
    settings = load_settings(environment=Environment.CI)
    app = create_app(settings)
    async with _client(app) as client:
        response = await client.get("/api/v1/auth/dev-login", follow_redirects=False)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dev_login_creates_reuses_identity_and_authenticates(db: Database) -> None:
    app = create_app(load_settings(environment=Environment.LOCAL))
    async with _client(app) as client:
        first = await client.get("/api/v1/auth/dev-login?return_to=%2F", follow_redirects=False)
        assert first.status_code == 302
        assert first.headers["location"] == "/"

        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["role"] == "owner"
        assert body["organizations"][0]["org_slug"] == "local-dev"

        second = await client.get("/api/v1/auth/dev-login?return_to=%2F", follow_redirects=False)
        assert second.status_code == 302

    async with db.session() as session:
        org = await session.scalar(select(Organization).where(Organization.slug == "local-dev"))
        assert org is not None

    async with db.session(TenantContext(org_id=org.id)) as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(User).where(User.org_id == org.id)
            )
        ) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(Membership).where(Membership.org_id == org.id)
            )
        ) == 1
        identity_count = await session.scalar(
            select(func.count())
            .select_from(Identity)
            .join(User, User.id == Identity.user_id)
            .where(User.org_id == org.id)
        )
        assert identity_count == 1


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://testserver",
        ) as client,
    ):
        yield client
