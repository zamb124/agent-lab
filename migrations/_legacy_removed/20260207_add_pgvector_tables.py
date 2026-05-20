"""add pgvector extension and vector_documents + crm_entities tables

Revision ID: a1b2c3d4e5f6
Revises: 9b4c6d8e0f2a
Create Date: 2026-02-07 12:00:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9b4c6d8e0f2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # расширение pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # vector_documents -- единое хранилище для RAG, CRM, Agents
    op.create_table(
        "vector_documents",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("namespace_id", sa.String(255), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=True),
        sa.Column("document_id", sa.String(255), nullable=False),
        sa.Column("document_name", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Используем raw SQL для создания колонки vector (Alembic не поддерживает тип vector напрямую)
    op.execute("ALTER TABLE vector_documents DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE vector_documents ADD COLUMN embedding vector(1024)")

    # B-tree индексы
    op.create_index("ix_vd_namespace_id", "vector_documents", ["namespace_id"])
    op.create_index("ix_vd_company_id", "vector_documents", ["company_id"])
    op.create_index("ix_vd_namespace_company", "vector_documents", ["namespace_id", "company_id"])
    op.create_index("ix_vd_document_id", "vector_documents", ["document_id"])

    # HNSW индекс для vector similarity search
    op.execute("""
        CREATE INDEX ix_vd_embedding_hnsw
        ON vector_documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # crm_entities -- структурные атрибуты CRM сущностей
    op.create_table(
        "crm_entities",
        sa.Column("entity_id", sa.String(100), primary_key=True),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False, server_default="default"),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_subtype", sa.String(100), nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("note_date", sa.Date(), nullable=True),
        sa.Column("assignees", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("attachment_ids", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("source_entity_id", sa.String(100), nullable=True),
        sa.Column("source_company_id", sa.String(100), nullable=True),
        sa.Column("relevance", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # crm_entities индексы
    op.create_index("ix_crm_entities_company_id", "crm_entities", ["company_id"])
    op.create_index("ix_crm_entities_entity_type", "crm_entities", ["entity_type"])
    op.create_index("ix_crm_entities_company_type", "crm_entities", ["company_id", "entity_type"])
    op.create_index("ix_crm_entities_namespace", "crm_entities", ["company_id", "namespace"])
    op.create_index("ix_crm_entities_due_date", "crm_entities", ["due_date"])
    op.create_index("ix_crm_entities_note_date", "crm_entities", ["note_date"])
    op.execute("""
        CREATE INDEX ix_crm_entities_tags
        ON crm_entities
        USING gin (tags)
    """)


def downgrade() -> None:
    # crm_entities
    op.execute("DROP INDEX IF EXISTS ix_crm_entities_tags")
    op.drop_index("ix_crm_entities_note_date", table_name="crm_entities")
    op.drop_index("ix_crm_entities_due_date", table_name="crm_entities")
    op.drop_index("ix_crm_entities_namespace", table_name="crm_entities")
    op.drop_index("ix_crm_entities_company_type", table_name="crm_entities")
    op.drop_index("ix_crm_entities_entity_type", table_name="crm_entities")
    op.drop_index("ix_crm_entities_company_id", table_name="crm_entities")
    op.drop_table("crm_entities")

    # vector_documents
    op.execute("DROP INDEX IF EXISTS ix_vd_embedding_hnsw")
    op.drop_index("ix_vd_document_id", table_name="vector_documents")
    op.drop_index("ix_vd_namespace_company", table_name="vector_documents")
    op.drop_index("ix_vd_company_id", table_name="vector_documents")
    op.drop_index("ix_vd_namespace_id", table_name="vector_documents")
    op.drop_table("vector_documents")

    op.execute("DROP EXTENSION IF EXISTS vector")
