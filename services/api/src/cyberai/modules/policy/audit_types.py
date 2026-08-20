"""Policy audit event types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SecurityAuditEvent:
    event_type: str
    org_id: UUID
    user_id: UUID | None
    request_id: str | None
    policy: str
    rule_id: str
    decision: str
    metadata: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class SecurityAuditSink(Protocol):
    async def record(self, event: SecurityAuditEvent) -> None: ...


class NoopSecurityAuditSink:
    async def record(self, event: SecurityAuditEvent) -> None:
        return None
