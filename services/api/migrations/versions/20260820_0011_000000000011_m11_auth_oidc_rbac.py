"""M11 OIDC, sessions, memberships and RBAC.

Revision ID: 000000000011
Revises: 000000000010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000011"
down_revision = "000000000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_identities_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identities")),
        sa.UniqueConstraint("issuer", "subject", name="uq_identities_issuer_subject"),
    )
    op.create_index(op.f("ix_identities_issuer"), "identities", ["issuer"], unique=False)
    op.create_index(op.f("ix_identities_subject"), "identities", ["subject"], unique=False)
    op.create_index(op.f("ix_identities_user_id"), "identities", ["user_id"], unique=False)

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_memberships_org_id_organizations")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("user_id", "org_id", name="uq_memberships_user_org"),
    )
    op.create_index(op.f("ix_memberships_org_id"), "memberships", ["org_id"], unique=False)
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("active_org_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from_session_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["active_org_id"],
            ["organizations.id"],
            name=op.f("fk_auth_sessions_active_org_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_auth_sessions_membership_id_memberships"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("session_token_hash", name=op.f("uq_auth_sessions_session_token_hash")),
    )
    op.create_index(
        op.f("ix_auth_sessions_active_org_id"), "auth_sessions", ["active_org_id"], unique=False
    )
    op.create_index(
        op.f("ix_auth_sessions_expires_at"), "auth_sessions", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_auth_sessions_session_token_hash"),
        "auth_sessions",
        ["session_token_hash"],
        unique=False,
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)

    op.create_table(
        "oidc_login_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("pkce_verifier", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.String(length=512), nullable=False),
        sa.Column("return_to", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oidc_login_states")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_oidc_login_states_state_hash")),
    )
    op.create_index(
        op.f("ix_oidc_login_states_expires_at"),
        "oidc_login_states",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oidc_login_states_state_hash"),
        "oidc_login_states",
        ["state_hash"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO memberships (id, user_id, org_id, role, status, created_at, updated_at)
        SELECT gen_random_uuid(), id, org_id, COALESCE(NULLIF(role, ''), 'member'), 'active',
               created_at, updated_at
        FROM users
        ON CONFLICT (user_id, org_id) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO identities (id, user_id, issuer, subject, email, created_at, updated_at)
        SELECT gen_random_uuid(), id, 'legacy', identity_provider_id, email, created_at, updated_at
        FROM users
        ON CONFLICT (issuer, subject) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_oidc_login_states_state_hash"), table_name="oidc_login_states")
    op.drop_index(op.f("ix_oidc_login_states_expires_at"), table_name="oidc_login_states")
    op.drop_table("oidc_login_states")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_session_token_hash"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_expires_at"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_active_org_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_org_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_index(op.f("ix_identities_user_id"), table_name="identities")
    op.drop_index(op.f("ix_identities_subject"), table_name="identities")
    op.drop_index(op.f("ix_identities_issuer"), table_name="identities")
    op.drop_table("identities")
