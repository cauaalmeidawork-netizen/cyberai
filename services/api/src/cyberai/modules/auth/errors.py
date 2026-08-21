"""Authentication and authorization errors."""

from __future__ import annotations

from cyberai.core.errors import ForbiddenError, UnauthorizedError


class AuthenticationRequiredError(UnauthorizedError):
    code = "authentication_required"
    default_detail = "Authentication is required."


class InvalidSessionError(UnauthorizedError):
    code = "invalid_session"
    default_detail = "The session is invalid or expired."


class PermissionDeniedError(ForbiddenError):
    code = "forbidden"
    default_detail = "You do not have permission to perform this action."


class CsrfFailedError(ForbiddenError):
    code = "csrf_failed"
    default_detail = "The request could not be verified."
