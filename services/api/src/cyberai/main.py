"""Application entry point.

``create_app`` is a factory rather than a module-level singleton so tests can
build an application with a different configuration and a different object
graph without touching global state.

Run it with::

    uvicorn cyberai.main:create_app --factory
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from cyberai.api.errors import register_exception_handlers
from cyberai.api.health import router as health_router
from cyberai.api.metrics import router as metrics_router
from cyberai.api.middleware import (
    AccessLogMiddleware,
    RequestBodyLimitMiddleware,
    RequestContextMiddleware,
    ResponseStartTimeoutMiddleware,
    SecurityHeadersMiddleware,
)
from cyberai.api.v1 import v1_router
from cyberai.container import Services, build_services, shutdown_services
from cyberai.core.config import Settings, get_settings
from cyberai.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

DESCRIPTION = """
CYBER AI platform API.

A modular monolith with explicit boundaries: the HTTP layer only validates and
delegates, model selection lives behind the Model Gateway, and reaching a model
runtime lives behind the Inference Gateway.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application."""
    settings = settings or get_settings()
    configure_logging(
        settings.logging,
        service=settings.app.name,
        environment=settings.environment.value,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services: Services = build_services(settings)
        app.state.services = services
        logger.info(
            "application.started",
            environment=settings.environment.value,
            version=settings.version,
            database_url=settings.database.masked_url,
            redis_url=settings.redis.masked_url,
        )
        try:
            yield
        finally:
            await shutdown_services(services)
            logger.info("application.stopped")

    expose_docs = settings.app.expose_docs is True

    app = FastAPI(
        title="CYBER AI API",
        description=DESCRIPTION,
        version=settings.version,
        root_path=settings.app.root_path,
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_docs else None,
    )

    # Added last == outermost. Correlation must wrap everything so that even a
    # rejected CORS preflight or a failed request carries a request id.
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.environment.is_deployed)
    app.add_middleware(AccessLogMiddleware, silent_paths=tuple(settings.logging.silent_paths))
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.app.trusted_hosts,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "Idempotency-Key",
            "X-CSRF-Token",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(
        ResponseStartTimeoutMiddleware,
        timeout_seconds=settings.app.request_timeout_seconds,
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=settings.app.max_request_body_bytes,
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(v1_router)

    return app
