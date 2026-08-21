"""M11 authentication, memberships and RBAC tests."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from cyberai.core.config import Environment, load_settings
from cyberai.modules.auth import Permission, Role, SessionService, permissions_for_role
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.models import (
    AuthSession,
    Membership,
    Organization,
    Project,
    User,
)


def test_roles_resolve_to_capabilities() -> None:
    owner_permissions = permissions_for_role(Role.OWNER)
    viewer_permissions = permissions_for_role(Role.VIEWER)

    assert Permission.ORGANIZATION_MANAGE in owner_permissions
    assert Permission.PROJECT_WRITE in owner_permissions
    assert Permission.PROJECT_READ in viewer_permissions
    assert Permission.PROJECT_WRITE not in viewer_permissions


def test_production_rejects_legacy_bearer_auth() -> None:
    with pytest.raises(ValueError, match="legacy bearer authentication"):
        load_settings(
            environment=Environment.PRODUCTION,
            database={"url": "postgresql+asyncpg://cyberai:secure-password@db:5432/cyberai"},
            app={
                "cors_origins": ["https://app.cyberai.dev"],
                "trusted_hosts": ["api.cyberai.dev"],
                "expose_docs": False,
            },
            logging={"format": "json"},
            auth={
                "jwt_secret": "prod-jwt-secret-with-enough-entropy",
                "legacy_bearer_enabled": True,
                "oidc_issuer": "https://idp.example.com",
                "oidc_client_id": "cyberai",
                "oidc_client_secret": "super-secret",
                "session_secret": "session-secret-with-enough-entropy",
                "csrf_secret": "csrf-secret-with-enough-entropy",
            },
            models={"default_model": "openai-compatible-chat", "fallback_models": []},
            openai_compatible={"enabled": True, "api_key": "test-key"},
        )


@pytest.mark.asyncio
async def test_session_service_stores_only_hash_and_rotates(db: Database) -> None:
    org, user, membership = await _create_member(db, role="admin")
    service = SessionService(db)

    created = await service.create_session(
        user_id=user.id,
        active_org_id=org.id,
        membership_id=membership.id,
        ttl=timedelta(hours=1),
    )

    token_hash = hashlib.sha256(created.token.encode("utf-8")).hexdigest()
    async with db.session() as session:
        row = await session.scalar(select(AuthSession).where(AuthSession.id == created.session_id))
        assert row is not None
        assert row.session_token_hash == token_hash
        assert created.token not in row.session_token_hash

    rotated = await service.rotate_session(
        token=created.token,
        active_org_id=org.id,
        membership_id=membership.id,
        ttl=timedelta(hours=1),
    )

    assert await service.authenticate(created.token) is None
    principal = await service.authenticate(rotated.token)
    assert principal is not None
    assert principal.user_id == user.id
    assert principal.active_org_id == org.id
    assert Permission.PROJECT_WRITE in principal.permissions


@pytest.mark.asyncio
async def test_current_principal_uses_active_membership_not_user_org(
    app_client: AsyncClient,
    db: Database,
) -> None:
    home_org, user, _home_membership = await _create_member(db, role="viewer")
    active_org = Organization(
        slug=f"active-{uuid4().hex[:8]}",
        display_name="Active Org",
    )
    async with db.session() as session:
        session.add(active_org)
        await session.flush()
        active_membership = Membership(
            user_id=user.id,
            org_id=active_org.id,
            role="admin",
            status="active",
        )
        session.add(active_membership)
        await session.flush()
    service = SessionService(db)
    created = await service.create_session(
        user_id=user.id,
        active_org_id=active_org.id,
        membership_id=active_membership.id,
        ttl=timedelta(hours=1),
    )

    async with db.session(TenantContext(org_id=home_org.id)) as session:
        session.add(Project(org_id=home_org.id, name="Home Project", description=None))
    async with db.session(TenantContext(org_id=active_org.id)) as session:
        session.add(Project(org_id=active_org.id, name="Active Project", description=None))

    app_client.cookies.set("cyberai_session", created.token)
    response = await app_client.get("/api/v1/projects")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Active Project"]

    await _cleanup_org(db, active_org.id)
    await _cleanup_org(db, home_org.id)


@pytest.mark.asyncio
async def test_viewer_membership_cannot_create_project(
    app_client: AsyncClient, db: Database
) -> None:
    org, user, membership = await _create_member(db, role="viewer")
    service = SessionService(db)
    created = await service.create_session(
        user_id=user.id,
        active_org_id=org.id,
        membership_id=membership.id,
        ttl=timedelta(hours=1),
    )

    app_client.cookies.set("cyberai_session", created.token)
    response = await app_client.post(
        "/api/v1/projects",
        json={"name": "Denied", "description": None},
        headers={"X-CSRF-Token": created.csrf_token},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"

    await _cleanup_org(db, org.id)


async def _create_member(db: Database, *, role: str) -> tuple[Organization, User, Membership]:
    suffix = uuid4().hex[:8]
    org = Organization(slug=f"auth-{suffix}", display_name="Auth Org")
    user = User(
        org_id=org.id,
        identity_provider_id=f"test|{suffix}",
        email=f"auth-{suffix}@cyberai.dev",
        display_name="Auth User",
    )
    async with db.session() as session:
        session.add(org)
        await session.flush()
        user.org_id = org.id
        session.add(user)
        await session.flush()
        membership = Membership(
            user_id=user.id,
            org_id=org.id,
            role=role,
            status="active",
        )
        session.add(membership)
        await session.flush()
    return org, user, membership


async def _cleanup_org(db: Database, org_id: UUID) -> None:
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM auth_sessions WHERE active_org_id = :id"),
            {"id": org_id},
        )
        await session.execute(text("DELETE FROM memberships WHERE org_id = :id"), {"id": org_id})
        await session.execute(text("DELETE FROM projects WHERE org_id = :id"), {"id": org_id})
        await session.execute(text("DELETE FROM users WHERE org_id = :id"), {"id": org_id})
        await session.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_id})
