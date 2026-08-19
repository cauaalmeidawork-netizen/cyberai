# ADR-001: Modular Monolith

## Context

The product will eventually be a multi-tenant SaaS. Starting with microservices
would create premature operational overhead, but a tangled monolith would make
later extraction impossible.

## Decision

Start as a modular monolith with explicit, import-linted boundaries. Each
domain module owns its public interface and may only depend on `core` and
`platform`.

## Consequences

- Simple deployment and local development.
- Boundaries remain real because `import-linter` fails the build on violations.
- Future extraction is a packaging change, not a rewrite.
