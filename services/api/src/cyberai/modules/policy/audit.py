"""Security audit recorder."""

from __future__ import annotations

from cyberai.core.logging import get_logger
from cyberai.modules.policy.audit_types import SecurityAuditEvent
from cyberai.observability.metrics import MetricsRecorder, NoopMetricsRecorder
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.models import SecurityAuditEventModel

logger = get_logger(__name__)
_SAFE_METADATA_KEYS = frozenset(
    {"source_type", "stage", "category", "severity", "profile", "action_type"}
)


class SecurityAuditRecorder:
    """Tenant-scoped audit recorder; failures are logged and metered."""

    def __init__(self, db: Database, *, metrics: MetricsRecorder | None = None) -> None:
        self._db = db
        self._metrics = metrics or NoopMetricsRecorder()

    async def record(self, event: SecurityAuditEvent) -> None:
        safe_metadata = {
            key: value for key, value in event.metadata.items() if key in _SAFE_METADATA_KEYS
        }
        try:
            async with self._db.session(TenantContext(org_id=event.org_id)) as session:
                session.add(
                    SecurityAuditEventModel(
                        org_id=event.org_id,
                        user_id=event.user_id,
                        request_id=event.request_id,
                        event_type=event.event_type,
                        policy=event.policy,
                        rule_id=event.rule_id,
                        decision=event.decision,
                        metadata_json=safe_metadata,
                        created_at=event.timestamp,
                    )
                )
                await session.commit()
            self._metrics.counter(
                "security_audit_events_total",
                labels={
                    "policy": event.policy,
                    "rule": event.rule_id,
                    "decision": event.decision,
                    "stage": safe_metadata.get("stage", "unknown"),
                },
            ).add()
        except Exception as exc:
            logger.warning("security.audit_record_failed", error=type(exc).__name__)
