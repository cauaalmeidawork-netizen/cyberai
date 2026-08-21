"""Organization membership and active organization switching."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from cyberai.api.auth import (
    CurrentPrincipalDep,
    require_csrf,
    session_cookie_options,
)
from cyberai.api.deps import DatabaseDep, SettingsDep
from cyberai.core.errors import ForbiddenError
from cyberai.modules.auth import SessionService
from cyberai.platform.db.models import Membership, Organization

router = APIRouter(tags=["organizations"], prefix="/organizations")

_CSRF_COOKIE_NAME = "cyberai_csrf"


class OrganizationOut(BaseModel):
    id: str
    slug: str
    display_name: str
    role: str
    active: bool


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(
    principal: CurrentPrincipalDep,
    db: DatabaseDep,
) -> list[OrganizationOut]:
    async with db.session() as session:
        result = await session.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(Membership.user_id == principal.user_id, Membership.status == "active")
            .order_by(Organization.display_name.asc(), Organization.id.asc())
        )
        return [
            OrganizationOut(
                id=str(organization.id),
                slug=organization.slug,
                display_name=organization.display_name,
                role=membership.role,
                active=organization.id == principal.active_org_id,
            )
            for membership, organization in result.all()
        ]


@router.post("/{org_id}/activate")
async def activate_organization(
    org_id: UUID,
    request: Request,
    principal: CurrentPrincipalDep,
    db: DatabaseDep,
    settings: SettingsDep,
) -> JSONResponse:
    await require_csrf(request=request, db=db, settings=settings)
    token = request.cookies.get(settings.auth.session_cookie_name)
    if token is None:
        raise ForbiddenError("The session is not available.")

    async with db.session() as session:
        membership = await session.scalar(
            select(Membership).where(
                Membership.user_id == principal.user_id,
                Membership.org_id == org_id,
                Membership.status == "active",
            )
        )
        if membership is None:
            raise ForbiddenError("You do not have access to this organization.")

    created = await SessionService(db).rotate_session(
        token=token,
        active_org_id=org_id,
        membership_id=membership.id,
        ttl=timedelta(seconds=settings.auth.session_ttl_seconds),
    )
    response = JSONResponse({"active_org_id": str(org_id)})
    response.set_cookie(value=created.token, **session_cookie_options(settings, created.expires_at))
    _set_csrf_cookie(response, created.csrf_token, settings)
    return response


def _set_csrf_cookie(response: JSONResponse, token: str, settings: SettingsDep) -> None:
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
