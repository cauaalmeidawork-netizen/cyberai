"""RAG Core Abstractions.

Defines the interfaces for the RAG pipeline components to avoid tight coupling
to specific vector databases or embedding models.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from cyberai.platform.db.models import Chunk


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk of text returned by a Retriever."""

    content: str
    metadata: dict[str, Any] | None
    score: float


class EmbeddingProvider(abc.ABC):
    """Abstract provider for text embeddings."""

    @abc.abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of documents/chunks."""
        ...

    @abc.abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generate an embedding for a search query."""
        ...


class VectorStore(abc.ABC):
    """Abstract storage for vector embeddings."""

    @abc.abstractmethod
    async def add_chunks(self, chunks: list[Chunk]) -> None:
        """Add chunks to the vector store.

        The store implementation is responsible for persisting the chunks.
        """
        ...

    @abc.abstractmethod
    async def search(self, query_vector: list[float], top_k: int = 3) -> list[RetrievedChunk]:
        """Search for the most similar chunks.

        Note: RLS (Row Level Security) ensures that the search only returns
        chunks that belong to the current tenant.
        """
        ...


class Retriever(abc.ABC):
    """Abstract retriever orchestrating query embedding and vector search."""

    @abc.abstractmethod
    async def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Retrieve relevant chunks for a given query."""
        ...
