"""HTTP timeout before response start.

This protects ordinary request handlers from hanging before they emit a
response, without imposing a global wall-clock timeout on legitimate streaming
responses after headers have been sent. Provider and stream timeouts remain
owned by the inference boundary.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ResponseStartTimeoutMiddleware:
    def __init__(self, app: ASGIApp, *, timeout_seconds: float) -> None:
        self.app = app
        self._timeout_seconds = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = asyncio.Event()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_started.set()
            await send(message)

        async def run_app() -> None:
            await self.app(scope, receive, send_wrapper)

        task: asyncio.Task[None] = asyncio.create_task(run_app())
        timeout_task = asyncio.create_task(response_started.wait())
        done, _pending = await asyncio.wait(
            {task, timeout_task},
            timeout=self._timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if task in done:
            timeout_task.cancel()
            await task
            return
        if timeout_task in done:
            await task
            return

        if response_started.is_set():
            await task
            return

        task.cancel()
        timeout_task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [(b"content-type", b"application/problem+json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": (
                    b'{"type":"https://errors.cyberai.dev/request_timeout",'
                    b'"title":"Service Unavailable","status":503,'
                    b'"detail":"The request timed out before a response started.",'
                    b'"code":"request_timeout"}'
                ),
            }
        )
