"""Shared Pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import jwt
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from cyberai.core.config import DatabaseSettings, Settings
from cyberai.main import create_app
from cyberai.platform.db import Database
from cyberai.platform.db.engine import Database as DatabaseEngine
from cyberai.platform.db.models import Organization, Project, User


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    db_settings = DatabaseSettings()
    database = DatabaseEngine(db_settings)
    yield database
    await database.dispose()


@pytest.fixture
async def test_org(db: Database) -> AsyncIterator[Organization]:
    suffix = uuid4().hex[:8]
    org = Organization(slug=f"test-org-{suffix}", display_name="Test Org")
    async with db.session() as session:
        session.add(org)
        await session.flush()
    yield org
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM organizations WHERE id = :id"),
            {"id": org.id},
        )


@pytest.fixture
async def test_user(db: Database, test_org: Organization) -> AsyncIterator[User]:
    suffix = uuid4().hex[:8]
    user = User(
        org_id=test_org.id,
        identity_provider_id=f"test-idp|{suffix}",
        email=f"test-{suffix}@cyberai.dev",
        display_name="Test User",
    )
    async with db.session() as session:
        session.add(user)
        await session.flush()
    yield user
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": user.id},
        )


@pytest.fixture
async def test_project(db: Database, test_org: Organization) -> AsyncIterator[Project]:
    suffix = uuid4().hex[:8]
    project = Project(
        org_id=test_org.id,
        name=f"Test Project {suffix}",
        description="A test project",
    )
    async with db.session() as session:
        session.add(project)
        await session.flush()
    yield project
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM projects WHERE id = :id"),
            {"id": project.id},
        )


@pytest.fixture
def test_user_token(test_user: User, settings: Settings) -> str:
    payload = {
        "sub": str(test_user.id),
        "exp": int(datetime.now(UTC).timestamp()) + 3600,
    }
    return jwt.encode(payload, settings.auth.jwt_secret, algorithm="HS256")


@pytest.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    app: FastAPI = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app), base_url="http://testserver"
        ) as client,
    ):
        yield client
