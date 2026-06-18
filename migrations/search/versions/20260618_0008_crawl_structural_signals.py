"""crawl structural signals column and structured enrichment requeue

Revision ID: search_0008
Revises: search_0007
Create Date: 2026-06-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0008"
down_revision: Union[str, None] = "search_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_urls
        ADD COLUMN IF NOT EXISTS extract_structural_signals JSONB
        """
    )
    op.execute(
        """
        UPDATE crawl_urls
        SET
            enriched_content_hash = NULL,
            enrichment_model = NULL,
            enrichment_prompt_version = NULL,
            last_error = NULL
        WHERE crawl_status = 'indexed'
          AND document_id IS NOT NULL
          AND (
            enrichment_prompt_version IS DISTINCT FROM 'structured'
            OR enriched_content_hash IS NULL
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_urls
        DROP COLUMN IF EXISTS extract_structural_signals
        """
    )
