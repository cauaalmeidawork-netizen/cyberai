"""RAG Application Service."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.modules.rag.abstractions import RetrievedChunk, Retriever
from cyberai.modules.rag.pipeline import IngestionPipeline
from cyberai.platform.db.models import Document


class RagService:
    """Coordinates Document ingestion and retrieval."""

    def __init__(
        self,
        session: AsyncSession,
        pipeline: IngestionPipeline,
        retriever: Retriever,
    ) -> None:
        self.session = session
        self.pipeline = pipeline
        self.retriever = retriever

    def _hash_content(self, content: str) -> str:
        """Create a SHA-256 hash of the content for deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def ingest_document(
        self,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        title: str,
        content: str,
        source_type: str = "text",
    ) -> Document:
        """Ingest a document into the RAG system.

        Raises ValueError if the exact content is already ingested in this project.
        """
        content_hash = self._hash_content(content)

        # 1. Deduplication Check
        # Ensure it is unique within the project. RLS already enforces org scoping,
        # but we explicitly filter by project_id and content_hash.
        stmt = select(Document).where(
            Document.project_id == project_id,
            Document.content_hash == content_hash,
        )
        existing = await self.session.scalar(stmt)
        if existing:
            raise ValueError(
                f"Document with identical content already exists"
                f" in project (ID: {existing.id})"
            )

        # 2. Persist Document as pending
        doc = Document(
            org_id=org_id,
            project_id=project_id,
            title=title,
            content_hash=content_hash,
            source_type=source_type,
            status="pending",
        )
        self.session.add(doc)
        await self.session.flush()
        await self.session.refresh(doc)

        # 3. Run Pipeline Synchronously for M3
        try:
            await self.pipeline.run(document=doc, raw_content=content)
            doc.status = "completed"
        except Exception:
            doc.status = "error"
            raise
        finally:
            self.session.add(doc)
            await self.session.flush()

        return doc

    async def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Retrieve chunks for a query.

        This delegates to the underlying Retriever. Row Level Security ensures
        only chunks for the current tenant are returned.
        """
        return await self.retriever.retrieve(query, top_k=top_k)

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        """Delete a document by ID. Chunks are CASCADE deleted by PostgreSQL."""
        doc = await self.session.get(Document, document_id)
        if not doc:
            return False

        await self.session.delete(doc)
        await self.session.flush()
        return True
