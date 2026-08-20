"""Simple repeated-abuse tracker."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from cyberai.modules.policy.types import PolicyDecisionType


@dataclass(frozen=True, slots=True)
class AbuseDecision:
    decision: PolicyDecisionType
    count: int


class AbuseTracker:
    """Windowed violation counter keyed by derived identifiers only."""

    def __init__(self, *, threshold: int = 5, window_seconds: int = 300) -> None:
        self._threshold = threshold
        self._window_seconds = window_seconds
        self._windows: dict[str, tuple[datetime, int]] = {}

    def record_violation(
        self,
        *,
        org_id: str | None,
        user_id: str | None,
        rule_id: str,
        now: datetime | None = None,
    ) -> AbuseDecision:
        current = now or datetime.now(UTC)
        key = self._key(org_id=org_id, user_id=user_id, rule_id=rule_id)
        existing = self._windows.get(key)
        if existing is None or (current - existing[0]).total_seconds() >= self._window_seconds:
            self._windows[key] = (current, 1)
            return AbuseDecision(PolicyDecisionType.REVIEW, 1)
        started, count = existing
        next_count = count + 1
        self._windows[key] = (started, next_count)
        decision = (
            PolicyDecisionType.DENY if next_count >= self._threshold else PolicyDecisionType.REVIEW
        )
        return AbuseDecision(decision, next_count)

    def snapshot_keys(self) -> tuple[str, ...]:
        return tuple(self._windows.keys())

    def _key(self, *, org_id: str | None, user_id: str | None, rule_id: str) -> str:
        raw = f"{org_id or ''}:{user_id or ''}:{rule_id}"
        return f"abuse:{hashlib.sha256(raw.encode()).hexdigest()}"
