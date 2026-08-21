"""Authentication, session and authorization dependencies."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal, TypedDict

import jwt
from fastapi import Depends, Request
from sqlalchemy import select

from cyberai.api.deps import DatabaseDep, SettingsDep
from cyberai.core.config import Environment, Settings
from cyberai.core.context import set_context
from cyberai.modules.auth import AuthenticatedPrincipal, Permission, Role, SessionService
from cyberai.modules.auth.errors import (
    AuthenticationRequiredError,
    CsrfFailedError,
    InvalidSessionError,
    PermissionDeniedError,
)
from cyberai.modules.auth.roles import parse_role, permissions_for_role
from cyberai.platform.db.models import Membership, User


async def get_current_principal(
    request: Request,
    db: DatabaseDep,
    settings: SettingsDep,
) -> AuthenticatedPrincipal:
    """Authenticate a session cookie or local/CI legacy bearer token."""
    session_token = request.cookies.get(settings.auth.session_cookie_name)
    if session_token:
        principal = await SessionService(db).authenticate(session_token)
        if principal is None:
            raise InvalidSessionError()
        principal = _with_request_id(principal, request)
        set_context(user_id=str(principal.user_id), org_id=str(principal.active_org_id))
        return principal

    if (
        settings.environment in {Environment.LOCAL, Environment.CI}
        and settings.auth.legacy_bearer_enabled
    ):
        principal = await _legacy_bearer_principal(request, db, settings)
        principal = _with_request_id(principal, request)
        set_context(user_id=str(principal.user_id), org_id=str(principal.active_org_id))
        return principal

    raise AuthenticationRequiredError()


async def _legacy_bearer_principal(
    request: Request,
    db: DatabaseDep,
    settings: SettingsDep,
) -> AuthenticatedPrincipal:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthenticationRequiredError("Missing or invalid authentication.")

    token = auth_header[len("Bearer ") :]
    try:
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        user_id = uuid.UUID(str(payload["sub"]))
    except jwt.ExpiredSignatureError:
        raise InvalidSessionError("Token expired.") from None
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise InvalidSessionError("Invalid token.") from None

    async with db.session() as session:
        user = await session.scalar(select(User).where(User.id == user_id, User.is_active))
        if user is None:
            raise InvalidSessionError("User not found or inactive.")
        membership = await session.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.org_id == user.org_id,
                Membership.status == "active",
            )
        )

    if membership is None:
        role = parse_role(user.role)
        return AuthenticatedPrincipal(
            user_id=user.id,
            active_org_id=user.org_id,
            membership_id=None,
            role=role,
            permissions=permissions_for_role(role),
        )

    role = parse_role(membership.role)
    return AuthenticatedPrincipal(
        user_id=user.id,
        active_org_id=membership.org_id,
        membership_id=membership.id,
        role=role,
        permissions=permissions_for_role(role),
    )


def _with_request_id(principal: AuthenticatedPrincipal, request: Request) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=principal.user_id,
        active_org_id=principal.active_org_id,
        membership_id=principal.membership_id,
        role=principal.role,
        permissions=principal.permissions,
        request_id=request.scope.get("request_id"),
        session_id=principal.session_id,
        csrf_token=principal.csrf_token,
    )


def require_permission(principal: AuthenticatedPrincipal, permission: Permission) -> None:
    if not principal.has_permission(permission):
        raise PermissionDeniedError()


async def require_csrf(
    *,
    request: Request,
    db: DatabaseDep,
    settings: SettingsDep,
) -> None:
    session_token = request.cookies.get(settings.auth.session_cookie_name)
    if session_token is None:
        return
    csrf_token = request.headers.get(settings.auth.csrf_header_name)
    if csrf_token is None:
        raise CsrfFailedError()
    if not await SessionService(db).verify_csrf(token=session_token, csrf_token=csrf_token):
        raise CsrfFailedError()


class SessionCookieOptions(TypedDict):
    key: str
    httponly: bool
    secure: bool
    samesite: Literal["lax", "strict", "none"]
    max_age: int
    path: str


def session_cookie_options(settings: Settings, expires_at: datetime) -> SessionCookieOptions:
    secure = settings.auth.session_secure_cookie
    if secure is None:
        secure = settings.environment.is_deployed
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    return {
        "key": settings.auth.session_cookie_name,
        "httponly": True,
        "secure": secure,
        "samesite": settings.auth.session_samesite,
        "max_age": max_age,
        "path": "/",
    }


CurrentPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]
CurrentUserDep = CurrentPrincipalDep

__all__ = [
    "CurrentPrincipalDep",
    "CurrentUserDep",
    "Permission",
    "Role",
    "require_csrf",
    "require_permission",
    "session_cookie_options",
]
