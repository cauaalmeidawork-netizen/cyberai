"""HTTP-level tests for health endpoints and common middleware."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cyberai.core.config import load_settings
from cyberai.main import create_app


@pytest.mark.asyncio
async def test_liveness(app_client: AsyncClient) -> None:
    response = await app_client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "nomercy-api"
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
    assert "schema" in names
    assert "model_gateway" in names


@pytest.mark.asyncio
async def test_meta_endpoint(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "nomercy-api"
    assert body["api_version"] == "v1"


@pytest.mark.asyncio
async def test_list_models(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/v1/models")
    assert response.status_code == 200
    body = response.json()
    # The public catalog never surfaces internal/test (mock) models, even when
    # they are the only configured providers.
    assert body["default_model"] == ""
    keys = {model["key"] for model in body["data"]}
    assert "mock-analyst-1" not in keys
    assert "mock-analyst-mini" not in keys
    for model in body["data"]:
        assert "Mock Analyst" not in model["display_name"]


@pytest.mark.asyncio
async def test_list_models_returns_configured_openai_compatible_default() -> None:
    settings = load_settings(
        openai_compatible={
            "enabled": True,
            "api_key": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": "qwen2.5:3b",
            "display_name": "Qwen 2.5 3B Local",
        },
        models={"default_model": "openai-compatible-chat", "fallback_models": []},
    )
    app = create_app(settings)
    async with _client(app) as client:
        response = await client.get("/api/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default_model"] == "openai-compatible-chat"
    assert body["data"][0]["key"] == "openai-compatible-chat"
    assert body["data"][0]["display_name"] == "Qwen 2.5 3B Local"


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


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://testserver",
        ) as client,
    ):
        yield client
