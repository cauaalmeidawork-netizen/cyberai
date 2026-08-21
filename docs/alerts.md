# Production Alerts

Initial beta alerts use existing Prometheus metrics and health probes. Labels
must stay low-cardinality; never alert by org_id, user_id, request_id or prompt.

## Required Alerts

- API readiness down: `/health/ready` returns non-200 for 2 minutes.
- API error rate high: `5xx / total` over 5% for 10 minutes.
- Non-LLM latency high: p95 HTTP latency over 1s for 10 minutes.
- DB unavailable: `dependency_health{dependency="postgresql",status="unhealthy"}`.
- Redis unavailable: `dependency_health{dependency="redis",status="unhealthy"}`.
- Provider failures high: `inference_errors_total` increases abnormally for 10 minutes.
- Billing webhook failures: `billing_webhook_events_total{status="failed"}` increases.
- Auth failures abnormal: auth rejected/error metrics spike for 10 minutes.
- Capacity: managed PostgreSQL disk/storage over 80%.

## Example PromQL

```promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m])) > 0.05
```

```promql
histogram_quantile(0.95, sum by (le, route) (rate(http_request_duration_seconds_bucket[5m]))) > 1
```

```promql
max(dependency_health{dependency=~"postgresql|redis",status="unhealthy"}) > 0
```
