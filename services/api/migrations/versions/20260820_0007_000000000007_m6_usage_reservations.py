"""M6 usage reservations.

Revision ID: 000000000007
Revises: 000000000006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000007"
down_revision = "000000000006"
branch_labels = None
depends_on = None

TENANT_IS_BOUND = "NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL"
TENANT_MATCHES = "org_id::text = current_setting('app.current_org_id', true)"
FAIL_CLOSED_POLICY = f"{TENANT_IS_BOUND} AND {TENANT_MATCHES}"


def upgrade() -> None:
    op.create_table(
        "usage_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("plan_key", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_input_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_output_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_total_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_reservations")),
        sa.UniqueConstraint("org_id", "request_id", name="uq_usage_reservations_org_request"),
    )
    op.create_index("ix_usage_reservations_org_id", "usage_reservations", ["org_id"], unique=False)
    op.execute("ALTER TABLE usage_reservations ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE usage_reservations FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_usage_reservations
        ON usage_reservations
        FOR ALL
        USING ({FAIL_CLOSED_POLICY})
        WITH CHECK ({FAIL_CLOSED_POLICY});
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_usage_reservations ON usage_reservations;")
    op.drop_table("usage_reservations")
