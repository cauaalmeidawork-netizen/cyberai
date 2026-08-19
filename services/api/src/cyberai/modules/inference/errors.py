"""Inference failures.

Every failure carries ``can_failover``: whether the Model Gateway is allowed to
retry the same request on another model. A timeout or an unavailable provider
is worth retrying elsewhere; an unknown model or an invalid request is not, and
retrying it would just burn latency across every candidate.
"""

from __future__ import annotations

from typing import Any

from cyberai.core.errors import AppError


class InferenceError(AppError):
    """Base class for failures raised by the Inference Gateway."""

    code = "inference_failed"
    status_code = 502
    title = "Inference Failed"
    default_detail = "The model could not produce a response."
    can_failover: bool = True

    def __init__(
        self,
        detail: str | None = None,
        *,
        provider: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        super().__init__(detail, extra=extra)


class ProviderTimeoutError(InferenceError):
    code = "provider_timeout"
    status_code = 504
    title = "Inference Timeout"
    default_detail = "The model did not respond in time."
    can_failover = True


class ProviderUnavailableError(InferenceError):
    code = "provider_unavailable"
    status_code = 503
    title = "Provider Unavailable"
    default_detail = "The inference provider is currently unavailable."
    can_failover = True


class ProviderRateLimitedError(InferenceError):
    code = "provider_rate_limited"
    status_code = 503
    title = "Provider Rate Limited"
    default_detail = "The inference provider is rate limiting requests."
    can_failover = True


class ProviderResponseError(InferenceError):
    """The provider answered, but the response was unusable."""

    code = "provider_response_invalid"
    status_code = 502
    title = "Invalid Provider Response"
    default_detail = "The inference provider returned an unusable response."
    can_failover = True


class CircuitOpenError(InferenceError):
    """The breaker for this provider is open; the call was not attempted."""

    code = "provider_circuit_open"
    status_code = 503
    title = "Provider Circuit Open"
    default_detail = "The inference provider is temporarily disabled after repeated failures."
    can_failover = True


class ProviderNotRegisteredError(InferenceError):
    """Configuration error: the requested provider was never wired up."""

    code = "provider_not_registered"
    status_code = 500
    title = "Provider Not Registered"
    default_detail = "The requested inference provider is not available."
    can_failover = False


class UnsupportedModelError(InferenceError):
    """The provider does not serve the requested model."""

    code = "model_not_supported"
    status_code = 400
    title = "Model Not Supported"
    default_detail = "The requested model is not served by this provider."
    can_failover = False
