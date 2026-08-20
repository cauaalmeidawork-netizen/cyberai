"""Fail closed RLS policies for RAG tables.

Revision ID: 000000000005
Revises: 000000000004
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "000000000005"
down_revision = "000000000004"
branch_labels = None
depends_on = None

TENANT_IS_BOUND = "NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL"
TENANT_MATCHES = "org_id::text = current_setting('app.current_org_id', true)"
FAIL_CLOSED_POLICY = f"{TENANT_IS_BOUND} AND {TENANT_MATCHES}"


def upgrade() -> None:
    for table in ("documents", "chunks"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table}
            ON {table}
            FOR ALL
            USING ({FAIL_CLOSED_POLICY})
            WITH CHECK ({FAIL_CLOSED_POLICY});
            """
        )


def downgrade() -> None:
    for table in ("documents", "chunks"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table}
            ON {table}
            USING (org_id::text = current_setting('app.current_org_id', true) OR
                   current_setting('app.current_org_id', true) = '');
            """
        )
