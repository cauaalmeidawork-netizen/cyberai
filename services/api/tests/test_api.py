"""HTTP-level tests for health endpoints and common middleware."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cyberai.main import create_app


@pytest.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    app: FastAPI = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app), base_url="http://testserver"
        ) as client,
    ):
        yield client


@pytest.mark.asyncio
async def test_liveness(app_client: AsyncClient) -> None:
    response = await app_client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "cyberai-api"
    assert "version" in body


@pytest.mark.asyncio
async def test_readiness_with_dependencies_down(app_client: AsyncClient) -> None:
    response = await app_client.get("/readyz")
    # PostgreSQL/Redis are not running in unit tests.
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    names = {d["name"] for d in body["dependencies"]}
    assert "postgresql" in names
    assert "redis" in names
    assert "inference:mock" in names


@pytest.mark.asyncio
async def test_meta_endpoint(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "cyberai-api"
    assert body["api_version"] == "v1"


@pytest.mark.asyncio
async def test_list_models(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/v1/models")
    assert response.status_code == 200
    body = response.json()
    keys = {model["key"] for model in body["data"]}
    assert "mock-analyst-1" in keys


@pytest.mark.asyncio
async def test_request_id_is_returned(app_client: AsyncClient) -> None:
    response = await app_client.get("/healthz", headers={"x-request-id": "test-123"})
    assert response.headers["x-request-id"] == "test-123"


@pytest.mark.asyncio
async def test_request_id_is_generated(app_client: AsyncClient) -> None:
    response = await app_client.get("/healthz")
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0


@pytest.mark.asyncio
async def test_security_headers(app_client: AsyncClient) -> None:
    response = await app_client.get("/healthz")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_validation_error_returns_problem_json(app_client: AsyncClient) -> None:
    response = await app_client.post("/not-a-route-that-exists")
    assert response.status_code == 404
    body: dict[str, Any] = response.json()
    assert body["type"].startswith("https://errors.cyberai.dev/")
    assert "request_id" in body


@pytest.mark.asyncio
async def test_cors_preflight(app_client: AsyncClient) -> None:
    response = await app_client.options(
        "/api/v1/meta",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"



