"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from cyberai.api.deps import ServicesDep
from cyberai.observability.prometheus import PROMETHEUS_CONTENT_TYPE, PrometheusMetricsRecorder

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics(services: ServicesDep) -> Response:
    recorder = services.metrics
    if isinstance(recorder, PrometheusMetricsRecorder):
        return Response(content=recorder.render(), media_type=PROMETHEUS_CONTENT_TYPE)
    return Response(content=b"", media_type=PROMETHEUS_CONTENT_TYPE)
