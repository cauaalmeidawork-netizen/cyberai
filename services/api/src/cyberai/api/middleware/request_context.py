"""Request correlation.

Assigns a request id and a trace id to every request and binds them to the
ambient context, so any log line, error document or downstream call can be tied
back to a single request without threading an argument through the codebase.

Written as pure ASGI rather than ``BaseHTTPMiddleware`` because the streaming
endpoints added in M2 need the response body to pass through untouched.

Client-supplied values are accepted (distributed tracing depends on it) but
validated first: an unvalidated header echoed into structured logs is a log
injection vector.
"""

from __future__ import annotations

import re
from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from cyberai.core.context import bind_context
from cyberai.core.ids import new_id, new_trace_id

REQUEST_ID_HEADER: Final = "x-request-id"
TRACEPARENT_HEADER: Final = "traceparent"

_MAX_REQUEST_ID_LENGTH: Final = 128
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
# W3C traceparent: version "-" trace-id "-" parent-id "-" flags
_TRACEPARENT = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<span_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$"
)
_INVALID_TRACE_ID: Final = "0" * 32


def _sanitize_request_id(raw: str | None) -> str:
    if raw and len(raw) <= _MAX_REQUEST_ID_LENGTH and _SAFE_REQUEST_ID.match(raw):
        return raw
    return new_id()


def _extract_trace_id(raw: str | None) -> str:
    if raw:
        match = _TRACEPARENT.match(raw.strip())
        if match and match.group("trace_id") != _INVALID_TRACE_ID:
            return match.group("trace_id")
    return new_trace_id()


class RequestContextMiddleware:
    """Binds request_id / trace_id for the lifetime of the request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = _sanitize_request_id(headers.get(REQUEST_ID_HEADER))
        trace_id = _extract_trace_id(headers.get(TRACEPARENT_HEADER))

        scope["request_id"] = request_id
        scope["trace_id"] = trace_id

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers.append("x-request-id", request_id)
            await send(message)

        with bind_context(request_id=request_id, trace_id=trace_id):
            await self.app(scope, receive, send_with_headers)
