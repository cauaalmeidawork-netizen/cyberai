# M7 Security Policy and Abuse Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic tenant-aware security policy, prompt-injection defenses, audit events, and abuse controls without changing the core AI architecture.

**Architecture:** `OrchestratorService` remains the application boundary for chat enforcement. Billing runs first, then policy input checks, RAG context checks, model generation, and buffered output policy before any response deltas are sent to clients. Audit persistence is tenant-scoped with fail-closed RLS.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL/RLS, existing metrics abstraction, existing OpenTelemetry helpers, deterministic Python rules.

**Spec:** User-approved M7 design in chat. Output policy uses temporary full-response buffering: no `TextDelta` is sent before final policy decision; provider TTFT metrics remain provider-side and must not be confused with client-perceived first byte.

## Global Constraints

- Do not implement LLM-as-policy-judge or external classifiers.
- Do not store JWT, API keys, Authorization headers, full prompts, full retrieved documents, or full responses in audit.
- Do not use org_id/user_id/request_id/content as metric labels.
- Policy output denies use 403-style policy errors, not 502.
- RAG retrieved context is untrusted data and must not become system instructions.
- Legitimate defensive cybersecurity content must remain allowed.
- Tests must not use skip, xfail, noqa, or type ignore to mask issues.

---

### Task 1: Policy Domain

- [ ] Add tests for `PolicyEngine`, `PolicyContext`, decisions, input allow/deny, output sanitize/deny, defensive cybersecurity allow, and prompt-injection detection.
- [ ] Implement `cyberai.modules.policy` deterministic rules and typed errors.
- [ ] Run `uv run pytest tests/test_policy_domain.py --tb=short -q`.

### Task 2: RAG Context Protection

- [ ] Add tests proving malicious retrieved chunks are removed/sanitized and retrieved context cannot overwrite system policy.
- [ ] Implement trusted message assembly with explicit system/user/retrieved-context separation.
- [ ] Run `uv run pytest tests/test_policy_orchestrator.py --tb=short -q`.

### Task 3: Output Buffering Policy

- [ ] Add tests proving provider deltas are buffered and not yielded before output allow/sanitize/deny.
- [ ] Preserve provider metrics path; do not reinterpret provider TTFT as client first byte.
- [ ] Document buffering as temporary M7 limitation in code comments.
- [ ] Run `uv run pytest tests/test_policy_orchestrator.py --tb=short -q`.

### Task 4: Audit and Abuse Controls

- [ ] Add integration tests for tenant-scoped `SecurityAuditEvent` RLS and audit metadata redaction.
- [ ] Add unit tests for repeated abuse score/window behavior with hashed identifiers.
- [ ] Implement audit recorder, in-memory abuse tracker, DB model and migration.
- [ ] Run policy/audit tests.

### Task 5: Observability and Wiring

- [ ] Wire `PolicyEngine`, `SecurityAuditRecorder`, and `AbuseTracker` in `container.py` and `state.py`.
- [ ] Add low-cardinality metrics and lightweight spans.
- [ ] Run full quality gates.
