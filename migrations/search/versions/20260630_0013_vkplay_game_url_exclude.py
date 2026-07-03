"""vkplay game launcher URL exclude and backlog cleanup

Revision ID: search_0013
Revises: search_0012
Create Date: 2026-06-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0013"
down_revision: Union[str, None] = "search_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE crawl_domains
        SET exclude_url_patterns = exclude_url_patterns || '["/play/game(/|$)"]'::jsonb,
            updated_at = NOW()
        WHERE domain = 'vkplay.ru'
          AND crawl_profile_id = 'runet_platform'
          AND NOT (exclude_url_patterns @> '["/play/game(/|$)"]'::jsonb)
        """
    )
    op.execute(
        """
        UPDATE crawl_urls cu
        SET crawl_status = 'skipped',
            fetch_attempts = 0,
            next_retry_after = NULL,
            last_error = NULL,
            last_crawled_at = NOW(),
            updated_at = NOW()
        FROM crawl_domains cd
        WHERE cu.crawl_domain_id = cd.crawl_domain_id
          AND cd.domain = 'vkplay.ru'
          AND cd.crawl_profile_id = 'runet_platform'
          AND cu.canonical_url ~ '/play/game(/|$)'
          AND cu.crawl_status IN ('pending', 'fetching', 'failed')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE crawl_domains
        SET exclude_url_patterns = (
            SELECT COALESCE(jsonb_agg(elem), '[]'::jsonb)
            FROM jsonb_array_elements_text(exclude_url_patterns) AS elem
            WHERE elem <> '/play/game(/|$)'
        ),
        updated_at = NOW()
        WHERE domain = 'vkplay.ru'
          AND crawl_profile_id = 'runet_platform'
        """
    )
