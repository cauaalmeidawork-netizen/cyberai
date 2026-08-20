"""RAG Providers and Concrete Implementations."""

from __future__ import annotations

import hashlib
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.modules.rag.abstractions import (
    EmbeddingProvider,
    RetrievedChunk,
    Retriever,
    VectorStore,
)
from cyberai.observability.metrics import MetricsRecorder, NoopMetricsRecorder
from cyberai.observability.tracing import start_span
from cyberai.platform.db.models import Chunk, Document


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock embedding provider for tests and local dev without GPU.

    It creates a 384-dimensional vector by hashing chunks of the text,
    ensuring the same text always produces the same vector.
    """

    def __init__(self, dim: int = 384, *, metrics: MetricsRecorder | None = None) -> None:
        self.dim = dim
        self.metrics = metrics or NoopMetricsRecorder()

    def _hash_to_float(self, text: str, index: int) -> float:
        """Deterministically map text and an index to a float between -1.0 and 1.0."""
        h = hashlib.sha256(f"{text}:{index}".encode()).hexdigest()
        # Use first 8 hex chars as an integer, then normalize
        val = int(h[:8], 16)
        return (val / 0xFFFFFFFF) * 2.0 - 1.0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        with start_span("rag.embed", {"rag.operation": "documents"}):
            try:
                return [[self._hash_to_float(t, i) for i in range(self.dim)] for t in texts]
            finally:
                self.metrics.histogram(
                    "rag_embedding_duration_seconds",
                    labels={"operation": "documents", "status": "success"},
                ).record(time.perf_counter() - started)

    async def embed_query(self, text: str) -> list[float]:
        started = time.perf_counter()
        with start_span("rag.embed", {"rag.operation": "query"}):
            try:
                return [self._hash_to_float(text, i) for i in range(self.dim)]
            finally:
                self.metrics.histogram(
                    "rag_embedding_duration_seconds",
                    labels={"operation": "query", "status": "success"},
                ).record(time.perf_counter() - started)


class PgVectorStore(VectorStore):
    """PostgreSQL pgvector implementation of VectorStore."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        org_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        """Initialize with an active database session.

        The session must already have the tenant context applied.
        """
        self.session = session
        self.org_id = org_id
        self.project_id = project_id
        self.metrics = metrics or NoopMetricsRecorder()

    async def add_chunks(self, chunks: list[Chunk]) -> None:
        """Add chunks to the database."""
        self.session.add_all(chunks)
        await self.session.flush()

    async def search(self, query_vector: list[float], top_k: int = 3) -> list[RetrievedChunk]:
        """Search chunks using pgvector cosine distance (<=>).

        Because the session has the tenant context applied, Row Level Security
        will automatically filter the chunks to the current organization.
        """
        # <-> is L2 distance, <=> is cosine distance, <#> is inner product
        # Cosine distance is standard for typical sentence embeddings.
        started = time.perf_counter()
        top_k_label = str(min(top_k, 20))
        with start_span("rag.vector_search", {"rag.top_k": top_k}):
            stmt = (
                select(Chunk)
                .where(Chunk.org_id == self.org_id)
                .order_by(Chunk.embedding.cosine_distance(query_vector))
                .limit(top_k)
            )
            if self.project_id is not None:
                stmt = stmt.join(Document, Document.id == Chunk.document_id).where(
                    Document.org_id == self.org_id, Document.project_id == self.project_id
                )
            result = await self.session.execute(stmt)

            chunks = [
                RetrievedChunk(
                    content=chunk.content,
                    metadata=chunk.metadata_json,
                    # Cosine distance returns 0 for exact match, so similarity is 1 - distance
                    # We mock the score since pgvector doesn't return it directly in select
                    # unless we select the distance explicitly. For M2, we just return a mock score.
                    score=1.0,
                )
                for chunk in result.scalars()
            ]
        self.metrics.histogram(
            "rag_vector_search_duration_seconds",
            labels={"top_k": top_k_label, "status": "success"},
        ).record(time.perf_counter() - started)
        return chunks


class StandardRetriever(Retriever):
    """Combines an EmbeddingProvider and a VectorStore to retrieve context."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        store: VectorStore,
        *,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self.embeddings = embeddings
        self.store = store
        self.metrics = metrics or NoopMetricsRecorder()

    async def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        started = time.perf_counter()
        top_k_label = str(min(top_k, 20))
        status = "success"
        with start_span("rag.retrieve", {"rag.top_k": top_k}):
            try:
                query_vector = await self.embeddings.embed_query(query)
                chunks = await self.store.search(query_vector, top_k)
                return chunks
            except Exception:
                status = "error"
                raise
            finally:
                self.metrics.counter(
                    "rag_retrieval_requests_total",
                    labels={"top_k": top_k_label, "status": status},
                ).add()
                self.metrics.histogram(
                    "rag_retrieval_duration_seconds",
                    labels={"top_k": top_k_label, "status": status},
                ).record(time.perf_counter() - started)
