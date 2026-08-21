"""OIDC discovery and authorization URL helpers."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt


@dataclass(frozen=True, slots=True)
class OidcDiscovery:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


@dataclass(frozen=True, slots=True)
class PkceMaterial:
    verifier: str
    challenge: str


async def discover_oidc(issuer: str) -> OidcDiscovery:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration")
        response.raise_for_status()
    data = response.json()
    return OidcDiscovery(
        issuer=str(data["issuer"]),
        authorization_endpoint=str(data["authorization_endpoint"]),
        token_endpoint=str(data["token_endpoint"]),
        jwks_uri=str(data["jwks_uri"]),
    )


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)


def generate_pkce() -> PkceMaterial:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PkceMaterial(verifier=verifier, challenge=challenge)


def authorization_url(
    *,
    endpoint: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    nonce: str,
    pkce: PkceMaterial,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{endpoint}?{query}"


def validate_id_token(
    token: str,
    *,
    key: object,
    issuer: str,
    audience: str,
    nonce: str,
) -> dict[str, object]:
    payload = jwt.decode(
        token,
        key=key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=audience,
        options={"require": ["exp", "iss", "sub", "aud"]},
    )
    if payload.get("nonce") != nonce:
        raise jwt.InvalidTokenError("nonce mismatch")
    return dict(payload)
