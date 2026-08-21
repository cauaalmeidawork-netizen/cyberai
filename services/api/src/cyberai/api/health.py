"""Liveness and readiness probes.

The two are deliberately different:

* ``/health/live`` answers "is this process alive?" and touches nothing. A
  dependency outage must not make an orchestrator kill healthy processes.
* ``/health/ready`` answers "should this instance receive traffic?" and probes every
  dependency, returning 503 when any of them is down.

Both are unauthenticated, and both are careful to expose failure *categories*
rather than connection strings or driver messages.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from cyberai.api.deps import ServicesDep, SettingsDep
from cyberai.modules.modelgw import TaskType

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str
    version: str
    environment: str
    build_commit: str
    build_time: str


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str = Field(examples=["ready", "degraded"])
    dependencies: list[DependencyStatus]


@router.get("/health/live", response_model=LivenessResponse, summary="Liveness probe")
@router.get("/healthz", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(settings: SettingsDep) -> LivenessResponse:
    return LivenessResponse(
        status="ok",
        service=settings.app.name,
        version=settings.version,
        environment=settings.environment.value,
        build_commit=settings.build.commit,
        build_time=settings.build.time,
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(
    response: Response,
    services: ServicesDep,
) -> ReadinessResponse:
    dependencies = [
        DependencyStatus(name="postgresql", healthy=await services.database.check_health()),
        DependencyStatus(name="redis", healthy=await services.cache.check_health()),
    ]
    schema = await services.database.check_schema_revision()
    dependencies.append(
        DependencyStatus(
            name="schema",
            healthy=schema.healthy,
            detail=schema.detail if schema.healthy else "schema_not_current",
        )
    )
    dependencies.append(_model_gateway_status(services))

    ready = all(dependency.healthy for dependency in dependencies)
    for dependency in dependencies:
        services.metrics.gauge(
            "dependency_health",
            labels={
                "dependency": dependency.name,
                "status": "healthy" if dependency.healthy else "unhealthy",
            },
        ).set(1)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if ready else "degraded", dependencies=dependencies)


def _model_gateway_status(services: ServicesDep) -> DependencyStatus:
    try:
        route = services.router.resolve(TaskType.CHAT)
    except Exception:
        return DependencyStatus(name="model_gateway", healthy=False, detail="routing_unavailable")
    provider_configured = services.providers.has(route.primary.provider) and all(
        services.providers.has(model.provider) for model in route.fallbacks
    )
    if not provider_configured:
        return DependencyStatus(
            name="model_gateway",
            healthy=False,
            detail="provider_not_configured",
        )
    return DependencyStatus(name="model_gateway", healthy=True, detail="configured")
