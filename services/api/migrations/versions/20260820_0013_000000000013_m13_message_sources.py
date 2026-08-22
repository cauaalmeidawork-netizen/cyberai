"""M13 message sources (research citations).

Revision ID: 000000000013
Revises: 000000000012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000013"
down_revision = "000000000012"
branch_labels = None
depends_on = None

TENANT_IS_BOUND = "NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL"
TENANT_MATCHES = "org_id::text = current_setting('app.current_org_id', true)"
FAIL_CLOSED_POLICY = f"{TENANT_IS_BOUND} AND {TENANT_MATCHES}"


def upgrade() -> None:
    op.create_table(
        "message_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.String(length=64), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("authority_score", sa.Float(), nullable=False),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_sources")),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_message_sources_org_id", "message_sources", ["org_id"], unique=False)
    op.create_index(
        "ix_message_sources_message_id", "message_sources", ["message_id"], unique=False
    )
    op.execute("ALTER TABLE message_sources ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE message_sources FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_message_sources
        ON message_sources
        FOR ALL
        USING ({FAIL_CLOSED_POLICY})
        WITH CHECK ({FAIL_CLOSED_POLICY});
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_message_sources ON message_sources;")
    op.drop_table("message_sources")
