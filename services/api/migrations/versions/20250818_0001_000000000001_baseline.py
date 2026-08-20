"""Baseline: tenant context and user/organization tables.

This is the first migration. It does not yet create tenant-scoped application
tables (those arrive with the chat module in M1), but it establishes the RLS
mechanism and the identity tables that chat tables will reference.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "000000000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Application role that owns tenant-scoped data. The API will connect with a
    # user that has this role so it can set the tenant variable for RLS.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cyberai_app') THEN "
        "CREATE ROLE cyberai_app NOLOGIN; "
        "END IF; "
        "END $$;"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO cyberai_app;")

    # A small, immutable table storing all known organizations. It has no RLS
    # because the application's own authorization decides whether to allow an
    # identity to create an organization; this table is just the registry.
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("identity_provider_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=False)

    # User records are always local: the managed identity provider owns the
    # credential, but we need a stable row to attach usage and audit events to.
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("identity_provider_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_users_org_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint(
            "org_id",
            "identity_provider_id",
            name=op.f("uq_users_org_id_identity_provider_id"),
        ),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"], unique=False)
    op.create_index(
        "ix_users_identity_provider_id", "users", ["identity_provider_id"], unique=False
    )

    # A usage ledger table for inference accounting. It is tenant-scoped so it
    # will have RLS enabled; for now the table is created and policies are added
    # separately to keep the migration readable.
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_key", sa.String(length=128), nullable=False),
        sa.Column("provider_model", sa.String(length=128), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("time_to_first_token_ms", sa.Float(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("actual_cost_usd", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_records")),
    )
    op.create_index("ix_usage_records_org_id", "usage_records", ["org_id"], unique=False)
    op.create_index("ix_usage_records_occurred_at", "usage_records", ["occurred_at"], unique=False)

    # Row Level Security for every tenant-scoped table.
    for table in ("users", "usage_records"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table}
            ON {table}
            USING (org_id::text = current_setting('app.current_org_id', true) OR
                   current_setting('app.current_org_id', true) = '');
            """
        )


def downgrade() -> None:
    for table in ("users", "usage_records"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("usage_records")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute("REVOKE ALL ON SCHEMA public FROM cyberai_app;")
    op.execute("DROP ROLE IF EXISTS cyberai_app;")
