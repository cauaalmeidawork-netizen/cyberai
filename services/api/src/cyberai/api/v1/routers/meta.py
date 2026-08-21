"""Service metadata."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cyberai.api.deps import SettingsDep

router = APIRouter(tags=["meta"])


class ServiceMeta(BaseModel):
    service: str
    version: str
    environment: str
    api_version: str
    build_commit: str
    build_time: str


@router.get("/meta", response_model=ServiceMeta, summary="Service metadata")
async def service_meta(settings: SettingsDep) -> ServiceMeta:
    return ServiceMeta(
        service=settings.app.name,
        version=settings.version,
        environment=settings.environment.value,
        api_version="v1",
        build_commit=settings.build.commit,
        build_time=settings.build.time,
    )
