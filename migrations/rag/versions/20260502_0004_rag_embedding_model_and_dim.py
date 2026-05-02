"""Размерность embedding vector(4096), колонка embedding_model.

Индекс HNSW по embedding для этой размерности не создаётся: в pgvector лимит
размерности для HNSW — 2000 float-компонент на кортеж индекса. Векторный поиск
выполняется без ANN-индекса по колонке embedding.

Revision ID: rag_0004
Revises: rag_0003
Create Date: 2026-05-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "rag_0004"
down_revision: Union[str, None] = "rag_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vd_embedding_hnsw")
    op.execute(
        """
        ALTER TABLE vector_documents
        ALTER COLUMN embedding TYPE vector(4096) USING NULL
        """
    )
    op.execute(
        """
        ALTER TABLE vector_documents
        ADD COLUMN embedding_model VARCHAR(255) DEFAULT NULL
        """
    )
    op.execute("CREATE INDEX ix_vd_embedding_model ON vector_documents (embedding_model)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vd_embedding_hnsw")
    op.execute("ALTER TABLE vector_documents ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    op.execute("DROP INDEX IF EXISTS ix_vd_embedding_model")
    op.execute("ALTER TABLE vector_documents DROP COLUMN IF EXISTS embedding_model")
    op.execute(
        """
        CREATE INDEX ix_vd_embedding_hnsw ON vector_documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
