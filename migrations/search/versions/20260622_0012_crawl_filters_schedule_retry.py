"""crawl url filters, per-domain schedule, fetch retry backoff

Revision ID: search_0012
Revises: search_0011
Create Date: 2026-06-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0012"
down_revision: Union[str, None] = "search_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_profiles
        ADD COLUMN IF NOT EXISTS include_url_patterns JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_profiles
        ADD COLUMN IF NOT EXISTS exclude_url_patterns JSONB NOT NULL
        DEFAULT '["/(cart|checkout|login|auth|search)(/|$)"]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_profiles
        ADD COLUMN IF NOT EXISTS exclude_extensions JSONB NOT NULL
        DEFAULT '["pdf","zip","jpg","jpeg","png","gif"]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_domains
        ADD COLUMN IF NOT EXISTS refresh_interval_seconds INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_domains
        ADD COLUMN IF NOT EXISTS include_url_patterns JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_domains
        ADD COLUMN IF NOT EXISTS exclude_url_patterns JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_domains
        DROP COLUMN IF EXISTS crawl_policy
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_urls
        ADD COLUMN IF NOT EXISTS fetch_attempts INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        ALTER TABLE crawl_urls
        ADD COLUMN IF NOT EXISTS next_retry_after TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE crawl_urls DROP COLUMN IF EXISTS next_retry_after")
    op.execute("ALTER TABLE crawl_urls DROP COLUMN IF EXISTS fetch_attempts")
    op.execute(
        """
        ALTER TABLE crawl_domains
        ADD COLUMN IF NOT EXISTS crawl_policy VARCHAR(32) NOT NULL DEFAULT 'sitemap_only'
        """
    )
    op.execute("ALTER TABLE crawl_domains DROP COLUMN IF EXISTS exclude_url_patterns")
    op.execute("ALTER TABLE crawl_domains DROP COLUMN IF EXISTS include_url_patterns")
    op.execute("ALTER TABLE crawl_domains DROP COLUMN IF EXISTS refresh_interval_seconds")
    op.execute("ALTER TABLE crawl_profiles DROP COLUMN IF EXISTS exclude_extensions")
    op.execute("ALTER TABLE crawl_profiles DROP COLUMN IF EXISTS exclude_url_patterns")
    op.execute("ALTER TABLE crawl_profiles DROP COLUMN IF EXISTS include_url_patterns")
