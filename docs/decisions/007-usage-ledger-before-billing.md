# ADR-007: Usage Ledger Before Billing

## Context

Billing will be introduced later, but understanding cost per request/user/org/
model/provider is essential from the first model call.

## Decision

Record a structured `UsageRecord` for every model invocation from M0. The
ledger is written to logs in M0 and persisted in a later milestone; the shape
is stable.

## Consequences

- Cost and gross margin can be analysed before billing exists.
- Pricing changes do not require migration of provider response parsers.
- `estimated_cost_usd` (our price table) and `actual_cost_usd` (provider bill)
  can be compared to catch drift.
