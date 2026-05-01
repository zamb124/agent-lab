"""TTL для строк статуса RAG-документов и backfill метаданных чанков.

Revision ID: rag_0003
Revises: rag_0002
Create Date: 2026-05-01

Колонка ``ttl_seconds`` в ``document_processing_status``: секунды жизни после
готовности индекса; ``0`` — без автоочистки. Для чанков без ключа ``ttl_seconds``
в ``metadata`` подмешивается значение: признаки CRM (вложения / текст сущности)
получают ``0``, остальные — ``864000`` (10 суток).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "rag_0003"
down_revision: Union[str, None] = "rag_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE document_processing_status
        ADD COLUMN ttl_seconds INTEGER NOT NULL DEFAULT 864000
        """
    )
    op.execute(
        """
        UPDATE document_processing_status
        SET ttl_seconds = 0
        WHERE COALESCE(extra_metadata->>'entity_id', '') <> ''
        """
    )
    op.execute(
        """
        UPDATE vector_documents
        SET metadata = metadata || '{"ttl_seconds": 0}'::jsonb
        WHERE NOT (metadata ? 'ttl_seconds')
          AND (
            metadata ? 'entity_id'
            OR (
              metadata ? 'entity_type'
              AND metadata ? 'company_id'
              AND NOT (metadata ? 'filename')
            )
          )
        """
    )
    op.execute(
        """
        UPDATE vector_documents
        SET metadata = metadata || '{"ttl_seconds": 864000}'::jsonb
        WHERE NOT (metadata ? 'ttl_seconds')
        """
    )


def downgrade() -> None:
    op.drop_column("document_processing_status", "ttl_seconds")
