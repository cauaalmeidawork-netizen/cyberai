"""RAG Application Service."""

from __future__ import annotations

import hashlib
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.modules.rag.abstractions import RetrievedChunk, Retriever
from cyberai.modules.rag.pipeline import IngestionPipeline
from cyberai.observability.metrics import MetricsRecorder, NoopMetricsRecorder
from cyberai.observability.tracing import record_exception, start_span
from cyberai.platform.db.models import Document


class RagService:
    """Coordinates Document ingestion and retrieval."""

    def __init__(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        pipeline: IngestionPipeline,
        retriever: Retriever,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.pipeline = pipeline
        self.retriever = retriever
        self.metrics = metrics or NoopMetricsRecorder()

    def _hash_content(self, content: str) -> str:
        """Create a SHA-256 hash of the content for deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def ingest_document(
        self,
        project_id: uuid.UUID,
        title: str,
        content: str,
        source_type: str = "text",
    ) -> Document:
        """Ingest a document into the RAG system.

        Raises ValueError if the exact content is already ingested in this project.
        """
        started = time.perf_counter()
        status = "success"
        content_hash = self._hash_content(content)

        with start_span("rag.ingest", {"rag.source_type": source_type}) as span:
            try:
                # 1. Deduplication Check
                # Ensure it is unique within the project. RLS already enforces org scoping,
                # but we explicitly filter by project_id and content_hash.
                stmt = select(Document).where(
                    Document.org_id == self.org_id,
                    Document.project_id == project_id,
                    Document.content_hash == content_hash,
                )
                existing = await self.session.scalar(stmt)
                if existing:
                    status = "duplicate"
                    raise ValueError(
                        "Document with identical content already exists "
                        f"in project (ID: {existing.id})"
                    )

                # 2. Persist Document as pending
                doc = Document(
                    org_id=self.org_id,
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
                    status = "error"
                    doc.status = "error"
                    raise
                finally:
                    self.session.add(doc)
                    await self.session.flush()

                return doc
            except Exception as exc:
                if status == "success":
                    status = "error"
                record_exception(span, exc, attributes={"error.type": type(exc).__name__})
                raise
            finally:
                labels = {"source_type": source_type, "status": status}
                self.metrics.histogram("rag_ingestion_duration_seconds", labels=labels).record(
                    time.perf_counter() - started
                )
                if status == "success":
                    self.metrics.counter("rag_documents_ingested_total", labels=labels).add()

    async def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Retrieve chunks for a query.

        This delegates to the underlying Retriever. Row Level Security ensures
        only chunks for the current tenant are returned.
        """
        started = time.perf_counter()
        status = "success"
        top_k_label = str(min(top_k, 20))
        chunks: list[RetrievedChunk] = []
        with start_span("rag.retrieve", {"rag.top_k": top_k}) as span:
            try:
                chunks = await self.retriever.retrieve(query, top_k=top_k)
                return chunks
            except Exception as exc:
                status = "error"
                record_exception(span, exc, attributes={"error.type": type(exc).__name__})
                raise
            finally:
                labels = {"top_k": top_k_label, "status": status}
                self.metrics.histogram("rag_retrieval_duration_seconds", labels=labels).record(
                    time.perf_counter() - started
                )
                self.metrics.counter("rag_retrieval_requests_total", labels=labels).add()
                if status == "success":
                    self.metrics.gauge("rag_chunks_returned", labels=labels).set(len(chunks))

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        """Delete a document by ID. Chunks are CASCADE deleted by PostgreSQL."""
        doc = await self.session.scalar(
            select(Document).where(Document.id == document_id, Document.org_id == self.org_id)
        )
        if not doc:
            return False

        await self.session.delete(doc)
        await self.session.flush()
        return True
