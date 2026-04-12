"""FTS: content_tsv + GIN на vector_documents.

Revision ID: rag_0002
Revises: rag_0001
Create Date: 2026-04-05

Статус обработки: PK document_id задаётся в baseline (rag_0001), одна строка на документ.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "rag_0002"
down_revision: Union[str, None] = "rag_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE vector_documents
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED
        """
    )
    op.create_index(
        "ix_vd_content_tsv_gin",
        "vector_documents",
        ["content_tsv"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_vd_content_tsv_gin", table_name="vector_documents")
    op.drop_column("vector_documents", "content_tsv")
