"""Tests for M2 RAG Foundation."""

from __future__ import annotations

import pytest

from cyberai.modules.rag.pipeline import Chunker, Cleaner, Parser
from cyberai.modules.rag.providers import MockEmbeddingProvider


def test_parser_basic() -> None:
    text = "Hello world"
    assert Parser.parse(text) == text
    assert Parser.parse(text, source_type="markdown") == text


def test_cleaner() -> None:
    text = "Hello    world\n\n\n\nTest"
    cleaned = Cleaner.clean(text)
    assert cleaned == "Hello world\n\nTest"


def test_chunker() -> None:
    chunker = Chunker(chunk_size=10, overlap=2)
    text = "abcdefghijklmno"
    chunks = chunker.chunk(text)
    assert chunks == ["abcdefghij", "ijklmno"]


@pytest.mark.asyncio
async def test_mock_embedding_provider() -> None:
    provider = MockEmbeddingProvider(dim=4)
    vector = await provider.embed_query("test query")
    assert len(vector) == 4
    for val in vector:
        assert -1.0 <= val <= 1.0

    # Test determinism
    vector2 = await provider.embed_query("test query")
    assert vector == vector2

    # Test batch
    vectors = await provider.embed_documents(["hello", "world"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 4
