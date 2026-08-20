"""Typed policy errors."""

from __future__ import annotations

from cyberai.core.errors import ForbiddenError, ServiceUnavailableError, ValidationFailedError


class PolicyDeniedError(ForbiddenError):
    code = "policy_denied"
    title = "Policy Denied"
    default_detail = "The request was blocked by security policy."


class UnsafeInputError(ValidationFailedError):
    code = "unsafe_input"
    title = "Unsafe Input"
    default_detail = "The request could not be accepted."


class UnsafeOutputError(PolicyDeniedError):
    code = "unsafe_output"
    title = "Unsafe Output"
    default_detail = "The response was blocked by security policy."


class PromptInjectionDetectedError(PolicyDeniedError):
    code = "prompt_injection_detected"
    title = "Prompt Injection Detected"
    default_detail = "The request was blocked by security policy."


class SecurityControlUnavailableError(ServiceUnavailableError):
    code = "security_control_unavailable"
    title = "Security Control Unavailable"
    default_detail = "A security control is unavailable."
