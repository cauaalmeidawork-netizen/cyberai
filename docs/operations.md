# Production Operations

This document defines the minimum production contract for running Nomercy AI.
It does not add product functionality; it describes how to deploy and operate
the existing modular monolith safely.

## Deployment Flow

The reference runtime for go-live is a managed Linux Docker host behind HTTPS
termination, using managed PostgreSQL and managed Redis. Images are built by
GitHub Actions, pushed to GHCR, then deployed with
`infra/compose/docker-compose.production.yml`. Kubernetes is intentionally not
part of the M12 reference path.

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

Set `NOMERCY_ENVIRONMENT=production` or `staging` and provide explicit values:

- `NOMERCY_DATABASE__URL`: PostgreSQL asyncpg URL.
- `NOMERCY_REDIS__URL`: Redis URL for rate limiting and shared transient state.
- `NOMERCY_AUTH__LEGACY_BEARER_ENABLED=false`: legacy Bearer auth is forbidden
  in staging/production.
- `NOMERCY_AUTH__OIDC_ENABLED=true`: enables real OIDC login.
- `NOMERCY_AUTH__OIDC_ISSUER`: OIDC issuer used for discovery.
- `NOMERCY_AUTH__OIDC_CLIENT_ID`: OIDC client id.
- `NOMERCY_AUTH__OIDC_CLIENT_SECRET`: provider secret from a secret manager.
- `NOMERCY_AUTH__OIDC_REDIRECT_URI`: backend callback URL.
- `NOMERCY_AUTH__OIDC_AUTO_PROVISION_ENABLED=false`: production login requires
  a previously authorized identity and active membership unless a controlled
  bootstrap mode is explicitly introduced.
- `NOMERCY_AUTH__SESSION_SECRET` and `NOMERCY_AUTH__CSRF_SECRET`:
  high-entropy secrets from a secret manager.
- `NOMERCY_AUTH__SESSION_SECURE_COOKIE=true`.
- `NOMERCY_APP__CORS_ORIGINS`: exact browser origins.
- `NOMERCY_APP__TRUSTED_HOSTS`: exact API hosts.
- `NOMERCY_LOGGING__FORMAT=json`.
- `NOMERCY_OPENAI_COMPATIBLE__ENABLED=true`.
- `NOMERCY_OPENAI_COMPATIBLE__API_KEY`: provider secret from environment only.
- `NOMERCY_MODELS__DEFAULT_MODEL`: real configured model key.
- `NOMERCY_MODELS__FALLBACK_MODELS`: real fallback model keys, or `[]`.
- `NOMERCY_POLICY__ENABLED=true`.
- `NOMERCY_BILLING__PROVIDER=stripe`.
- `NOMERCY_BILLING__STRIPE_SECRET_KEY`: Stripe API secret from a secret manager.
- `NOMERCY_BILLING__STRIPE_WEBHOOK_SECRET`: Stripe webhook signing secret.
- `NOMERCY_BILLING__STRIPE_PRICE_IDS`: JSON map of local plan keys to Stripe price IDs.
- `NOMERCY_BILLING__CHECKOUT_SUCCESS_URL`, `CHECKOUT_CANCEL_URL`,
  `PORTAL_RETURN_URL`: browser URLs for Stripe redirects.

Production and staging refuse to start with mock model defaults or fallbacks.
Mock providers are only for local development, tests and CI.
Production and staging also refuse to start when legacy Bearer authentication
is enabled or OIDC/session secrets are missing.
When `billing.provider=stripe`, production and staging refuse to start if Stripe
secrets, price IDs or redirect URLs are missing.

## Release Workflow

The protected `Release` workflow:

1. builds API and web Docker images;
2. pushes images to GHCR;
3. copies the production Compose file to the runtime host;
4. runs the migration profile before rollout;
5. starts API/web;
6. runs smoke tests against the production API base URL.

PR CI never deploys.

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

Automated backup command:

```bash
python scripts/pg_backup.py --database-url "$NOMERCY_DATABASE__URL" --output backups/nomercy.dump
```

Restore validation command:

```bash
python scripts/pg_restore_check.py \
  --admin-url "$POSTGRES_ADMIN_URL" \
  --backup backups/nomercy.dump \
  --database nomercy_restore_check
```
