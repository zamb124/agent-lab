"""crawl_urls layer-1 markdown snapshot for async enrichment

Revision ID: search_0006
Revises: search_0005
Create Date: 2026-06-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0006"
down_revision: Union[str, None] = "search_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_urls
        ADD COLUMN IF NOT EXISTS extract_markdown TEXT,
        ADD COLUMN IF NOT EXISTS extract_title TEXT
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_urls
        DROP COLUMN IF EXISTS extract_title,
        DROP COLUMN IF EXISTS extract_markdown
        """
    )
