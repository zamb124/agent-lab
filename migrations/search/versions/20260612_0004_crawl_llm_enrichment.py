"""crawl llm enrichment columns

Revision ID: search_0004
Revises: search_0003
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0004"
down_revision: Union[str, None] = "search_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_profiles
            ADD COLUMN IF NOT EXISTS llm_enrichment_enabled BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS enrichment_model VARCHAR(128) NULL
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_urls
            ADD COLUMN IF NOT EXISTS extract_content_hash VARCHAR(64) NULL,
            ADD COLUMN IF NOT EXISTS enriched_content_hash VARCHAR(64) NULL,
            ADD COLUMN IF NOT EXISTS enrichment_model VARCHAR(128) NULL,
            ADD COLUMN IF NOT EXISTS enrichment_prompt_version VARCHAR(32) NULL
        """
    )
    op.execute(
        """
        UPDATE crawl_urls
        SET extract_content_hash = content_hash
        WHERE content_hash IS NOT NULL AND extract_content_hash IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_jobs
            ADD COLUMN IF NOT EXISTS urls_enriched INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS urls_enrichment_failed INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        UPDATE crawl_profiles
        SET
            llm_enrichment_enabled = true,
            enrichment_model = 'qwen/qwen2.5-1.5b-instruct-crawl'
        WHERE crawl_profile_id = 'runet_platform'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_jobs
            DROP COLUMN IF EXISTS urls_enrichment_failed,
            DROP COLUMN IF EXISTS urls_enriched
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_urls
            DROP COLUMN IF EXISTS enrichment_prompt_version,
            DROP COLUMN IF EXISTS enrichment_model,
            DROP COLUMN IF EXISTS enriched_content_hash,
            DROP COLUMN IF EXISTS extract_content_hash
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_profiles
            DROP COLUMN IF EXISTS enrichment_model,
            DROP COLUMN IF EXISTS llm_enrichment_enabled
        """
    )
