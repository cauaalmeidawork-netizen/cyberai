# Incident Runbooks

## Migration Failure

Stop rollout. Keep old API/web running if possible. Inspect Alembic error logs.
If no destructive migration ran, fix forward and rerun the migration job. If
partial effects exist, restore from backup into a new database and validate.

## DB Unavailable

Check managed PostgreSQL status, connection limits and storage. API readiness
should fail. Do not restart-loop the API until the database is healthy.

## Redis Unavailable

Billing rate limiter may degrade according to configured fail behavior. Check
Redis service status and network. Confirm PostgreSQL usage ledger remains intact.

## Provider Unavailable

Confirm provider status and API key validity. Disable affected model route by
configuration or switch fallback model if available. Watch inference errors.

## OIDC Unavailable

Existing sessions may continue until expiry. New login fails. Confirm discovery
URL, JWKS, client credentials and redirect URI. Do not enable legacy Bearer in
production.

## Billing Webhook Failure

Check Stripe webhook delivery logs and `billing_webhook_events` rows with
`status='failed'`. Fix the processing issue, then replay the Stripe event from
the Stripe dashboard or CLI. Processed event IDs are idempotent and will not
reapply effects.

## Session Or Security Incident

Rotate session/CSRF secrets according to secret manager procedure, revoke active
sessions if needed, preserve audit logs, and rotate OIDC/provider/billing
secrets if exposure is suspected.
