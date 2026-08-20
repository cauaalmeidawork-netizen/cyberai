"""Integration tests for security audit events."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, text

from cyberai.modules.policy import SecurityAuditEvent
from cyberai.modules.policy.audit import SecurityAuditRecorder
from cyberai.platform.db import Database, TenantContext
from cyberai.platform.db.models import Organization, SecurityAuditEventModel, User

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_security_audit_event_is_tenant_scoped_and_redacts_metadata(
    db: Database,
    test_org: Organization,
    test_user: User,
) -> None:
    recorder = SecurityAuditRecorder(db)
    request_id = f"req-audit-{uuid4().hex[:8]}"

    await recorder.record(
        SecurityAuditEvent(
            event_type="policy_denied",
            org_id=test_org.id,
            user_id=test_user.id,
            request_id=request_id,
            policy="default",
            rule_id="prompt_injection_override",
            decision="deny",
            metadata={
                "authorization": "Bearer secret",
                "prompt": "full user prompt",
                "source_type": "chat",
            },
        )
    )

    async with db.session(TenantContext(org_id=test_org.id)) as session:
        event = await session.scalar(
            select(SecurityAuditEventModel).where(SecurityAuditEventModel.request_id == request_id)
        )

    assert event is not None
    assert event.org_id == test_org.id
    assert event.metadata_json == {"source_type": "chat"}

    other_org = Organization(
        slug=f"audit-other-org-{uuid4().hex[:8]}",
        display_name="Audit Other Org",
    )
    async with db.session() as session:
        session.add(other_org)
        await session.flush()

    async with db.session(TenantContext(org_id=other_org.id)) as session:
        leaked_event = await session.scalar(
            select(SecurityAuditEventModel).where(
                SecurityAuditEventModel.request_id == request_id,
                SecurityAuditEventModel.org_id == other_org.id,
            )
        )

    assert leaked_event is None

    async with db.session() as session:
        policy_expr = await session.scalar(
            text(
                """
                SELECT pg_get_expr(polqual, polrelid)
                FROM pg_policy
                WHERE polrelid = 'security_audit_events'::regclass
                  AND polname = 'tenant_isolation_security_audit_events'
                """
            )
        )

    assert policy_expr is not None
    assert "NULLIF(current_setting('app.current_org_id'" in policy_expr
    assert "IS NOT NULL" in policy_expr
    assert " OR " not in policy_expr.upper()
    async with db.session() as session:
        await session.execute(
            text("DELETE FROM security_audit_events WHERE request_id = :request_id"),
            {"request_id": request_id},
        )
        await session.execute(
            text("DELETE FROM organizations WHERE id = :id"),
            {"id": other_org.id},
        )
