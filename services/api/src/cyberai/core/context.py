"""Ambient request context.

Correlation data (request id, trace id, tenant, principal) must be reachable
from any layer without threading it through every function signature, and it
must never leak between concurrent requests. ``contextvars`` gives us both.

The tenant identifier lives here so that, from M1 onwards, the database layer
can bind it to the PostgreSQL session for Row Level Security without the
calling code having to remember to pass it around.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

_request_id: ContextVar[str | None] = ContextVar("cyberai_request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("cyberai_trace_id", default=None)
_org_id: ContextVar[str | None] = ContextVar("cyberai_org_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("cyberai_user_id", default=None)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Immutable snapshot of the ambient context of the current request."""

    request_id: str | None = None
    trace_id: str | None = None
    org_id: str | None = None
    user_id: str | None = None

    def as_log_fields(self) -> dict[str, str]:
        """Return the non-empty fields, ready to be merged into a log event."""
        fields = {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "org_id": self.org_id,
            "user_id": self.user_id,
        }
        return {key: value for key, value in fields.items() if value is not None}


@dataclass(slots=True)
class _ContextTokens:
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = field(default_factory=list)


def current_context() -> RequestContext:
    """Return the context bound to the current task."""
    return RequestContext(
        request_id=_request_id.get(),
        trace_id=_trace_id.get(),
        org_id=_org_id.get(),
        user_id=_user_id.get(),
    )


def current_request_id() -> str | None:
    return _request_id.get()


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_org_id() -> str | None:
    """Return the tenant bound to the current task, if any.

    Security note: this value is always derived from a verified identity on the
    server side. It is never read from a client-supplied header or body field.
    """
    return _org_id.get()


def current_user_id() -> str | None:
    return _user_id.get()


@contextmanager
def bind_context(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    org_id: str | None = None,
    user_id: str | None = None,
) -> Iterator[RequestContext]:
    """Bind context values for the duration of the block, then restore them."""
    state = _ContextTokens()
    for var, value in (
        (_request_id, request_id),
        (_trace_id, trace_id),
        (_org_id, org_id),
        (_user_id, user_id),
    ):
        if value is not None:
            state.tokens.append((var, var.set(value)))
    try:
        yield current_context()
    finally:
        for var, token in reversed(state.tokens):
            var.reset(token)
