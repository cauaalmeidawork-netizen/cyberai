"""M10 chat history, idempotency and fail-closed chat RLS.

Revision ID: 000000000010
Revises: 000000000009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000010"
down_revision = "000000000009"
branch_labels = None
depends_on = None

TENANT_IS_BOUND = "NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL"
TENANT_MATCHES = "org_id::text = current_setting('app.current_org_id', true)"
FAIL_CLOSED_POLICY = f"{TENANT_IS_BOUND} AND {TENANT_MATCHES}"
PERMISSIVE_POLICY = (
    "org_id::text = current_setting('app.current_org_id', true) "
    "OR current_setting('app.current_org_id', true) = ''"
)


def upgrade() -> None:
    op.create_table(
        "chat_idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=True),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=True),
        sa.Column("model_key", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"],
            ["messages.id"],
            name=op.f("fk_chat_idempotency_keys_assistant_message_id_messages"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_chat_idempotency_keys_conversation_id_conversations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["messages.id"],
            name=op.f("fk_chat_idempotency_keys_user_message_id_messages"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_idempotency_keys")),
        sa.UniqueConstraint(
            "org_id",
            "conversation_id",
            "idempotency_key",
            name="uq_chat_idempotency_org_conversation_key",
        ),
    )
    op.create_index(
        op.f("ix_chat_idempotency_keys_conversation_id"),
        "chat_idempotency_keys",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_idempotency_keys_org_id"),
        "chat_idempotency_keys",
        ["org_id"],
        unique=False,
    )
    op.execute("ALTER TABLE chat_idempotency_keys ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE chat_idempotency_keys FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_chat_idempotency_keys
        ON chat_idempotency_keys
        FOR ALL
        USING ({FAIL_CLOSED_POLICY})
        WITH CHECK ({FAIL_CLOSED_POLICY});
        """
    )

    for table in ("projects", "conversations", "messages"):
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
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_chat_idempotency_keys ON chat_idempotency_keys;"
    )
    op.drop_index(op.f("ix_chat_idempotency_keys_org_id"), table_name="chat_idempotency_keys")
    op.drop_index(
        op.f("ix_chat_idempotency_keys_conversation_id"), table_name="chat_idempotency_keys"
    )
    op.drop_table("chat_idempotency_keys")

    for table in ("projects", "conversations", "messages"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table}
            ON {table}
            FOR ALL
            USING ({PERMISSIVE_POLICY})
            WITH CHECK ({PERMISSIVE_POLICY});
            """
        )
