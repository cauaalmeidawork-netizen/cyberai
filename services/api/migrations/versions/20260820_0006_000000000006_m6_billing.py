"""M6 billing foundation.

Revision ID: 000000000006
Revises: 000000000005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "000000000006"
down_revision = "000000000005"
branch_labels = None
depends_on = None

TENANT_IS_BOUND = "NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL"
TENANT_MATCHES = "org_id::text = current_setting('app.current_org_id', true)"
FAIL_CLOSED_POLICY = f"{TENANT_IS_BOUND} AND {TENANT_MATCHES}"


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("limits_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_plans")),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("plan_key", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_subscriptions_org_id_organizations")
        ),
        sa.ForeignKeyConstraint(
            ["plan_key"], ["plans.key"], name=op.f("fk_subscriptions_plan_key_plans")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"], unique=False)
    op.create_table(
        "usage_aggregates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_requests", sa.Integer(), nullable=False),
        sa.Column("used_input_tokens", sa.Integer(), nullable=False),
        sa.Column("used_output_tokens", sa.Integer(), nullable=False),
        sa.Column("used_total_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_requests", sa.Integer(), nullable=False),
        sa.Column("reserved_input_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_output_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_total_tokens", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_aggregates")),
        sa.UniqueConstraint("org_id", "period_start", name="uq_usage_aggregates_org_period"),
    )
    op.create_index("ix_usage_aggregates_org_id", "usage_aggregates", ["org_id"], unique=False)
    op.create_table(
        "model_costs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_token_unit_cost", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("output_token_unit_cost", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_costs")),
    )
    op.create_index("ix_model_costs_provider", "model_costs", ["provider"], unique=False)
    op.create_index("ix_model_costs_model", "model_costs", ["model"], unique=False)

    op.create_unique_constraint(
        "uq_usage_records_org_id_request_id",
        "usage_records",
        ["org_id", "request_id"],
    )

    for table in ("usage_records", "subscriptions", "usage_aggregates"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
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
    for table in ("usage_records", "subscriptions", "usage_aggregates"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")
    op.drop_constraint("uq_usage_records_org_id_request_id", "usage_records", type_="unique")
    op.drop_table("model_costs")
    op.drop_table("usage_aggregates")
    op.drop_table("subscriptions")
    op.drop_table("plans")
