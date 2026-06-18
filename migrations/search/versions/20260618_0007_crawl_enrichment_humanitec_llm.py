"""crawl enrichment humanitec_llm defaults

Revision ID: search_0007
Revises: search_0006
Create Date: 2026-06-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0007"
down_revision: Union[str, None] = "search_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE crawl_profiles
        SET enrichment_model = 'auto'
        WHERE enrichment_model = 'qwen/qwen2.5-1.5b-instruct-crawl'
           OR enrichment_model IS NULL
        """
    )
    op.execute(
        """
        UPDATE crawl_urls
        SET
            enrichment_model = NULL,
            enrichment_prompt_version = NULL,
            last_error = NULL
        WHERE enriched_content_hash IS NULL
          AND last_error IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE crawl_profiles
        SET enrichment_model = 'qwen/qwen2.5-1.5b-instruct-crawl'
        WHERE enrichment_model = 'auto'
          AND llm_enrichment_enabled = true
        """
    )
