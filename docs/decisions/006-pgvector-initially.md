# ADR-006: pgvector Initially

## Context

RAG needs a vector store. Dedicated vector databases add operational complexity
at the MVP stage.

## Decision

Use PostgreSQL + pgvector initially, behind a `VectorStore` abstraction.

## Consequences

- One database, one operational surface.
- The abstraction prevents lock-in; a specialized vector store can be plugged
  in later without changing RAG consumers.
- pgvector is sufficient for the first tens of thousands of documents.
