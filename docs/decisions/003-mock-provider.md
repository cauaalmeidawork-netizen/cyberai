# ADR-003: MockModelProvider

## Context

Initial development is on a laptop without a GPU. Waiting for GPU infrastructure
or vendor accounts would block every other layer.

## Decision

Implement a first-class `MockModelProvider` behind the same interface as real
providers. It simulates success and failure modes and remains part of the test
suite forever.

## Consequences

- Frontend, backend, RAG plumbing and tests can be built without a model.
- Deterministic failures make circuit-breaker and fallback tests reliable.
- The mock provider is not throwaway code; it is a test fixture.
