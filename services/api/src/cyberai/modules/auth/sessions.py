"""Opaque server-managed sessions."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from cyberai.modules.auth.principal import AuthenticatedPrincipal
from cyberai.modules.auth.roles import parse_role, permissions_for_role
from cyberai.platform.db import Database
from cyberai.platform.db.models import AuthSession, Membership, User
from cyberai.platform.db.tenant import TenantContext, apply_tenant_context


@dataclass(frozen=True, slots=True)
class CreatedSession:
    session_id: UUID
    token: str
    csrf_token: str
    expires_at: datetime


class SessionService:
    """Create, rotate, revoke and authenticate opaque session tokens."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_session(
        self,
        *,
        user_id: UUID,
        active_org_id: UUID,
        membership_id: UUID,
        ttl: timedelta,
    ) -> CreatedSession:
        token = _new_token()
        csrf_token = _new_token()
        expires_at = datetime.now(UTC) + ttl
        row = AuthSession(
            user_id=user_id,
            active_org_id=active_org_id,
            membership_id=membership_id,
            session_token_hash=_hash_token(token),
            csrf_token_hash=_hash_token(csrf_token),
            expires_at=expires_at,
        )
        async with self._db.session() as session:
            session.add(row)
            await session.flush()
        return CreatedSession(
            session_id=row.id,
            token=token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

    async def authenticate(self, token: str) -> AuthenticatedPrincipal | None:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            row = await session.scalar(
                select(AuthSession).where(
                    AuthSession.session_token_hash == _hash_token(token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
            )
            if row is None:
                return None

            # auth_sessions is intentionally global so the opaque token can be
            # resolved before a tenant is known. Once the session reveals the
            # active organization, bind that tenant before reading users (RLS).
            await apply_tenant_context(session, TenantContext(org_id=row.active_org_id))

            membership = await session.scalar(
                select(Membership).where(
                    Membership.id == row.membership_id,
                    Membership.user_id == row.user_id,
                    Membership.org_id == row.active_org_id,
                    Membership.status == "active",
                )
            )
            user = await session.scalar(select(User).where(User.id == row.user_id, User.is_active))
            if membership is None or user is None:
                return None
            role = parse_role(membership.role)
            return AuthenticatedPrincipal(
                user_id=row.user_id,
                active_org_id=row.active_org_id,
                membership_id=row.membership_id,
                role=role,
                permissions=permissions_for_role(role),
                session_id=row.id,
            )

    async def verify_csrf(self, *, token: str, csrf_token: str) -> bool:
        async with self._db.session() as session:
            row = await session.scalar(
                select(AuthSession).where(
                    AuthSession.session_token_hash == _hash_token(token),
                    AuthSession.revoked_at.is_(None),
                )
            )
            return row is not None and row.csrf_token_hash == _hash_token(csrf_token)

    async def rotate_session(
        self,
        *,
        token: str,
        active_org_id: UUID,
        membership_id: UUID,
        ttl: timedelta,
    ) -> CreatedSession:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            row = await session.scalar(
                select(AuthSession).where(
                    AuthSession.session_token_hash == _hash_token(token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
            )
            if row is None:
                raise ValueError("session is invalid")
            row.revoked_at = now
            session.add(row)
            new_token = _new_token()
            new_csrf = _new_token()
            expires_at = now + ttl
            replacement = AuthSession(
                user_id=row.user_id,
                active_org_id=active_org_id,
                membership_id=membership_id,
                session_token_hash=_hash_token(new_token),
                csrf_token_hash=_hash_token(new_csrf),
                expires_at=expires_at,
                rotated_from_session_id=row.id,
            )
            session.add(replacement)
            await session.flush()
        return CreatedSession(
            session_id=replacement.id,
            token=new_token,
            csrf_token=new_csrf,
            expires_at=expires_at,
        )

    async def revoke(self, token: str) -> None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(AuthSession).where(
                    AuthSession.session_token_hash == _hash_token(token),
                    AuthSession.revoked_at.is_(None),
                )
            )
            if row is not None:
                row.revoked_at = datetime.now(UTC)
                session.add(row)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
