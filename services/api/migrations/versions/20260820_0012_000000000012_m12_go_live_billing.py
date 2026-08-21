"""M12 billing provider state and webhook idempotency.

Revision ID: 000000000012
Revises: 000000000011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000012"
down_revision = "000000000011"
branch_labels = None
depends_on = None

TENANT_IS_BOUND = "NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL"
TENANT_MATCHES = "org_id::text = current_setting('app.current_org_id', true)"
FAIL_CLOSED_POLICY = f"{TENANT_IS_BOUND} AND {TENANT_MATCHES}"


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column(
        "subscriptions", sa.Column("provider_customer_id", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "subscriptions",
        sa.Column("provider_subscription_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "subscriptions", sa.Column("provider_status", sa.String(length=32), nullable=True)
    )
    op.create_index(
        op.f("ix_subscriptions_provider_customer_id"),
        "subscriptions",
        ["provider_customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscriptions_provider_subscription_id"),
        "subscriptions",
        ["provider_subscription_id"],
        unique=False,
    )

    op.create_table(
        "billing_customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_billing_customers_org_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_customers")),
        sa.UniqueConstraint("org_id", "provider", name="uq_billing_customers_org_provider"),
        sa.UniqueConstraint(
            "provider",
            "provider_customer_id",
            name="uq_billing_customers_provider_customer",
        ),
    )
    op.create_index(
        op.f("ix_billing_customers_org_id"), "billing_customers", ["org_id"], unique=False
    )
    op.create_index(
        op.f("ix_billing_customers_provider_customer_id"),
        "billing_customers",
        ["provider_customer_id"],
        unique=False,
    )
    op.execute("ALTER TABLE billing_customers ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE billing_customers FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_billing_customers
        ON billing_customers
        FOR ALL
        USING ({FAIL_CLOSED_POLICY})
        WITH CHECK ({FAIL_CLOSED_POLICY});
        """
    )

    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_webhook_events")),
        sa.UniqueConstraint(
            "provider",
            "event_id",
            name="uq_billing_webhook_events_provider_event",
        ),
    )
    op.create_index(
        op.f("ix_billing_webhook_events_event_id"),
        "billing_webhook_events",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_billing_webhook_events_provider"),
        "billing_webhook_events",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_billing_webhook_events_provider"), table_name="billing_webhook_events")
    op.drop_index(op.f("ix_billing_webhook_events_event_id"), table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_billing_customers ON billing_customers;")
    op.drop_index(op.f("ix_billing_customers_provider_customer_id"), table_name="billing_customers")
    op.drop_index(op.f("ix_billing_customers_org_id"), table_name="billing_customers")
    op.drop_table("billing_customers")
    op.drop_index(op.f("ix_subscriptions_provider_subscription_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_provider_customer_id"), table_name="subscriptions")
    op.drop_column("subscriptions", "provider_status")
    op.drop_column("subscriptions", "provider_subscription_id")
    op.drop_column("subscriptions", "provider_customer_id")
    op.drop_column("subscriptions", "provider")
