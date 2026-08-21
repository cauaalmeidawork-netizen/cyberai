"""Documents and RAG retrieval endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.api.auth import CurrentUserDep, Permission, require_csrf, require_permission
from cyberai.api.deps import (
    BillingRepositoryDep,
    DatabaseDep,
    MetricsDep,
    PlanCatalogDep,
    SettingsDep,
)
from cyberai.modules.billing.entitlements import EntitlementService
from cyberai.modules.billing.errors import EntitlementDeniedError
from cyberai.modules.rag.pipeline import IngestionPipeline
from cyberai.modules.rag.providers import MockEmbeddingProvider, PgVectorStore, StandardRetriever
from cyberai.modules.rag.service import RagService
from cyberai.observability.metrics import MetricsRecorder
from cyberai.platform.db.models import Document, Project
from cyberai.platform.db.tenant import TenantContext

router = APIRouter(tags=["documents"], dependencies=[])


# --- Request and Response Models ---


class DocumentCreate(BaseModel):
    title: str
    content: str
    source_type: str = "text"


class DocumentResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    source_type: str
    status: str
    content_hash: str
    model_config = ConfigDict(from_attributes=True)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 3


class RetrievedChunkResponse(BaseModel):
    content: str
    metadata: dict[str, Any] | None
    score: float


# --- Helpers ---


def build_rag_service(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    metrics: MetricsRecorder,
    project_id: uuid.UUID | None = None,
) -> RagService:
    embeddings = MockEmbeddingProvider(metrics=metrics)
    store = PgVectorStore(session, org_id=org_id, project_id=project_id, metrics=metrics)
    pipeline = IngestionPipeline(embeddings, store)
    retriever = StandardRetriever(embeddings, store, metrics=metrics)
    return RagService(
        session, org_id=org_id, pipeline=pipeline, retriever=retriever, metrics=metrics
    )


async def verify_project_access(
    db: DatabaseDep, project_id: uuid.UUID, user: CurrentUserDep
) -> None:
    """Ensure the project belongs to the user's organization."""
    # Note: RLS ensures we only see projects for the current org context anyway,
    # but doing an explicit check returns a 404 cleanly.
    stmt = select(Project).where(Project.id == project_id, Project.org_id == user.org_id)
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        project = await session.scalar(stmt)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")


# --- Endpoints ---


@router.post("/projects/{project_id}/documents", response_model=DocumentResponse)
async def create_document(
    project_id: uuid.UUID,
    payload: DocumentCreate,
    user: CurrentUserDep,
    db: DatabaseDep,
    metrics: MetricsDep,
    billing_repository: BillingRepositoryDep,
    plan_catalog: PlanCatalogDep,
    request: Request,
    settings: SettingsDep,
) -> Document:
    """Upload and ingest a new document."""
    require_permission(user, Permission.DOCUMENT_WRITE)
    await require_csrf(request=request, db=db, settings=settings)
    await verify_project_access(db, project_id, user)
    subscription = await billing_repository.get_subscription(user.org_id)
    document_count_stmt = (
        select(func.count()).select_from(Document).where(Document.org_id == user.org_id)
    )
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        current_documents = await session.scalar(document_count_stmt) or 0
    decision = EntitlementService(plan_catalog).can_ingest_document(subscription, current_documents)
    if not decision.allowed:
        raise EntitlementDeniedError(
            "Document ingestion is not allowed by the current plan.",
            extra={"reason": decision.reason},
        )

    try:
        async with db.session(TenantContext(org_id=user.org_id)) as session:
            rag_service = build_rag_service(
                session,
                org_id=user.org_id,
                project_id=project_id,
                metrics=metrics,
            )
            return await rag_service.ingest_document(
                project_id=project_id,
                title=payload.title,
                content=payload.content,
                source_type=payload.source_type,
            )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/projects/{project_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    project_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> list[Document]:
    """List all documents for a project."""
    require_permission(user, Permission.DOCUMENT_READ)
    await verify_project_access(db, project_id, user)

    stmt = (
        select(Document)
        .where(Document.project_id == project_id, Document.org_id == user.org_id)
        .order_by(Document.created_at.desc())
    )
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        result = await session.execute(stmt)
        return list(result.scalars())


@router.get("/projects/{project_id}/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> Document:
    """Get a specific document."""
    require_permission(user, Permission.DOCUMENT_READ)
    await verify_project_access(db, project_id, user)

    stmt = select(Document).where(
        Document.id == document_id,
        Document.project_id == project_id,
        Document.org_id == user.org_id,
    )
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        doc = await session.scalar(stmt)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
async def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
    metrics: MetricsDep,
    request: Request,
    settings: SettingsDep,
) -> None:
    """Delete a document and all its chunks."""
    require_permission(user, Permission.DOCUMENT_WRITE)
    await require_csrf(request=request, db=db, settings=settings)
    await verify_project_access(db, project_id, user)

    # Check if doc exists in project first
    stmt = select(Document.id).where(
        Document.id == document_id,
        Document.project_id == project_id,
        Document.org_id == user.org_id,
    )
    async with db.session(TenantContext(org_id=user.org_id)) as session:
        doc_id = await session.scalar(stmt)
        if not doc_id:
            raise HTTPException(status_code=404, detail="Document not found")

        rag_service = build_rag_service(
            session,
            org_id=user.org_id,
            project_id=project_id,
            metrics=metrics,
        )
        deleted = await rag_service.delete_document(document_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")


@router.post("/projects/{project_id}/rag/retrieve", response_model=list[RetrievedChunkResponse])
async def retrieve_chunks(
    project_id: uuid.UUID,
    payload: RetrieveRequest,
    user: CurrentUserDep,
    db: DatabaseDep,
    metrics: MetricsDep,
) -> list[RetrievedChunkResponse]:
    """Test retrieval for a query in the RAG system."""
    require_permission(user, Permission.DOCUMENT_READ)
    await verify_project_access(db, project_id, user)

    async with db.session(TenantContext(org_id=user.org_id)) as session:
        rag_service = build_rag_service(
            session,
            org_id=user.org_id,
            project_id=project_id,
            metrics=metrics,
        )
        chunks = await rag_service.retrieve(payload.query, top_k=payload.top_k)
    return [
        RetrievedChunkResponse(
            content=c.content,
            metadata=c.metadata,
            score=c.score,
        )
        for c in chunks
    ]
