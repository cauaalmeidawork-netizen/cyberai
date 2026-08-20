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
from cyberai.observability.metrics import MetricsRecorder
from cyberai.observability.tracing import record_exception, start_span

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
        error_type: str | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            with start_span(
                "http.request",
                {
                    "http.request.method": str(scope.get("method")),
                    "url.path": path,
                },
            ) as span:
                try:
                    await self.app(scope, receive, send_wrapper)
                except Exception as exc:
                    error_type = type(exc).__name__
                    record_exception(span, exc, attributes={"error.type": error_type})
                    raise
                finally:
                    span.set_attribute("http.response.status_code", status_code)
        finally:
            duration_seconds = time.perf_counter() - started
            duration_ms = duration_seconds * 1000
            services = scope.get("app")
            metrics = _metrics_from_app(services)
            if metrics is not None:
                labels = {
                    "method": str(scope.get("method")),
                    "route": path,
                    "status": str(status_code),
                    "status_family": f"{status_code // 100}xx",
                }
                metrics.counter("http_requests_total", labels=labels).add()
                metrics.histogram("http_request_duration_seconds", labels=labels).record(
                    duration_seconds
                )
            logger.info(
                "http.request",
                method=scope.get("method"),
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 2),
                error_type=error_type,
            )


def _metrics_from_app(app: object) -> MetricsRecorder | None:
    state = getattr(app, "state", None)
    services = getattr(state, "services", None)
    return getattr(services, "metrics", None)
