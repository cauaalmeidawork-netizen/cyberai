"""Documents and RAG retrieval endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from cyberai.api.auth import CurrentUserDep
from cyberai.api.deps import DatabaseDep, RagServiceDep
from cyberai.platform.db.models import Document, Project

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

async def verify_project_access(
    db: DatabaseDep, project_id: uuid.UUID, user: CurrentUserDep
) -> None:
    """Ensure the project belongs to the user's organization."""
    # Note: RLS ensures we only see projects for the current org context anyway,
    # but doing an explicit check returns a 404 cleanly.
    stmt = select(Project).where(Project.id == project_id)
    async with db.session() as session:
        project = await session.scalar(stmt)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")


# --- Endpoints ---

@router.post("/projects/{project_id}/documents", response_model=DocumentResponse)
async def create_document(
    project_id: uuid.UUID,
    payload: DocumentCreate,
    rag_service: RagServiceDep,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> Document:
    """Upload and ingest a new document."""
    await verify_project_access(db, project_id, user)

    try:
        doc = await rag_service.ingest_document(
            project_id=project_id,
            org_id=user.org_id,
            title=payload.title,
            content=payload.content,
            source_type=payload.source_type,
        )
        return doc
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/projects/{project_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    project_id: uuid.UUID,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> list[Document]:
    """List all documents for a project."""
    await verify_project_access(db, project_id, user)

    stmt = (
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.desc())
    )
    async with db.session() as session:
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
    await verify_project_access(db, project_id, user)

    stmt = select(Document).where(
        Document.id == document_id, Document.project_id == project_id
    )
    async with db.session() as session:
        doc = await session.scalar(stmt)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
async def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    rag_service: RagServiceDep,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> None:
    """Delete a document and all its chunks."""
    await verify_project_access(db, project_id, user)

    # Check if doc exists in project first
    stmt = select(Document.id).where(
        Document.id == document_id, Document.project_id == project_id
    )
    async with db.session() as session:
        doc_id = await session.scalar(stmt)
        if not doc_id:
            raise HTTPException(status_code=404, detail="Document not found")

    deleted = await rag_service.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")


@router.post("/projects/{project_id}/rag/retrieve", response_model=list[RetrievedChunkResponse])
async def retrieve_chunks(
    project_id: uuid.UUID,
    payload: RetrieveRequest,
    rag_service: RagServiceDep,
    user: CurrentUserDep,
    db: DatabaseDep,
) -> list[RetrievedChunkResponse]:
    """Test retrieval for a query in the RAG system."""
    await verify_project_access(db, project_id, user)

    chunks = await rag_service.retrieve(payload.query, top_k=payload.top_k)
    return [
        RetrievedChunkResponse(
            content=c.content,
            metadata=c.metadata,
            score=c.score,
        )
        for c in chunks
    ]
