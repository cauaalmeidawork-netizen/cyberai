"""M7 security audit events.

Revision ID: 000000000009
Revises: 000000000008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "000000000009"
down_revision = "000000000008"
branch_labels = None
depends_on = None

TENANT_IS_BOUND = "NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL"
TENANT_MATCHES = "org_id::text = current_setting('app.current_org_id', true)"
FAIL_CLOSED_POLICY = f"{TENANT_IS_BOUND} AND {TENANT_MATCHES}"


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("policy", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_security_audit_events")),
    )
    op.create_index(
        "ix_security_audit_events_org_id", "security_audit_events", ["org_id"], unique=False
    )
    op.execute("ALTER TABLE security_audit_events ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE security_audit_events FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_security_audit_events
        ON security_audit_events
        FOR ALL
        USING ({FAIL_CLOSED_POLICY})
        WITH CHECK ({FAIL_CLOSED_POLICY});
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_security_audit_events ON security_audit_events;"
    )
    op.drop_table("security_audit_events")
