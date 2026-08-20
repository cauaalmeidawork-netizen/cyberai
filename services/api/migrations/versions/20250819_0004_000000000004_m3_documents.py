"""M3: RAG Ingestion API (document hash and cascade).

Revision ID: 000000000004
Revises: 000000000003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "000000000004"
down_revision = "000000000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add content_hash to documents
    op.add_column("documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    # Set a dummy hash for existing rows if any, then make it NOT NULL
    op.execute("UPDATE documents SET content_hash = 'legacy' WHERE content_hash IS NULL")
    op.alter_column("documents", "content_hash", nullable=False)
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"], unique=False)

    # 2. Add CASCADE to chunks.document_id
    # First, drop the existing foreign key
    op.drop_constraint("fk_chunks_document_id_documents", "chunks", type_="foreignkey")
    # Then recreate it with ON DELETE CASCADE
    op.create_foreign_key(
        "fk_chunks_document_id_documents",
        "chunks",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # 1. Revert CASCADE on chunks.document_id
    op.drop_constraint("fk_chunks_document_id_documents", "chunks", type_="foreignkey")
    op.create_foreign_key(
        "fk_chunks_document_id_documents", "chunks", "documents", ["document_id"], ["id"]
    )

    # 2. Remove content_hash from documents
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
