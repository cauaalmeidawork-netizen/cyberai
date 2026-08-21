# Beta SLOs

These SLOs are intentionally conservative until production traffic establishes
real baselines.

- API availability: 99.0% monthly for non-LLM API endpoints.
- Non-LLM API latency: p95 under 1 second over 30 days.
- Chat success rate: 95% of requests complete without policy, quota or provider failure.
- Billing webhook processing: 99.5% of valid Stripe webhooks processed within 5 minutes.
- Readiness: production instances should be ready 99.0% of the time outside planned deploy windows.

## Measurement

- Availability: HTTP 2xx/3xx/4xx expected responses divided by all non-health requests.
- Latency: `http_request_duration_seconds` excluding streaming provider duration where route labels allow.
- Chat success: `ai_orchestrator_requests_total` by status.
- Billing webhook: `billing_webhook_events_total` by status and operational logs.
- Readiness: health probe history for `/health/ready`.
