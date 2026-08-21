"""Version 1 of the public API."""

from fastapi import APIRouter

from cyberai.api.v1.routers import (
    auth,
    billing,
    conversations,
    documents,
    meta,
    models,
    organizations,
    projects,
)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(meta.router)
v1_router.include_router(auth.router)
v1_router.include_router(organizations.router)
v1_router.include_router(models.router)
v1_router.include_router(projects.router)
v1_router.include_router(conversations.router)
v1_router.include_router(documents.router)
v1_router.include_router(billing.router)

__all__ = ["v1_router"]
