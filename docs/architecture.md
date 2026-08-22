# Architecture

Nomercy AI is a cybersecurity conversational AI platform. This document is a
synthetic, up-to-date view of the approved architecture.

## High-level flow

```text
User
 |
 v
Frontend (Next.js / React / TypeScript / Tailwind)
 |
 v
API Gateway / FastAPI
 |
 v
AI Orchestrator (M2)
 |
 +--> Model Gateway      (WHICH model)
 |      +-- fallback chain
 |      +-- task-based routing
 |      +-- usage accounting
 |
 +--> Inference Gateway  (HOW to reach it)
        +-- timeout / concurrency / circuit breaker
        +-- provider adapters (mock, commercial, local GPU)
 |
 +--> RAG / Memory / Policy (M2+)
 |
 +--> Knowledge Engine (M3+)
```

## Architectural principles

1. **Model and runtime are separate**: Model Gateway decides which model
   answers; Inference Gateway decides how to reach a model runtime.
2. **Everything is behind an interface**: providers, vector stores, identity
   providers and sinks can all be replaced without touching callers.
3. **Security boundary at the database**: PostgreSQL Row Level Security is
   mandatory for tenant-scoped tables.
4. **Untrusted content isolation**: user input, files and RAG chunks are
   never merged into system-level instructions without validation and policy.
5. **Measure before billing**: usage is recorded from the first model call,
   with a shape that supports cost per request/user/org/model/provider and
   gross margin.
6. **Start simple, scale out**: M0 is a modular monolith; extraction into
   services is enabled by the boundaries above.

## Domain modules

- `core`: framework-free kernel (config, errors, logging, ids, context).
- `platform`: infrastructure adapters (PostgreSQL, Redis, RLS).
- `modules/inference`: provider port, registry, gateway, circuit breaker.
- `modules/modelgw`: catalog, routing, gateway, usage ledger.
- `modules/policy` (M2+): structured decisions (allow / restrict / refuse / require_context).
- `modules/rag` (M3+): ingestion, chunking, embedding, retrieval, reranking.
- `modules/metering` (M5+): persistent usage records and quota enforcement.
- `modules/billing` (M7+): plans, subscriptions, payments.

## Scaling path

```text
M0  Local dev: Docker Compose, mock provider, pgvector-ready Postgres
M1  Auth + tenant API + chat CRUD
M2  AI Orchestrator + policy + prompt injection defense
M3  RAG: ingestion, chunking, retrieval, reranking, provenance
M4  Commercial provider (OpenAI / Anthropic / DeepSeek API)
M5  Usage metering + rate limiting + quotas
M6  Background workers + evaluation gate
M7  Billing integration
M8  Enterprise SSO (OIDC/SAML/SCIM)
M9  Admin panel + audit log UI
M10 Production hardening + observability
M11 Local GPU inference (vLLM / SGLang) behind Inference Gateway
M12 Multi-region / horizontal scaling
```

## Technology choices

See [decision records](decisions/) for the rationale behind each major choice.
