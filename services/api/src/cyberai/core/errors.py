"""Application error taxonomy.

Every error the API returns is serialised as an RFC 9457 ``application/problem+json``
document. Two rules are non-negotiable:

* the ``detail`` of an error is written for the caller, never copied from an
  internal exception message;
* stack traces and driver messages are logged, never returned.

``AppError`` carries the HTTP status only as metadata. The core package does not
import a web framework; the API layer maps these objects onto responses.
"""

from __future__ import annotations

from typing import Any

PROBLEM_CONTENT_TYPE = "application/problem+json"
_PROBLEM_BASE_URI = "https://errors.cyberai.dev"


class AppError(Exception):
    """Base class for every expected, user-facing failure."""

    code: str = "internal_error"
    status_code: int = 500
    title: str = "Internal Server Error"
    default_detail: str = "An unexpected error occurred."

    def __init__(
        self,
        detail: str | None = None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.default_detail
        self.extra: dict[str, Any] = extra or {}
        super().__init__(self.detail)

    @property
    def type_uri(self) -> str:
        return f"{_PROBLEM_BASE_URI}/{self.code}"

    def to_problem(self, *, instance: str | None = None) -> dict[str, Any]:
        """Render this error as an RFC 9457 problem document."""
        problem: dict[str, Any] = {
            "type": self.type_uri,
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
            "code": self.code,
        }
        if instance is not None:
            problem["instance"] = instance
        problem.update(self.extra)
        return problem


# --- Client errors -----------------------------------------------------------


class ValidationFailedError(AppError):
    code = "validation_failed"
    status_code = 422
    title = "Validation Failed"
    default_detail = "The request payload is invalid."


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = 401
    title = "Unauthorized"
    default_detail = "Authentication is required."


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403
    title = "Forbidden"
    default_detail = "You do not have access to this resource."


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    title = "Not Found"
    default_detail = "The requested resource does not exist."


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    title = "Conflict"
    default_detail = "The request conflicts with the current state."


class RateLimitedError(AppError):
    code = "rate_limited"
    status_code = 429
    title = "Too Many Requests"
    default_detail = "Rate limit exceeded. Retry later."


class QuotaExceededError(AppError):
    code = "quota_exceeded"
    status_code = 429
    title = "Quota Exceeded"
    default_detail = "The organization quota for this resource has been exhausted."


# --- Server / upstream errors ------------------------------------------------


class InternalError(AppError):
    """Catch-all for unexpected failures. Never carries internal details."""

    code = "internal_error"
    status_code = 500
    title = "Internal Server Error"
    default_detail = "An unexpected error occurred."


class ServiceUnavailableError(AppError):
    code = "service_unavailable"
    status_code = 503
    title = "Service Unavailable"
    default_detail = "A dependency is currently unavailable."


class ConfigurationError(AppError):
    """Raised at startup when the environment is misconfigured."""

    code = "configuration_error"
    status_code = 500
    title = "Configuration Error"
    default_detail = "The service is misconfigured."
