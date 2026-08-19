# ADR-005: PostgreSQL + Row Level Security for Multi-Tenancy

## Context

The product needs User > Organization > Project > Conversation isolation.
Options range from shared schema with application filtering to database-per-
tenant.

## Decision

Use shared database + shared schema with an `org_id` column on every tenant-
scoped table, protected by PostgreSQL Row Level Security. The application sets
a transaction-scoped configuration variable, and policies enforce isolation at
the database layer.

## Consequences

- Strong isolation even when application code has a bug.
- Works with a single database at small scale.
- A path exists to dedicated schema or database for Enterprise customers.
- Requires every tenant-scoped query to run inside a transaction.
