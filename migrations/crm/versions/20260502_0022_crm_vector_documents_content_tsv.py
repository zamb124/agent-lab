"""FTS на CRM vector_documents: content_tsv + GIN (гибридный поиск в CRM БД).

Revision ID: crm_0022
Revises: crm_0021
Create Date: 2026-05-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0022"
down_revision: Union[str, None] = "crm_0021"
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
