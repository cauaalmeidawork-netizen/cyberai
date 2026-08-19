"""Structured access logging.

One event per request, carrying the correlation fields injected upstream.

Query strings are not logged: they routinely carry tokens and identifiers, and
a log pipeline is not an appropriate place for either. Health probe paths are
skipped so they do not drown out real traffic.
"""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from cyberai.core.logging import get_logger

logger = get_logger("cyberai.access")


class AccessLogMiddleware:
    """Emits one structured event per HTTP request."""

    def __init__(self, app: ASGIApp, *, silent_paths: tuple[str, ...] = ()) -> None:
        self.app = app
        self._silent_paths = frozenset(silent_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in self._silent_paths:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "http.request",
                method=scope.get("method"),
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
            )
