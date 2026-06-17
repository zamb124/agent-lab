"""crawl batch limits for runet_platform

Revision ID: search_0005
Revises: search_0004
Create Date: 2026-06-17
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0005"
down_revision: Union[str, None] = "search_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE crawl_profiles
        SET
            max_domains_per_tick = 10,
            max_urls_per_domain_per_tick = 10,
            max_urls_per_batch = 10,
            http_concurrency = 2
        WHERE crawl_profile_id = 'runet_platform'
        """
    )
    op.execute(
        """
        UPDATE crawl_jobs
        SET status = 'failed', finished_at = NOW()
        WHERE status = 'running' AND finished_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE crawl_profiles
        SET
            max_domains_per_tick = 20,
            max_urls_per_domain_per_tick = 200,
            max_urls_per_batch = 50,
            http_concurrency = 8
        WHERE crawl_profile_id = 'runet_platform'
        """
    )
