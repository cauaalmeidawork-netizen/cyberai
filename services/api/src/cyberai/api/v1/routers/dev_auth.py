"""Local-only development login.

This endpoint exists solely for the local environment so the product can be
run without an external OIDC provider. It provisions a deterministic local
organization/user membership and issues the same opaque session cookies used by
normal OIDC login.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from cyberai.api.auth import session_cookie_options
from cyberai.api.deps import DatabaseDep, SettingsDep
from cyberai.core.config import Environment
from cyberai.core.errors import ForbiddenError
from cyberai.modules.auth import SessionService
from cyberai.platform.db import TenantContext
from cyberai.platform.db.models import Membership, Organization, User

router = APIRouter(tags=["auth"], prefix="/auth")

_CSRF_COOKIE_NAME = "cyberai_csrf"
_LOCAL_ORG_SLUG = "local-dev"
_LOCAL_IDENTITY_ID = "local-dev"


@router.get("/dev-login")
async def dev_login(
    settings: SettingsDep,
    db: DatabaseDep,
    return_to: Annotated[str | None, Query(max_length=512)] = None,
) -> RedirectResponse:
    """Create/reuse a local developer account and issue a normal session."""
    if settings.environment is not Environment.LOCAL:
        raise ForbiddenError("Local development login is not available in this environment.")

    async with db.session() as session:
        organization = await session.scalar(
            select(Organization).where(Organization.slug == _LOCAL_ORG_SLUG)
        )
        if organization is None:
            organization = Organization(
                slug=_LOCAL_ORG_SLUG,
                display_name="CyberAI Local",
                identity_provider_id=_LOCAL_IDENTITY_ID,
            )
            session.add(organization)
            await session.flush()
        org_id = organization.id

    async with db.session(TenantContext(org_id=org_id)) as session:
        user = await session.scalar(
            select(User).where(
                User.org_id == org_id,
                User.identity_provider_id == _LOCAL_IDENTITY_ID,
            )
        )
        if user is None:
            user = User(
                org_id=org_id,
                identity_provider_id=_LOCAL_IDENTITY_ID,
                email="local@cyberai.dev",
                display_name="Local Developer",
                role="owner",
                is_active=True,
            )
            session.add(user)
            await session.flush()

        membership = await session.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.org_id == org_id,
            )
        )
        if membership is None:
            membership = Membership(
                user_id=user.id,
                org_id=org_id,
                role="owner",
                status="active",
            )
            session.add(membership)
            await session.flush()
        elif membership.status != "active" or membership.role != "owner":
            membership.status = "active"
            membership.role = "owner"
            session.add(membership)

        user_id = user.id
        membership_id = membership.id

    created = await SessionService(db).create_session(
        user_id=user_id,
        active_org_id=org_id,
        membership_id=membership_id,
        ttl=timedelta(seconds=settings.auth.session_ttl_seconds),
    )

    redirect_target = _safe_return_to(return_to) or "/"
    if redirect_target.startswith("/") and settings.app.cors_origins:
        redirect_target = f"{str(settings.app.cors_origins[0]).rstrip('/')}{redirect_target}"

    response = RedirectResponse(redirect_target, status_code=302)
    response.set_cookie(value=created.token, **session_cookie_options(settings, created.expires_at))
    _set_csrf_cookie(response, created.csrf_token, settings)
    return response


def _safe_return_to(raw: str | None) -> str | None:
    if raw is None or not raw.startswith("/") or raw.startswith("//"):
        return None
    return raw


def _set_csrf_cookie(response: RedirectResponse, token: str, settings: SettingsDep) -> None:
    secure = settings.auth.session_secure_cookie
    if secure is None:
        secure = settings.environment.is_deployed
    response.set_cookie(
        key=_CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=secure,
        samesite=settings.auth.session_samesite,
        path="/",
    )
