"""crawl enrichment snapshot for report list/detail

Revision ID: search_0009
Revises: search_0008
Create Date: 2026-06-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "search_0009"
down_revision: Union[str, None] = "search_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_urls
        ADD COLUMN IF NOT EXISTS enrichment_snapshot JSONB
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE crawl_urls
        DROP COLUMN IF EXISTS enrichment_snapshot
        """
    )
