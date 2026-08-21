"""Authentication module public API."""

from cyberai.modules.auth.oidc import (
    PkceMaterial,
    authorization_url,
    discover_oidc,
    generate_nonce,
    generate_pkce,
    generate_state,
    validate_id_token,
)
from cyberai.modules.auth.principal import AuthenticatedPrincipal
from cyberai.modules.auth.roles import Permission, Role, permissions_for_role
from cyberai.modules.auth.sessions import CreatedSession, SessionService

__all__ = [
    "AuthenticatedPrincipal",
    "CreatedSession",
    "Permission",
    "PkceMaterial",
    "Role",
    "SessionService",
    "authorization_url",
    "discover_oidc",
    "generate_nonce",
    "generate_pkce",
    "generate_state",
    "permissions_for_role",
    "validate_id_token",
]
