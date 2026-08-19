"""Authentication and Principal Binding."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from cyberai.api.deps import DatabaseDep, SettingsDep
from cyberai.core.context import set_context
from cyberai.platform.db.models import User


async def get_current_user(
    request: Request,
    db: DatabaseDep,
    settings: SettingsDep,
) -> User:
    """Minimal M1 Auth: validate a JWT and bind tenant.

    Validates a cryptographically signed JWT, enforces expiration, extracts
    the user UUID from the 'sub' claim, and binds the ambient context.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        ) from None

    token = auth_header[len("Bearer ") :]
    try:
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValueError("Token missing 'sub' claim")
        user_id = uuid.UUID(user_id_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from None
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format or signature",
        ) from None

    async with db.session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id, User.is_active)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        ) from None

    # Bind the context variables so current_context() reads the correct tenant and user.
    set_context(user_id=str(user.id), org_id=str(user.org_id))

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
