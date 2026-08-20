"""RAG Providers and Concrete Implementations."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cyberai.modules.rag.abstractions import (
    EmbeddingProvider,
    RetrievedChunk,
    Retriever,
    VectorStore,
)
from cyberai.platform.db.models import Chunk


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic mock embedding provider for tests and local dev without GPU.

    It creates a 384-dimensional vector by hashing chunks of the text,
    ensuring the same text always produces the same vector.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _hash_to_float(self, text: str, index: int) -> float:
        """Deterministically map text and an index to a float between -1.0 and 1.0."""
        h = hashlib.sha256(f"{text}:{index}".encode()).hexdigest()
        # Use first 8 hex chars as an integer, then normalize
        val = int(h[:8], 16)
        return (val / 0xFFFFFFFF) * 2.0 - 1.0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[self._hash_to_float(t, i) for i in range(self.dim)] for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [self._hash_to_float(text, i) for i in range(self.dim)]


class PgVectorStore(VectorStore):
    """PostgreSQL pgvector implementation of VectorStore."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with an active database session.

        The session must already have the tenant context applied.
        """
        self.session = session

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
        stmt = (
            select(Chunk)
            .order_by(Chunk.embedding.cosine_distance(query_vector))
            .limit(top_k)
        )
        result = await self.session.execute(stmt)

        return [
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


class StandardRetriever(Retriever):
    """Combines an EmbeddingProvider and a VectorStore to retrieve context."""

    def __init__(self, embeddings: EmbeddingProvider, store: VectorStore) -> None:
        self.embeddings = embeddings
        self.store = store

    async def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        query_vector = await self.embeddings.embed_query(query)
        return await self.store.search(query_vector, top_k)
