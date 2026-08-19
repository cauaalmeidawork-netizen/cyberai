"""Projects CRUD."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from cyberai.api.auth import CurrentUserDep
from cyberai.api.deps import DatabaseDep
from cyberai.platform.db.models import Project
from cyberai.platform.db.tenant import TenantContext

router = APIRouter(tags=["projects"], prefix="/projects")


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    user: CurrentUserDep,
    db: DatabaseDep,
) -> Any:
    """List all projects for the current tenant."""
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        result = await session.execute(select(Project).order_by(Project.created_at.desc()))
        return [
            ProjectOut(id=str(p.id), name=p.name, description=p.description)
            for p in result.scalars()
        ]


@router.post("", response_model=ProjectOut)
async def create_project(
    payload: ProjectCreate,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> Any:
    """Create a new project."""
    project = Project(
        org_id=user.org_id,
        name=payload.name,
        description=payload.description,
    )
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        session.add(project)
        await session.commit()
        await session.refresh(project)
    return ProjectOut(
        id=str(project.id),
        name=project.name,
        description=project.description,
    )
