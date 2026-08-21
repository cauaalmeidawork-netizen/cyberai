"""Request body size limiting."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Reject HTTP requests whose body exceeds the configured byte ceiling."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self._max_bytes:
            await _send_payload_too_large(send)
            return

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] != "http.request":
                return message
            body = message.get("body", b"")
            consumed += len(body)
            if consumed > self._max_bytes:
                return {"type": "http.disconnect"}
            return message

        await self.app(scope, limited_receive, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name.lower() != b"content-length":
            continue
        try:
            return int(value.decode("ascii"))
        except ValueError:
            return None
    return None


async def _send_payload_too_large(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/problem+json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": (
                b'{"type":"https://errors.cyberai.dev/request_too_large",'
                b'"title":"Payload Too Large","status":413,'
                b'"detail":"The request body is too large.",'
                b'"code":"request_too_large"}'
            ),
        }
    )
