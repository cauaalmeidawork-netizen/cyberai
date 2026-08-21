"""Authenticated request principal."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from cyberai.modules.auth.roles import Permission, Role


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: UUID
    active_org_id: UUID
    membership_id: UUID | None
    role: Role
    permissions: frozenset[Permission]
    request_id: str | None = None
    session_id: UUID | None = None
    csrf_token: str | None = None

    @property
    def id(self) -> UUID:
        return self.user_id

    @property
    def org_id(self) -> UUID:
        return self.active_org_id

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions
