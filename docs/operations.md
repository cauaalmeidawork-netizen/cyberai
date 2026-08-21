# Production Operations

This document defines the minimum production contract for running CYBER AI.
It does not add product functionality; it describes how to deploy and operate
the existing modular monolith safely.

## Deployment Flow

Run migrations as an explicit deployment step before rolling out API instances:

```bash
cd services/api
uv run alembic upgrade head
```

For Docker Compose local validation, run:

```bash
docker compose -f infra/compose/docker-compose.yml --profile migrate run --rm migrate
docker compose -f infra/compose/docker-compose.yml up --build
```

Production startup must not run destructive or schema-changing migrations
silently inside the API process. The API readiness probe only verifies that the
database revision equals the expected Alembic head.

## Required Production Configuration

Set `CYBERAI_ENVIRONMENT=production` or `staging` and provide explicit values:

- `CYBERAI_DATABASE__URL`: PostgreSQL asyncpg URL.
- `CYBERAI_REDIS__URL`: Redis URL for rate limiting and shared transient state.
- `CYBERAI_AUTH__JWT_SECRET`: high-entropy secret from a secret manager.
- `CYBERAI_APP__CORS_ORIGINS`: exact browser origins.
- `CYBERAI_APP__TRUSTED_HOSTS`: exact API hosts.
- `CYBERAI_LOGGING__FORMAT=json`.
- `CYBERAI_OPENAI_COMPATIBLE__ENABLED=true`.
- `CYBERAI_OPENAI_COMPATIBLE__API_KEY`: provider secret from environment only.
- `CYBERAI_MODELS__DEFAULT_MODEL`: real configured model key.
- `CYBERAI_MODELS__FALLBACK_MODELS`: real fallback model keys, or `[]`.
- `CYBERAI_POLICY__ENABLED=true`.

Production and staging refuse to start with mock model defaults or fallbacks.
Mock providers are only for local development, tests and CI.

## Health and Readiness

- `GET /health/live`: process liveness only.
- `GET /health/ready`: PostgreSQL, Redis, schema revision and local model
  gateway configuration.
- `GET /healthz` and `GET /readyz`: compatibility aliases.

Readiness never runs migrations and does not make paid model calls.

## Runtime Security

The API should run behind TLS termination and a trusted proxy. Runtime defaults:

- non-root containers;
- security headers;
- restrictive CORS by environment;
- Trusted Host validation;
- request body size limit;
- timeout until response start, without killing long-running streams after
  response headers have been sent;
- provider/stream timeouts handled separately by the Inference Gateway.

## Smoke Tests

After deployment:

```bash
python scripts/smoke.py --base-url https://api.example.com
```

The smoke test checks liveness, readiness, expected auth failure, metadata and
metrics. It does not call a paid model provider.

## Backup and Recovery Assumptions

- PostgreSQL is the source of truth for tenant data, documents, chunks, usage,
  billing foundation and audit events.
- Vector data stored through pgvector is part of PostgreSQL backup scope.
- Redis is transient shared state and must not be the only copy of critical
  accounting or tenant data.
- Restores must apply migrations to a revision compatible with the application
  image being rolled out.
- Migration jobs should be tested against restored backups before production
  rollout when a migration changes tenant-scoped data or RLS policies.
