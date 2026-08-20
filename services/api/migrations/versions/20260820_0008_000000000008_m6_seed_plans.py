"""Seed M6 billing plans.

Revision ID: 000000000008
Revises: 000000000007
"""

from __future__ import annotations

from alembic import op

revision = "000000000008"
down_revision = "000000000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO plans (key, display_name, limits_json, is_active, created_at)
        VALUES
          ('free', 'Free', '{"monthly_requests": 100}'::jsonb, true, now()),
          ('pro', 'Pro', '{"monthly_requests": 2000}'::jsonb, true, now()),
          ('business', 'Business', '{"monthly_requests": 20000}'::jsonb, true, now()),
          ('enterprise', 'Enterprise', '{"monthly_requests": 1000000}'::jsonb, true, now())
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM plans WHERE key IN ('free', 'pro', 'business', 'enterprise');")
