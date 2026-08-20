# M6 Usage Metering, Limits, and Billing Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add enterprise usage metering, plans, quotas, rate limits, and billing foundation without Stripe or customer charging.

**Architecture:** Requests enter through Auth/Tenant, the Orchestrator asks a billing `LimitEnforcer` to reserve capacity before `ModelGateway`, and `ModelGateway` records final usage through a persistent, idempotent `UsageRecorder`. Billing state is tenant-scoped and exposed through read-only tenant APIs.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL/RLS, Redis adapter boundary, existing Model Gateway usage records, existing metrics abstraction.

**Spec:** User-approved M6 design in chat, with required additions: explicit `TokenEstimator` and persistent idempotency by `request_id`.

## Global Constraints

- Do not integrate Stripe or charge customers.
- Do not store prompts or responses for billing.
- Tenant/org is the primary enforcement unit.
- All quota periods use UTC.
- Enforce before provider inference starts.
- Use `TenantContext(org_id=user.org_id)` for tenant-scoped persistence.
- Do not use high-cardinality labels such as org_id, user_id, request_id, UUIDs, prompts, or content.
- Unit tests must not require Redis.
- Preserve real integration tests separately.
- Do not use skip, xfail, noqa, or type ignore to hide issues.

---

### Task 1: Billing Domain Contracts

**Files:**
- Create: `services/api/src/cyberai/modules/billing/types.py`
- Create: `services/api/src/cyberai/modules/billing/errors.py`
- Create: `services/api/src/cyberai/modules/billing/plans.py`
- Create: `services/api/tests/test_billing_domain.py`

**Interfaces:**
- Produces `Plan`, `PlanLimits`, `Subscription`, `QuotaResource`, `QuotaSnapshot`, `TokenEstimate`, `BillingDecision`.
- Produces `EntitlementDeniedError`, `QuotaExceededError`, `RateLimitExceededError`.
- Produces `StaticPlanCatalog` with plans `free`, `pro`, `business`, `enterprise`.

- [ ] Write failing tests for plan limits, model/RAG entitlements, UTC monthly period boundaries, and token estimate conservatism.
- [ ] Implement minimal dataclasses/enums/errors/catalog to pass.
- [ ] Run `uv run pytest tests/test_billing_domain.py --tb=short -q`.

### Task 2: Rate Limiter Abstraction

**Files:**
- Create: `services/api/src/cyberai/modules/billing/rate_limit.py`
- Create: `services/api/src/cyberai/platform/cache/rate_limit.py`
- Create: `services/api/tests/test_billing_rate_limit.py`

**Interfaces:**
- Produces `RateLimiter` protocol, `RateLimitRequest`, `RateLimitResult`.
- Produces `InMemoryRateLimiter` for unit tests.
- Produces `RedisRateLimiter` adapter with explicit fail-open/fail-closed behavior from config.

- [ ] Write failing tests for org-level window, optional user-level window, no sensitive keys, and fail behavior.
- [ ] Implement in-memory limiter and Redis adapter boundary.
- [ ] Run `uv run pytest tests/test_billing_rate_limit.py --tb=short -q`.

### Task 3: Persistence and Idempotent Usage Recording

**Files:**
- Modify: `services/api/src/cyberai/platform/db/models.py`
- Create: `services/api/migrations/versions/20260820_0006_000000000006_m6_billing.py`
- Create: `services/api/src/cyberai/modules/billing/repository.py`
- Create: `services/api/src/cyberai/modules/billing/usage.py`
- Create: `services/api/tests/test_billing_usage.py`

**Interfaces:**
- Produces persistent `PlanModel`, `SubscriptionModel`, `UsageAggregateModel`, `ModelCostModel`.
- Updates existing `UsageRecordModel` for idempotency constraints.
- Produces `UsageRecorder.record_once(record)` that returns whether a request was newly recorded.

- [ ] Write failing tests for record idempotency by `(org_id, request_id)`, aggregate adjustment, and no prompt/response fields.
- [ ] Implement SQLAlchemy models and repository methods.
- [ ] Implement `PersistentUsageSink` adapter for `ModelGateway`.
- [ ] Run `uv run pytest tests/test_billing_usage.py --tb=short -q`.

### Task 4: Limit Enforcer and Orchestrator Integration

**Files:**
- Create: `services/api/src/cyberai/modules/billing/entitlements.py`
- Create: `services/api/src/cyberai/modules/billing/quotas.py`
- Create: `services/api/src/cyberai/modules/billing/enforcement.py`
- Modify: `services/api/src/cyberai/modules/orchestrator/service.py`
- Modify: `services/api/src/cyberai/modules/modelgw/usage.py`
- Modify: `services/api/src/cyberai/container.py`
- Modify: `services/api/src/cyberai/state.py`
- Create: `services/api/tests/test_billing_enforcement.py`

**Interfaces:**
- Produces `TokenEstimator` protocol and `ProviderTokenEstimator`.
- Produces `LimitEnforcer.reserve_for_request(...)`.
- `OrchestratorService.stream_chat(...)` calls enforcer before `ModelGateway`.

- [ ] Write failing tests proving quota-exceeded requests do not call provider.
- [ ] Write failing tests for model restrictions and RAG restrictions.
- [ ] Implement conservative reservation with explicit `TokenEstimator`.
- [ ] Implement aggregate locking with `SELECT ... FOR UPDATE`.
- [ ] Run `uv run pytest tests/test_billing_enforcement.py --tb=short -q`.

### Task 5: Billing API and Observability

**Files:**
- Create: `services/api/src/cyberai/api/v1/routers/billing.py`
- Modify: `services/api/src/cyberai/api/v1/__init__.py`
- Modify: `services/api/src/cyberai/api/deps.py`
- Create: `services/api/tests/test_billing_api.py`

**Interfaces:**
- Produces `GET /api/v1/billing/usage`.
- Produces `GET /api/v1/billing/limits`.
- Metrics: quota checks/exceeded, entitlement denied, rate limit checks/exceeded, usage recording.

- [ ] Write failing tests for tenant-scoped usage/limits endpoints and cross-tenant isolation.
- [ ] Implement endpoints using authenticated user context only.
- [ ] Add low-cardinality billing metrics.
- [ ] Run `uv run pytest tests/test_billing_api.py --tb=short -q`.

### Task 6: Quality Gates

**Files:**
- No new files.

**Interfaces:**
- Produces final verification evidence.

- [ ] Run `uv run pytest -m "not integration" --tb=short -q`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run ruff format --check .`.
- [ ] Run `uv run mypy src tests`.
- [ ] Run `uv run lint-imports`.
- [ ] If PostgreSQL/Redis are available, run `uv run pytest -m "integration" --tb=short -q`.
