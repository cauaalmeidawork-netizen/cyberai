"""Liveness and readiness probes.

The two are deliberately different:

* ``/healthz`` answers "is this process alive?" and touches nothing. A
  dependency outage must not make an orchestrator kill healthy processes.
* ``/readyz`` answers "should this instance receive traffic?" and probes every
  dependency, returning 503 when any of them is down.

Both are unauthenticated, and both are careful to expose failure *categories*
rather than connection strings or driver messages.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from cyberai.api.deps import CacheDep, DatabaseDep, InferenceGatewayDep, SettingsDep

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str
    version: str
    environment: str


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str = Field(examples=["ready", "degraded"])
    dependencies: list[DependencyStatus]


@router.get("/healthz", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(settings: SettingsDep) -> LivenessResponse:
    return LivenessResponse(
        status="ok",
        service=settings.app.name,
        version=settings.version,
        environment=settings.environment.value,
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(
    response: Response,
    database: DatabaseDep,
    cache: CacheDep,
    inference: InferenceGatewayDep,
) -> ReadinessResponse:
    dependencies = [
        DependencyStatus(name="postgresql", healthy=await database.check_health()),
        DependencyStatus(name="redis", healthy=await cache.check_health()),
    ]
    for name, health in (await inference.health()).items():
        dependencies.append(
            DependencyStatus(name=f"inference:{name}", healthy=health.healthy, detail=health.detail)
        )

    ready = all(dependency.healthy for dependency in dependencies)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if ready else "degraded", dependencies=dependencies)
