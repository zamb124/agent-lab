"""CRM vector_documents: vector(1024) + HNSW.

Revision ID: crm_0023
Revises: crm_0022
Create Date: 2026-05-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0023"
down_revision: Union[str, None] = "crm_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vd_embedding_hnsw")
    op.execute(
        """
        ALTER TABLE vector_documents
        ALTER COLUMN embedding TYPE vector(1024) USING NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_vd_embedding_hnsw ON vector_documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vd_embedding_hnsw")
    op.execute(
        """
        ALTER TABLE vector_documents
        ALTER COLUMN embedding TYPE vector(4096) USING NULL
        """
    )
