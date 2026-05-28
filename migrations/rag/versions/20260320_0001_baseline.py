"""Базовая миграция rag DB

Revision ID: rag_0001
Revises:
Create Date: 2026-03-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "rag_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_processing_status",
        sa.Column("document_id", sa.String(255), primary_key=True, nullable=False),
        sa.Column("task_id", sa.String(255), nullable=False, unique=True),
        sa.Column("namespace_id", sa.String(255), nullable=False),
        sa.Column("document_name", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("s3_key", sa.String(1000), nullable=True),
        sa.Column("s3_bucket", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("chunks_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_document_processing_status_document_id", "document_processing_status", ["document_id"])
    op.create_index("ix_document_processing_status_namespace_id", "document_processing_status", ["namespace_id"])
    op.create_index("ix_document_processing_status_status", "document_processing_status", ["status"])
    op.create_index("ix_document_status_task_id", "document_processing_status", ["task_id"])
    op.create_index("ix_document_status_namespace_status", "document_processing_status", ["namespace_id", "status"])

    op.create_table(
        "vector_documents",
        sa.Column("id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("namespace_id", sa.String(255), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=True),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("document_name", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),  # тип vector создаётся отдельно
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Заменяем JSONB-колонку embedding на vector(1024)
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
    op.drop_table("vector_documents")
    op.drop_table("document_processing_status")
