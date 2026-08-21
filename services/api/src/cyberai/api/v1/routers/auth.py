"""OIDC login, session and current-principal endpoints."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import jwt
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select

from cyberai.api.auth import (
    CurrentPrincipalDep,
    require_csrf,
    session_cookie_options,
)
from cyberai.api.deps import DatabaseDep, SettingsDep
from cyberai.core.errors import ForbiddenError, ServiceUnavailableError
from cyberai.modules.auth import (
    SessionService,
    authorization_url,
    discover_oidc,
    generate_nonce,
    generate_pkce,
    generate_state,
    validate_id_token,
)
from cyberai.platform.db.models import Identity, Membership, OidcLoginState, Organization

router = APIRouter(tags=["auth"], prefix="/auth")

_CSRF_COOKIE_NAME = "cyberai_csrf"


class OrganizationMembershipOut(BaseModel):
    id: str
    org_id: str
    org_slug: str
    org_display_name: str
    role: str
    status: str


class MeOut(BaseModel):
    user_id: str
    active_org_id: str
    membership_id: str | None
    role: str
    permissions: list[str]
    organizations: list[OrganizationMembershipOut]


@router.get("/login")
async def login(
    settings: SettingsDep,
    db: DatabaseDep,
    return_to: Annotated[str | None, Query(max_length=512)] = None,
) -> RedirectResponse:
    if not settings.auth.oidc_enabled:
        raise ServiceUnavailableError("OIDC login is not configured.")
    if not settings.auth.oidc_issuer or not settings.auth.oidc_client_id:
        raise ServiceUnavailableError("OIDC login is not configured.")
    redirect_uri = settings.auth.oidc_redirect_uri
    if redirect_uri is None:
        raise ServiceUnavailableError("OIDC redirect URI is not configured.")

    discovery = await discover_oidc(settings.auth.oidc_issuer)
    state = generate_state()
    nonce = generate_nonce()
    pkce = generate_pkce()
    async with db.session() as session:
        session.add(
            OidcLoginState(
                state_hash=_hash_token(state),
                nonce=nonce,
                pkce_verifier=pkce.verifier,
                redirect_uri=redirect_uri,
                return_to=_safe_return_to(return_to),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
    url = authorization_url(
        endpoint=discovery.authorization_endpoint,
        client_id=settings.auth.oidc_client_id,
        redirect_uri=redirect_uri,
        scope=settings.auth.oidc_scope,
        state=state,
        nonce=nonce,
        pkce=pkce,
    )
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def callback(
    settings: SettingsDep,
    db: DatabaseDep,
    state: str,
    code: str,
) -> RedirectResponse:
    if not settings.auth.oidc_enabled:
        raise ServiceUnavailableError("OIDC login is not configured.")
    if (
        not settings.auth.oidc_issuer
        or not settings.auth.oidc_client_id
        or not settings.auth.oidc_client_secret
    ):
        raise ServiceUnavailableError("OIDC login is not configured.")

    now = datetime.now(UTC)
    async with db.session() as session:
        login_state = await session.scalar(
            select(OidcLoginState).where(
                OidcLoginState.state_hash == _hash_token(state),
                OidcLoginState.consumed_at.is_(None),
                OidcLoginState.expires_at > now,
            )
        )
        if login_state is None:
            raise ForbiddenError("The login attempt could not be verified.")
        login_state.consumed_at = now
        session.add(login_state)

    discovery = await discover_oidc(settings.auth.oidc_issuer)
    token_data = await _exchange_code(
        token_endpoint=discovery.token_endpoint,
        client_id=settings.auth.oidc_client_id,
        client_secret=settings.auth.oidc_client_secret.get_secret_value(),
        code=code,
        redirect_uri=login_state.redirect_uri,
        pkce_verifier=login_state.pkce_verifier,
    )
    id_token = token_data.get("id_token")
    if not isinstance(id_token, str):
        raise ForbiddenError("The identity provider did not return a valid identity token.")

    signing_key = jwt.PyJWKClient(discovery.jwks_uri).get_signing_key_from_jwt(id_token).key
    claims = validate_id_token(
        id_token,
        key=signing_key,
        issuer=discovery.issuer,
        audience=settings.auth.oidc_client_id,
        nonce=login_state.nonce,
    )
    subject = str(claims["sub"])

    async with db.session() as session:
        identity = await session.scalar(
            select(Identity).where(Identity.issuer == discovery.issuer, Identity.subject == subject)
        )
        if identity is None:
            if not settings.auth.oidc_auto_provision_enabled:
                raise ForbiddenError("This identity is not authorized for CyberAI.")
            raise ForbiddenError("OIDC auto-provisioning is not available in this deployment.")
        membership = await session.scalar(
            select(Membership)
            .where(Membership.user_id == identity.user_id, Membership.status == "active")
            .order_by(Membership.created_at.asc(), Membership.id.asc())
        )
        if membership is None:
            raise ForbiddenError("This identity has no active organization membership.")

    created = await SessionService(db).create_session(
        user_id=identity.user_id,
        active_org_id=membership.org_id,
        membership_id=membership.id,
        ttl=timedelta(seconds=settings.auth.session_ttl_seconds),
    )
    response = RedirectResponse(login_state.return_to or "/", status_code=302)
    response.set_cookie(value=created.token, **session_cookie_options(settings, created.expires_at))
    _set_csrf_cookie(response, created.csrf_token, settings)
    return response


@router.get("/me", response_model=MeOut)
async def me(principal: CurrentPrincipalDep, db: DatabaseDep) -> MeOut:
    memberships = await _memberships_for_user(db, principal.user_id)
    return MeOut(
        user_id=str(principal.user_id),
        active_org_id=str(principal.active_org_id),
        membership_id=str(principal.membership_id) if principal.membership_id else None,
        role=principal.role.value,
        permissions=sorted(permission.value for permission in principal.permissions),
        organizations=memberships,
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    principal: CurrentPrincipalDep,
    db: DatabaseDep,
    settings: SettingsDep,
) -> Response:
    _ = principal
    await require_csrf(request=request, db=db, settings=settings)
    token = request.cookies.get(settings.auth.session_cookie_name)
    if token is not None:
        await SessionService(db).revoke(token)
    response = Response(status_code=204)
    response.delete_cookie(settings.auth.session_cookie_name, path="/")
    response.delete_cookie(_CSRF_COOKIE_NAME, path="/")
    return response


async def _memberships_for_user(
    db: DatabaseDep, user_id: object
) -> list[OrganizationMembershipOut]:
    async with db.session() as session:
        result = await session.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(Membership.user_id == user_id, Membership.status == "active")
            .order_by(Organization.display_name.asc(), Organization.id.asc())
        )
        return [
            OrganizationMembershipOut(
                id=str(membership.id),
                org_id=str(organization.id),
                org_slug=organization.slug,
                org_display_name=organization.display_name,
                role=membership.role,
                status=membership.status,
            )
            for membership, organization in result.all()
        ]


async def _exchange_code(
    *,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    pkce_verifier: str,
) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": pkce_verifier,
            },
        )
        response.raise_for_status()
    return dict(response.json())


def _safe_return_to(raw: str | None) -> str | None:
    if raw is None or not raw.startswith("/"):
        return None
    if raw.startswith("//"):
        return None
    return raw


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
