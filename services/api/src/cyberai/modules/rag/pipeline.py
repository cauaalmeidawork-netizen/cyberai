"""RAG Ingestion Pipeline."""

from __future__ import annotations

import re
from typing import Any

from cyberai.modules.rag.abstractions import EmbeddingProvider, VectorStore
from cyberai.platform.db.models import Chunk, Document


class Parser:
    """Extracts raw text from different source formats.

    For M2, we support basic text and markdown. Complex formats like PDF
    are deferred to avoid unnecessary complexity in the foundation.
    """

    @staticmethod
    def parse(raw_content: str, source_type: str = "text") -> str:
        if source_type == "markdown":
            # For M2, markdown is mostly treated as text.
            # In the future, this would strip markdown tags or extract headers.
            pass
        return raw_content


class Cleaner:
    """Normalizes text by removing invisible characters and extra whitespace."""

    @staticmethod
    def clean(text: str) -> str:
        # Replace multiple spaces/newlines with a single space/newline
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class Chunker:
    """Splits text into manageable chunks for embedding."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 100) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        """Naive character-based chunking for M2."""
        chunks = []
        start = 0
        text_len = len(text)

        if text_len == 0:
            return []

        while start < text_len:
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.overlap

        return chunks


class IngestionPipeline:
    """Coordinates parsing, cleaning, chunking, embedding, and storage."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        store: VectorStore,
        chunker: Chunker | None = None,
    ) -> None:
        self.embeddings = embeddings
        self.store = store
        self.chunker = chunker or Chunker()

    async def run(
        self, document: Document, raw_content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Process a document and store its chunks."""
        # 1. Parse
        parsed_text = Parser.parse(raw_content, source_type=document.source_type)

        # 2. Clean
        cleaned_text = Cleaner.clean(parsed_text)

        # 3. Chunk
        text_chunks = self.chunker.chunk(cleaned_text)
        if not text_chunks:
            return

        # 4. Embed
        vectors = await self.embeddings.embed_documents(text_chunks)

        # 5. Store
        chunks_to_insert = []
        for text_chunk, vector in zip(text_chunks, vectors, strict=True):
            chunks_to_insert.append(
                Chunk(
                    org_id=document.org_id,
                    document_id=document.id,
                    content=text_chunk,
                    metadata_json=metadata or {},
                    embedding=vector,
                )
            )

        await self.store.add_chunks(chunks_to_insert)
