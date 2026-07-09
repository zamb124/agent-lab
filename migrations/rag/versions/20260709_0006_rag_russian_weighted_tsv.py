"""FTS: content_tsv на russian config + веса title/headings/content.

Revision ID: rag_0006
Revises: rag_0005
Create Date: 2026-07-09

Перестройка generated column — полная перезапись tsvector по таблице
(тяжёлый ALTER на большом индексе, выполняется офлайн/в окно обслуживания).
Веса: A — заголовок страницы (metadata.page_title / document_name),
B — heading trail чанка, D — тело контента.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "rag_0006"
down_revision: Union[str, None] = "rag_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WEIGHTED_RUSSIAN_TSV = """
setweight(to_tsvector('russian', coalesce(metadata->>'page_title', document_name, '')), 'A')
|| setweight(to_tsvector('russian', coalesce(metadata->>'heading_trail', '')), 'B')
|| setweight(to_tsvector('russian', coalesce(content, '')), 'D')
"""


def upgrade() -> None:
    op.drop_index("ix_vd_content_tsv_gin", table_name="vector_documents")
    op.drop_column("vector_documents", "content_tsv")
    op.execute(
        f"""
        ALTER TABLE vector_documents
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS ({WEIGHTED_RUSSIAN_TSV}) STORED
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
