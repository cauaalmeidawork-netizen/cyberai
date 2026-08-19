"""Baseline security response headers.

Cheap, always-on hardening. The API returns JSON rather than HTML, so these
mostly matter for the documentation UI and for any browser that is tricked into
rendering a response, but they cost nothing and close a class of mistakes.

Transport security (HSTS) is only asserted in deployed environments, where TLS
is terminated at the edge.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BASE_HEADERS: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
    ("cross-origin-opener-policy", "same-origin"),
    ("permissions-policy", "geolocation=(), microphone=(), camera=()"),
)

_HSTS = ("strict-transport-security", "max-age=63072000; includeSubDomains")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        self.app = app
        self._headers = (*_BASE_HEADERS, _HSTS) if enable_hsts else _BASE_HEADERS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self._headers:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)
