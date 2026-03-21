"""vector_documents в CRM БД для JOIN с crm_entities (семантический поиск)

Revision ID: crm_0003
Revises: crm_0002
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0003"
down_revision: Union[str, None] = "crm_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "vector_documents",
        sa.Column("id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("namespace_id", sa.String(255), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=True),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("document_name", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("ALTER TABLE vector_documents ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    op.create_index("ix_vd_namespace_id", "vector_documents", ["namespace_id"])
    op.create_index("ix_vd_company_id", "vector_documents", ["company_id"])
    op.create_index("ix_vd_document_id", "vector_documents", ["document_id"])
    op.create_index("ix_vd_namespace_company", "vector_documents", ["namespace_id", "company_id"])
    op.execute(
        """
        CREATE INDEX ix_vd_embedding_hnsw ON vector_documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_vd_embedding_hnsw", table_name="vector_documents")
    op.drop_index("ix_vd_namespace_company", table_name="vector_documents")
    op.drop_index("ix_vd_document_id", table_name="vector_documents")
    op.drop_index("ix_vd_company_id", table_name="vector_documents")
    op.drop_index("ix_vd_namespace_id", table_name="vector_documents")
    op.drop_table("vector_documents")
