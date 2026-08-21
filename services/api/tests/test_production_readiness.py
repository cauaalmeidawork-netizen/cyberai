"""Production readiness tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.responses import StreamingResponse

from cyberai.api.middleware.response_start_timeout import ResponseStartTimeoutMiddleware
from cyberai.core.config import Settings
from cyberai.main import create_app
from cyberai.platform.db.migrations import schema_revision_health


def test_schema_revision_health_detects_current_head() -> None:
    status = schema_revision_health(applied_revision="head-1", expected_head="head-1")

    assert status.healthy is True
    assert status.detail == "schema_current"


def test_schema_revision_health_fails_closed_on_divergence() -> None:
    status = schema_revision_health(applied_revision="old", expected_head="head")

    assert status.healthy is False
    assert status.detail == "schema_mismatch"


@pytest.mark.asyncio
async def test_health_live_aliases_return_build_metadata() -> None:
    settings = Settings(
        build={"commit": "abc123", "time": "2026-08-20T00:00:00Z"},
    )
    app = create_app(settings)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://testserver",
        ) as client,
    ):
        live = await client.get("/health/live")
        legacy = await client.get("/healthz")

    assert live.status_code == 200
    assert legacy.status_code == 200
    assert live.json()["build_commit"] == "abc123"


@pytest.mark.asyncio
async def test_docs_can_be_disabled_by_configuration() -> None:
    settings = Settings(app={"expose_docs": False})
    app = create_app(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        docs = await client.get("/docs")
        openapi = await client.get("/openapi.json")

    assert docs.status_code == 404
    assert openapi.status_code == 404


@pytest.mark.asyncio
async def test_request_body_limit_rejects_large_payload_before_handler() -> None:
    settings = Settings(app={"max_request_body_bytes": 8})
    app = create_app(settings)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://testserver",
        ) as client,
    ):
        response = await client.post(
            "/api/v1/conversations",
            content=b"0123456789",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413


@pytest.mark.asyncio
async def test_trusted_host_rejects_unconfigured_host() -> None:
    settings = Settings(app={"trusted_hosts": ["allowed.test"]})
    app = create_app(settings)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://bad.test",
        ) as client,
    ):
        response = await client.get("/health/live")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_response_start_timeout_does_not_cancel_started_stream() -> None:
    app = FastAPI()
    app.add_middleware(ResponseStartTimeoutMiddleware, timeout_seconds=0.01)

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def body() -> AsyncIterator[bytes]:
            yield b"first"

            await asyncio.sleep(0.03)
            yield b"second"

        return StreamingResponse(body())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/stream")

    assert response.status_code == 200
    assert response.content == b"firstsecond"


@pytest.mark.asyncio
async def test_response_start_timeout_rejects_handler_that_never_starts_response() -> None:
    app = FastAPI()
    app.add_middleware(ResponseStartTimeoutMiddleware, timeout_seconds=0.01)

    @app.get("/slow")
    async def slow() -> dict[str, str]:
        await asyncio.sleep(1.0)
        return {"status": "late"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/slow")

    assert response.status_code == 503
    assert response.json()["code"] == "request_timeout"
