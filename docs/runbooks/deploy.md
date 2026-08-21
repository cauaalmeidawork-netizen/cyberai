# Deploy Runbook

1. Confirm PR CI is green.
2. Create a release tag or run the protected `Release` workflow manually.
3. Confirm images are pushed to GHCR.
4. The workflow copies `infra/compose/docker-compose.production.yml` to the runtime host.
5. The workflow runs `docker compose --profile migrate run --rm migrate`.
6. If migrations pass, the workflow runs `docker compose up -d api web`.
7. The workflow runs `python scripts/smoke.py --base-url $PRODUCTION_API_BASE_URL`.
8. Verify `/health/ready`, `/metrics`, OIDC login and Stripe webhook delivery.

Rollback application image by redeploying the previous image tags. Do not run
Alembic downgrade automatically. Prefer forward-fix for schema changes unless a
specific reversible migration has been tested.
